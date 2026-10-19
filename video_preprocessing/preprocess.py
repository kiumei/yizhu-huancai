"""Traceable, conservative video frame preparation for COLMAP / 3DGS.

Requires Python 3.10+, opencv-python, numpy and Pillow. No network access.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
from pathlib import Path
import shutil
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

VERSION = "1.1.0"
FLAGS_ZH = {
    "black_frame": "近乎全黑", "white_frame": "近乎全白",
    "blur_candidate": "清晰度偏低待复核", "dark_candidate": "偏暗待复核",
    "bright_candidate": "偏亮待复核", "near_duplicate": "相邻高度重复",
    "coverage_anchor": "按时间间隔保留连接候选",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def load_review(path: Path | None, source_hash: str) -> dict:
    if path is None:
        return {}
    result = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"sample_id", "source_sha256", "source_frame_index", "timestamp_seconds",
                    "sampling_fps", "decision", "comment"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("复核 CSV 缺少字段：" + ", ".join(sorted(required)))
        for row in reader:
            key = row["sample_id"].strip()
            if not key or key in result:
                raise ValueError(f"复核 ID 为空或重复：{key}")
            if row["source_sha256"].strip() != source_hash:
                raise ValueError(f"复核表与原视频 SHA256 不匹配：{key}")
            decision = row["decision"].strip().lower() or "auto"
            if decision not in {"auto", "keep", "drop"}:
                raise ValueError(f"不支持的复核决定：{decision}")
            result[key] = {"decision": decision, "comment": row["comment"].strip(),
                           "frame": int(row["source_frame_index"]),
                           "time": float(row["timestamp_seconds"]), "fps": float(row["sampling_fps"])}
    return result


def quality(frame: np.ndarray, analysis_max_side: int = 640) -> tuple[dict, np.ndarray]:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    scale = min(1.0, analysis_max_side / max(w, h))
    if scale < 1:
        gray = cv2.resize(gray, (max(1, round(w * scale)), max(1, round(h * scale))),
                          interpolation=cv2.INTER_AREA)
    tiny = cv2.resize(gray, (64, 64), interpolation=cv2.INTER_AREA)
    hash_img = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
    dhash = 0
    for bit in (hash_img[:, 1:] > hash_img[:, :-1]).flat:
        dhash = (dhash << 1) | int(bit)
    return {
        "sharpness": round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 6),
        "brightness": round(float(gray.mean()), 6),
        "dark_fraction": round(float((gray < 12).mean()), 6),
        "bright_fraction": round(float((gray > 243).mean()), 6),
        "dhash": f"{dhash:016x}", "analysis_width": gray.shape[1],
        "analysis_height": gray.shape[0],
    }, tiny


def decide(metrics: dict, tiny: np.ndarray, previous: dict | None,
           timestamp: float, args) -> tuple[bool, list[str], str, float | str]:
    flags = []
    if metrics["brightness"] < 3 and metrics["dark_fraction"] >= .99:
        flags.append("black_frame")
    if metrics["brightness"] > 252 and metrics["bright_fraction"] >= .99:
        flags.append("white_frame")
    if metrics["sharpness"] < args.blur_threshold:
        flags.append("blur_candidate")
    if metrics["brightness"] < 35:
        flags.append("dark_candidate")
    if metrics["brightness"] > 220:
        flags.append("bright_candidate")
    duplicate_of, mad = "", ""
    if previous is not None and not {"black_frame", "white_frame"}.intersection(flags):
        distance = (int(metrics["dhash"], 16) ^ previous["hash"]).bit_count()
        mad = round(float(np.abs(tiny.astype(float) - previous["tiny"].astype(float)).mean()), 6)
        if distance <= args.duplicate_hamming and mad <= args.duplicate_mad:
            duplicate_of = previous["id"]
            flags.append("near_duplicate")
            if timestamp - previous["timestamp"] >= args.max_keep_gap - 1e-7:
                flags.append("coverage_anchor")
    hard_bad = bool({"black_frame", "white_frame"}.intersection(flags))
    repeated = "near_duplicate" in flags and "coverage_anchor" not in flags
    return not (hard_bad or repeated), flags, duplicate_of, mad


def split_rows(rows: list[dict], val_ratio: float) -> tuple[list[dict], list[dict]]:
    kept = [row for row in rows if row["selected"]]
    if not kept:
        raise ValueError("没有可保留的图像；请检查视频或人工复核表。")
    count = min(len(kept) - 1, max(1, math.floor(len(kept) * val_ratio + .5))) if len(kept) >= 3 else 0
    # Ordered, deterministic midpoint sampling. No random leakage between lists.
    indices = {min(len(kept) - 1, math.floor((i + .5) * len(kept) / count))
               for i in range(count)}
    for row in rows:
        row["split"] = "excluded"
    for i, row in enumerate(kept):
        row["split"] = "val" if i in indices else "train"
    return [r for r in kept if r["split"] == "train"], [r for r in kept if r["split"] == "val"]


def font(size: int):
    for name in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if Path(name).exists():
            return ImageFont.truetype(name, size)
    return ImageFont.load_default(size=size)


def sheet(rows: list[dict], path: Path, root: Path, title: str, columns=4, thumb=(240, 280)) -> None:
    cell_w, image_h = thumb
    cell_h = image_h + 76
    canvas = Image.new("RGB", (columns * cell_w, 64 + math.ceil(len(rows) / columns) * cell_h), "#edf1f5")
    draw = ImageDraw.Draw(canvas)
    draw.text((12, 16), title, font=font(21), fill="#172638")
    for i, row in enumerate(rows):
        x, y = (i % columns) * cell_w, 64 + (i // columns) * cell_h
        with Image.open(root / row["candidate_path"]) as im:
            tile = ImageOps.contain(im.convert("RGB"), (cell_w - 14, image_h - 10))
        canvas.paste(tile, (x + (cell_w - tile.width) // 2, y + (image_h - tile.height) // 2))
        status = "排除" if not row["selected"] else ("检验" if row["split"] == "val" else "训练")
        color = "#b12632" if not row["selected"] else "#155b83"
        draw.text((x + 8, y + image_h), f'{row["sample_id"]}  {row["timestamp_seconds"]:.2f}s', font=font(14), fill="#172638")
        draw.text((x + 8, y + image_h + 23), f'{status}  清晰度 {row["sharpness"]:.1f}', font=font(14), fill=color)
        note = " / ".join(FLAGS_ZH.get(f, f) for f in row["flags"].split(";") if f)
        draw.text((x + 8, y + image_h + 46), note[:17] or "常规帧", font=font(13), fill="#555555")
    canvas.save(path, quality=90)


def build_report(root: Path, rows: list[dict], summary: dict) -> None:
    previews = root / "previews"
    previews.mkdir()
    sheet(rows, previews / "overview.jpg", root, "全部候选帧与最终划分", 6, (180, 235))
    for offset in range(0, len(rows), 12):
        sheet(rows[offset:offset + 12], previews / f"contact_{offset // 12 + 1:03d}.jpg",
              root, f"候选帧复核 {offset + 1}—{min(offset + 12, len(rows))}", 3, (320, 385))
    usable = [r for r in rows if r["selected"]]
    examples = [max(usable, key=lambda r: r["sharpness"]),
                min((r for r in rows if "black_frame" not in r["flags"]), key=lambda r: r["sharpness"])]
    rejected = [r for r in rows if "black_frame" in r["flags"]]
    if rejected:
        examples.append(rejected[0])
    sheet(examples, previews / "quality_examples.jpg", root, "清晰帧、模糊候选与黑场示例", len(examples), (320, 385))
    cards = []
    for row in rows:
        status = "排除" if not row["selected"] else ("检验集" if row["split"] == "val" else "训练集")
        notes = "；".join(FLAGS_ZH.get(f, f) for f in row["flags"].split(";") if f) or "无质量警示"
        cards.append(f'''<article class="{'excluded' if not row['selected'] else ''}">
<a href="{row['candidate_path']}"><img loading="lazy" src="{row['candidate_path']}" alt="{row['sample_id']}"></a>
<b>{row['sample_id']} · {row['timestamp_seconds']:.3f} 秒 · {status}</b>
<p>原帧 {row['source_frame_index']} · 清晰度 {row['sharpness']:.2f} · 亮度 {row['brightness']:.2f}</p>
<p>{html.escape(notes)}</p><p>{html.escape(row['review_comment'])}</p></article>''')
    counts = summary["counts"]
    content = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>视频预处理实验结果</title>
<style>body{{font:16px/1.6 system-ui,sans-serif;background:#edf1f5;color:#172638;margin:25px auto;padding:0 20px;max-width:1400px}}
h1{{font-size:28px}}.stats{{padding:18px;background:white;border-radius:10px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}}
article{{background:white;border-radius:8px;padding:12px}}article.excluded{{border:2px solid #b12632}}img{{width:100%;height:300px;object-fit:contain;background:#e3e7ec}}p{{margin:8px 0}}a{{color:#155b83}}b{{display:block}}</style>
<h1>视频预处理实验结果</h1><div class="stats">
<p>原素材：{html.escape(summary['source']['file_name'])} · {summary['source']['decoded_frames']} 帧 · {summary['source']['duration_seconds']:.3f} 秒</p>
<p><b>{counts['candidates']} 张候选 → {counts['selected']} 张保留 → {counts['train']} 张训练 / {counts['val']} 张检验；排除 {counts['excluded']} 张。</b></p>
<p>每秒 {summary['parameters']['sample_fps']} 帧，并额外保留最后一帧用于片尾检查。质量评分在最长边不超过 640 像素的灰度图上计算；原图不美化、不去模糊。</p>
<p>模糊和曝光警示默认保留供复核；黑白场及高度重复帧默认排除。显式复核决定：{counts['manual_decisions']} 条。</p>
<p>时间覆盖检查仅用于定位缺口，不代表多视角几何验证通过。检验帧来自同一视频，与训练帧相关，只能用于流程自检。</p>
<p><a href="previews/overview.jpg">全部图像总览</a> · <a href="frames.csv">逐帧评分和来源</a> · <a href="review.csv">人工复核表</a> · <a href="summary.json">完整统计</a></p></div>
<h2>全部候选帧 点击查看原尺寸图像</h2><div class="grid">{''.join(cards)}</div></html>'''
    (root / "report.html").write_text(content, encoding="utf-8")


def validate(args) -> None:
    if not args.input.is_file():
        raise ValueError(f"找不到输入视频：{args.input}")
    if args.output.exists():
        raise ValueError(f"输出目录已存在，换一个新目录以保护已有结果：{args.output}")
    if not math.isfinite(args.sample_fps) or args.sample_fps <= 0:
        raise ValueError("--sample-fps 必须是大于零的有限数")
    if not 0 < args.val_ratio < 1:
        raise ValueError("--val-ratio 必须在 0 与 1 之间")
    if not math.isfinite(args.max_keep_gap) or args.max_keep_gap <= 0:
        raise ValueError("--max-keep-gap 必须大于零")
    if not math.isfinite(args.blur_threshold) or args.blur_threshold < 0:
        raise ValueError("--blur-threshold 必须非负")
    if not 0 <= args.duplicate_hamming <= 64 or not math.isfinite(args.duplicate_mad) or args.duplicate_mad < 0:
        raise ValueError("重复判定阈值无效")
    if not 1 <= args.jpeg_quality <= 100:
        raise ValueError("JPEG 质量必须在 1—100 之间")


def run(args, progress=None) -> dict:
    def notify(value, message):
        if progress:
            progress(value, message)

    notify(0, "检查视频和处理参数")
    args.input = args.input.resolve()
    args.output = args.output.resolve()
    validate(args)
    source_hash = sha256(args.input)
    notify(2, "已记录原视频指纹，开始解码")
    review = load_review(args.review_file, source_hash)
    cap = cv2.VideoCapture(str(args.input))
    if not cap.isOpened():
        raise ValueError("无法解码输入视频；请检查格式或编码")
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    expected_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if not math.isfinite(fps) or fps <= 0:
        cap.release()
        raise ValueError("视频未提供有效帧率，无法建立可靠时间戳")
    if args.sample_fps > fps:
        cap.release()
        raise ValueError(f"抽帧率 {args.sample_fps} 超过原视频帧率 {fps}，请降低参数")
    root = args.output
    root.mkdir(parents=True)
    for folder in ("candidates", "images", "splits"):
        (root / folder).mkdir()
    write_json(root / "run_state.json", {"status": "running", "program_version": VERSION})
    rows, previous = [], None
    next_target, index, last_time = 0.0, 0, -1.0
    fallback_count = 0
    last_frame, last_info = None, None
    dimensions = set()

    def accept(frame, frame_index, timestamp, timestamp_source, reported_ms, terminal=False):
        nonlocal previous
        sample_id = f"v001_{len(rows) + 1:06d}"
        name = f"{sample_id}.jpg"
        metrics, tiny = quality(frame)
        auto_keep, flags, duplicate_of, mad = decide(metrics, tiny, previous, timestamp, args)
        decision = review.get(sample_id, {"decision": "auto", "comment": ""})
        if sample_id in review and (decision["frame"] != frame_index
                                    or not math.isclose(decision["time"], timestamp, abs_tol=1e-5)
                                    or not math.isclose(decision["fps"], args.sample_fps, abs_tol=1e-9)):
            raise ValueError(f"复核表与本次抽帧参数、帧号或时间戳不匹配：{sample_id}")
        selected = {"keep": True, "drop": False}.get(decision["decision"], auto_keep)
        ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, args.jpeg_quality])
        if not ok:
            raise ValueError(f"图像编码失败：{sample_id}")
        candidate = root / "candidates" / name
        encoded.tofile(str(candidate))  # Unicode paths also work on Windows.
        row = {
            "sample_id": sample_id, "source_file": args.input.name,
            "source_sha256": source_hash, "source_frame_index": frame_index,
            "timestamp_seconds": round(timestamp, 6), "timestamp_source": timestamp_source,
            "reported_timestamp_ms": round(reported_ms, 6) if math.isfinite(reported_ms) else "",
            "terminal_sample": terminal, "width": frame.shape[1], "height": frame.shape[0],
            **metrics, "flags": ";".join(flags), "duplicate_of": duplicate_of,
            "difference_to_previous_kept": mad, "auto_selected": auto_keep,
            "review_decision": decision["decision"], "review_comment": decision["comment"],
            "selected": selected, "split": "", "candidate_path": f"candidates/{name}",
            "selected_path": f"images/{name}" if selected else "",
            "image_sha256": sha256(candidate),
        }
        rows.append(row)
        if selected:
            previous = {"id": sample_id, "hash": int(metrics["dhash"], 16),
                        "tiny": tiny, "timestamp": timestamp}

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            raw_ms = float(cap.get(cv2.CAP_PROP_POS_MSEC))
            timestamp = raw_ms / 1000
            stamp_source = "container_pos_msec"
            if not math.isfinite(timestamp) or timestamp < 0 or (index > 0 and timestamp <= last_time):
                timestamp = max(index / fps, last_time + 1 / fps)
                stamp_source = "fps_fallback"
                fallback_count += 1
            dimensions.add((frame.shape[1], frame.shape[0]))
            if len(dimensions) > 1:
                raise ValueError("视频帧尺寸发生变化；请先拆分成同设备/同尺寸片段")
            if timestamp + 1e-7 >= next_target:
                accept(frame, index, timestamp, stamp_source, raw_ms)
                next_target = (math.floor((timestamp + 1e-7) * args.sample_fps) + 1) / args.sample_fps
            last_frame, last_info = frame, (index, timestamp, stamp_source, raw_ms)
            last_time = timestamp
            index += 1
            if index % 10 == 0:
                notify(min(79, 3 + 76 * index / max(expected_frames, index)),
                       f"已解码 {index} 帧，抽取 {len(rows)} 张候选图")
        cap.release()
        if index == 0:
            raise ValueError("输入视频没有可解码帧")
        if expected_frames > 0 and index != expected_frames:
            raise ValueError(f"视频可能损坏或未完整解码：声明 {expected_frames} 帧，实际 {index} 帧")
        if rows[-1]["source_frame_index"] != last_info[0]:
            accept(last_frame, *last_info, terminal=True)
        unknown = set(review) - {r["sample_id"] for r in rows}
        if unknown:
            raise ValueError("复核表包含本次抽帧不存在的 ID：" + ", ".join(sorted(unknown)))
        train, val = split_rows(rows, args.val_ratio)
        notify(81, "保存筛选图像和固定划分")
        for row in rows:
            if row["selected"]:
                shutil.copyfile(root / row["candidate_path"], root / row["selected_path"])
        for label, subset in (("train", train), ("val", val), ("all", [r for r in rows if r["selected"]])):
            (root / "splits" / f"{label}.txt").write_text("".join(Path(r["selected_path"]).name + "\n" for r in subset), encoding="utf-8")
        for label, subset in (("train", train), ("val", val)):
            write_json(root / "splits" / f"{label}.json", [
                {k: r[k] for k in ("sample_id", "selected_path", "source_frame_index", "timestamp_seconds", "source_sha256")}
                for r in subset])
        write_csv(root / "frames.csv", rows)
        write_csv(root / "review.csv", [
            {"sample_id": r["sample_id"], "source_sha256": source_hash,
             "source_frame_index": r["source_frame_index"], "timestamp_seconds": r["timestamp_seconds"],
             "sampling_fps": args.sample_fps,
             "decision": r["review_decision"], "comment": r["review_comment"]} for r in rows])
        parameters = {k: v for k, v in vars(args).items() if k not in {"input", "output", "review_file"}}
        write_json(root / "config.json", parameters)
        source = {
            "file_name": args.input.name, "absolute_path": str(args.input),
            "sha256": source_hash, "size_bytes": args.input.stat().st_size,
            "fps": fps, "declared_frames": expected_frames, "decoded_frames": index,
            "duration_seconds": round(last_time + 1 / fps, 6),
            "dimensions": [list(x) for x in sorted(dimensions)],
            "timestamp_fallback_frames": fallback_count,
            "camera_device": args.capture_device, "lens_and_focal_length": args.lens,
            "location": args.location, "description": args.source_description,
        }
        write_json(root / "source_manifest.json", source)
        selected = [r for r in rows if r["selected"]]
        gaps = [{"from_id": a["sample_id"], "to_id": b["sample_id"],
                 "seconds": round(b["timestamp_seconds"] - a["timestamp_seconds"], 6)}
                for a, b in zip(selected, selected[1:])]
        summary = {
            "program_version": VERSION,
            "program_sha256": sha256(Path(__file__).with_suffix(".py") if Path(__file__).with_suffix(".py").exists()
                                     else Path(sys.executable)),
            "environment": {"python": sys.version.split()[0], "opencv": cv2.__version__,
                            "numpy": np.__version__, "pillow": Image.__version__},
            "parameters": parameters, "source": source,
            "review_file_sha256": sha256(args.review_file) if args.review_file else None,
            "counts": {"candidates": len(rows), "selected": len(selected),
                       "excluded": len(rows) - len(selected), "train": len(train), "val": len(val),
                       "manual_decisions": sum(r["review_decision"] != "auto" for r in rows)},
            "flag_counts": {flag: sum(flag in r["flags"].split(";") for r in rows) for flag in FLAGS_ZH},
            "temporal_coverage": {"first_kept_seconds": selected[0]["timestamp_seconds"],
                                  "last_kept_seconds": selected[-1]["timestamp_seconds"],
                                  "max_gap_seconds": max((g["seconds"] for g in gaps), default=0),
                                  "gaps_above_limit": [g for g in gaps if g["seconds"] > args.max_keep_gap + 1e-6]},
            "evaluation_note": "同视频时间均匀留出，仅用于流程检查；不证明新视角泛化或 COLMAP 重建成功。",
        }
        write_json(root / "summary.json", summary)
        notify(87, "生成图像总览和复核报告")
        build_report(root, rows, summary)
        write_json(root / "run_state.json", {"status": "complete", "program_version": VERSION})
        notify(100, "处理完成")
        return summary
    except Exception as exc:
        cap.release()
        write_json(root / "run_state.json", {"status": "failed", "error": str(exc)})
        raise


def parser():
    p = argparse.ArgumentParser(description="视频抽帧、质量初筛、人工复核、来源追溯与训练/检验划分")
    p.add_argument("--input", type=Path, required=True, help="输入视频，不修改原文件")
    p.add_argument("--output", type=Path, required=True, help="新的输出目录；拒绝覆盖")
    p.add_argument("--sample-fps", type=float, default=2.0, help="每秒抽取帧数，默认 2")
    p.add_argument("--blur-threshold", type=float, default=50.0, help="清晰度警示阈值，不自动删除模糊帧")
    p.add_argument("--duplicate-hamming", type=int, default=2)
    p.add_argument("--duplicate-mad", type=float, default=2.0)
    p.add_argument("--max-keep-gap", type=float, default=2.0, help="重复片段连接候选保留间隔及时间缺口警示阈值")
    p.add_argument("--val-ratio", type=float, default=.1, help="检验集比例；不足 3 张时不划检验集")
    p.add_argument("--jpeg-quality", type=int, default=95)
    p.add_argument("--review-file", type=Path, help="含 auto/keep/drop 的人工复核 CSV，必须与抽帧参数对应")
    p.add_argument("--capture-device", default="unknown", help="采集设备；未知时不推测")
    p.add_argument("--lens", default="unknown", help="镜头与焦段记录")
    p.add_argument("--location", default="未提供", help="拍摄位置记录")
    p.add_argument("--source-description", default="未提供", help="素材用途和来源说明")
    return p


def main() -> int:
    args = parser().parse_args()
    try:
        summary = run(args)
        print(json.dumps({"output": str(args.output), "counts": summary["counts"],
                          "temporal_coverage": summary["temporal_coverage"]}, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, cv2.error) as exc:
        print(f"处理失败：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
