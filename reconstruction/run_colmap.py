"""Run COLMAP sparse reconstruction and undistortion for 3DGS training."""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import shutil
import sys
import time

from common import (
    DEFAULT_COLMAP_CANDIDATES,
    colmap_env,
    find_executable,
    parse_colmap_txt_model,
    run_logged,
    write_json,
)


def collect_images(images_dir: Path, image_list: Path | None) -> list[str]:
    """Return sorted relative image filenames to process."""
    if not images_dir.is_dir():
        raise ValueError(f"找不到图像目录：{images_dir}")
    if image_list is not None:
        names = [line.strip() for line in image_list.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not names:
            raise ValueError(f"图像列表为空：{image_list}")
        for name in names:
            if not (images_dir / name).is_file():
                raise ValueError(f"图像列表中的文件不存在：{images_dir / name}")
        return names

    exts = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
    names = sorted(
        p.relative_to(images_dir).as_posix()
        for p in images_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in exts
    )
    if not names:
        raise ValueError(f"图像目录中没有支持的图像文件：{images_dir}")
    return names


def run_pipeline(args) -> dict:
    colmap_bin = find_executable(
        args.colmap_bin, "COLMAP_BIN", ("colmap", "colmap.exe"), DEFAULT_COLMAP_CANDIDATES, "COLMAP"
    )
    images_dir = args.images.resolve()
    output_dir = args.output.resolve()
    image_list = args.image_list.resolve() if args.image_list else None
    input_names = collect_images(images_dir, image_list)

    if output_dir.exists() and any(output_dir.iterdir()):
        if not args.overwrite:
            raise ValueError(f"输出目录已存在且非空，请换新目录或显式传入 --overwrite：{output_dir}")
        shutil.rmtree(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    sparse_dir = output_dir / "sparse"
    sparse_dir.mkdir()
    database_path = output_dir / "database.db"
    effective_list_path = output_dir / "input_images.txt"
    effective_list_path.write_text("\n".join(input_names) + "\n", encoding="utf-8")

    env = colmap_env(colmap_bin)
    log_path = output_dir / "colmap.log"
    started = time.perf_counter()

    with log_path.open("w", encoding="utf-8") as log_file:
        extract_cmd = [
            str(colmap_bin), "feature_extractor",
            "--database_path", str(database_path),
            "--image_path", str(images_dir),
            "--image_list_path", str(effective_list_path),
            "--ImageReader.camera_model", args.camera_model,
            "--ImageReader.single_camera", "1" if args.single_camera else "0",
            "--FeatureExtraction.use_gpu", "0" if args.cpu else "1",
        ]
        if args.max_image_size > 0:
            extract_cmd.extend(["--FeatureExtraction.max_image_size", str(args.max_image_size)])
        run_logged(extract_cmd, log_file, env=env)

        if args.matcher == "sequential":
            match_cmd = [
                str(colmap_bin), "sequential_matcher",
                "--database_path", str(database_path),
                "--FeatureMatching.use_gpu", "0" if args.cpu else "1",
                "--SequentialMatching.overlap", str(args.overlap),
                "--SequentialMatching.quadratic_overlap", "1",
            ]
        else:
            match_cmd = [
                str(colmap_bin), "exhaustive_matcher",
                "--database_path", str(database_path),
                "--FeatureMatching.use_gpu", "0" if args.cpu else "1",
            ]
        run_logged(match_cmd, log_file, env=env)

        mapper_cmd = [
            str(colmap_bin),
            "global_mapper" if args.mapper == "global" else "mapper",
            "--database_path", str(database_path),
            "--image_path", str(images_dir),
            "--output_path", str(sparse_dir),
        ]
        run_logged(mapper_cmd, log_file, env=env)

        submodels = sorted((p for p in sparse_dir.iterdir() if p.is_dir()), key=lambda p: p.name)
        if not submodels:
            raise RuntimeError("COLMAP mapper 未能成功建图（sparse 目录为空）。")

        submodel_summaries: list[dict] = []
        for sub in submodels:
            txt_dir = output_dir / "sparse_txt" / sub.name
            txt_dir.mkdir(parents=True, exist_ok=True)
            run_logged([
                str(colmap_bin), "model_converter",
                "--input_path", str(sub),
                "--output_path", str(txt_dir),
                "--output_type", "TXT",
            ], log_file, env=env)
            run_logged([
                str(colmap_bin), "model_analyzer",
                "--path", str(sub),
            ], log_file, env=env)
            stats = parse_colmap_txt_model(txt_dir)
            stats["submodel"] = sub.name
            submodel_summaries.append(stats)

        best = max(submodel_summaries, key=lambda item: item["registered_count"])
        best_sparse_dir = sparse_dir / best["submodel"]

        undistorted_dir = None
        if not args.skip_undistort:
            undistorted_dir = output_dir / "undistorted"
            undistort_cmd = [
                str(colmap_bin), "image_undistorter",
                "--image_path", str(images_dir),
                "--input_path", str(best_sparse_dir),
                "--output_path", str(undistorted_dir),
                "--output_type", "COLMAP",
                "--image_list_path", str(effective_list_path),
            ]
            if args.max_image_size > 0:
                undistort_cmd.extend(["--max_image_size", str(args.max_image_size)])
            run_logged(undistort_cmd, log_file, env=env)

    registered_set = set(best["registered_images"])
    unregistered = [name for name in input_names if name not in registered_set]
    report = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "colmap_bin": str(colmap_bin),
        "images_dir": str(images_dir),
        "image_list": str(image_list) if image_list else None,
        "output_dir": str(output_dir),
        "undistorted_dir": str(undistorted_dir) if undistorted_dir else None,
        "parameters": {
            "camera_model": args.camera_model,
            "single_camera": args.single_camera,
            "matcher": args.matcher,
            "mapper": args.mapper,
            "overlap": args.overlap if args.matcher == "sequential" else None,
            "max_image_size": args.max_image_size,
            "use_gpu": not args.cpu,
        },
        "input_image_count": len(input_names),
        "submodel_count": len(submodel_summaries),
        "primary_submodel": best["submodel"],
        "registered_count": best["registered_count"],
        "registration_rate": round(best["registered_count"] / len(input_names), 4),
        "unregistered_images": unregistered,
        "points3d_count": best["points3d_count"],
        "mean_reprojection_error": best["mean_reprojection_error"],
        "mean_track_length": best["mean_track_length"],
        "cameras": best["cameras"],
        "all_submodels": [
            {k: v for k, v in item.items() if k != "registered_images"}
            for item in submodel_summaries
        ],
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "log_file": str(log_path),
    }
    write_json(output_dir / "sfm_report.json", report)
    return report


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="运行 COLMAP 位姿解算、稀疏重建与去畸变整理")
    p.add_argument("--images", type=Path, required=True, help="输入图像目录")
    p.add_argument("--output", type=Path, required=True, help="COLMAP 工作输出目录")
    p.add_argument("--image-list", type=Path, help="可选图像列表（如 splits/train.txt），每行一个文件名")
    p.add_argument("--camera-model", default="SIMPLE_RADIAL", help="COLMAP 相机模型，默认 SIMPLE_RADIAL")
    p.add_argument("--multi-camera", dest="single_camera", action="store_false", help="不强制共享单相机内参")
    p.set_defaults(single_camera=True)
    p.add_argument("--matcher", choices=("sequential", "exhaustive"), default="sequential", help="特征匹配策略")
    p.add_argument("--mapper", choices=("incremental", "global"), default="incremental", help="位姿建图器：incremental 或 global")
    p.add_argument("--overlap", type=int, default=10, help="顺序匹配重叠窗口")
    p.add_argument("--max-image-size", type=int, default=-1, help="限制最大边分辨率；-1 表示保持原图")
    p.add_argument("--cpu", action="store_true", help="禁用 GPU（默认启用 CUDA）")
    p.add_argument("--skip-undistort", action="store_true", help="仅做稀疏解算，不做去畸变输出")
    p.add_argument("--overwrite", action="store_true", help="覆盖非空输出目录")
    p.add_argument("--colmap-bin", type=Path, help="显式指定 colmap.exe 路径")
    return p


def main() -> int:
    args = build_parser().parse_args()
    try:
        report = run_pipeline(args)
        summary = {
            "output_dir": report["output_dir"],
            "undistorted_dir": report["undistorted_dir"],
            "submodel_count": report["submodel_count"],
            "registered": f"{report['registered_count']}/{report['input_image_count']}",
            "points3d_count": report["points3d_count"],
            "mean_reprojection_error": report["mean_reprojection_error"],
            "elapsed_seconds": report["elapsed_seconds"],
        }
        print(summary)
        return 0
    except (ValueError, FileNotFoundError, RuntimeError, OSError) as exc:
        print(f"COLMAP 执行失败：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
