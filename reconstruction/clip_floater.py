"""Prune floater Gaussians from a 3DGS binary PLY and report what was removed.

Thresholds are always expressed in human-readable units: opacity as a probability
0..1 and scale as a linear sigma, even though the PLY stores logit and log values.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np

from inspect_ply import PLY_DTYPES, read_ply_vertices


REQUIRED_XYZ = ("x", "y", "z")
SCALE_KEYS = ("scale_0", "scale_1", "scale_2")


def sigmoid_raw_to_prob(raw: np.ndarray) -> np.ndarray:
    """Convert stored logit opacity to probability, matching the renderer's activation."""
    return 1.0 / (1.0 + np.exp(-np.clip(raw.astype(np.float64), -60.0, 60.0)))


def write_ply_vertices(path: Path, properties: list[tuple[str, str]], data: np.ndarray) -> None:
    """Write a binary_little_endian PLY vertex table with the original property order."""
    header = ["ply", "format binary_little_endian 1.0", f"element vertex {len(data)}"]
    header += [f"property {ptype} {name}" for name, ptype in properties]
    header.append("end_header")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.write(("\n".join(header) + "\n").encode("ascii"))
        np.ascontiguousarray(data).tofile(f)


def percentile_bbox(xyz: np.ndarray, low: float, high: float) -> tuple[np.ndarray, np.ndarray]:
    """Return an axis-aligned box spanning the given percentiles of valid points."""
    return np.percentile(xyz, low, axis=0), np.percentile(xyz, high, axis=0)


def summarize_axis(xyz: np.ndarray) -> dict | None:
    """Describe point spread with percentiles so floter removal can be judged."""
    if len(xyz) == 0:
        return None
    p05, p50, p95 = (np.percentile(xyz, q, axis=0) for q in (5, 50, 95))
    return {
        "bbox_min": [round(float(v), 4) for v in xyz.min(axis=0)],
        "bbox_max": [round(float(v), 4) for v in xyz.max(axis=0)],
        "percentile_05": [round(float(v), 4) for v in p05],
        "median": [round(float(v), 4) for v in p50],
        "percentile_95": [round(float(v), 4) for v in p95],
    }


def prune(args: argparse.Namespace) -> int:
    source = args.ply.resolve()
    properties, data = read_ply_vertices(source)
    names = [n for n, _ in properties]
    missing_xyz = [k for k in REQUIRED_XYZ if k not in names]
    if missing_xyz:
        raise ValueError(f"PLY 缺少坐标属性：{', '.join(missing_xyz)}")

    total = len(data)
    xyz = np.column_stack([data["x"], data["y"], data["z"]]).astype(np.float64)
    alive = np.ones(total, dtype=bool)
    removed_by_reason: dict[str, int] = {}

    def drop(reason: str, mask: np.ndarray) -> None:
        """Apply a removal stage, counting only points still alive at this stage."""
        nonlocal alive
        hit = alive & mask
        count = int(hit.sum())
        if count:
            removed_by_reason[reason] = count
        alive = alive & ~mask

    # Non-finite coordinates break rendering unconditionally; no flag to keep them.
    non_finite = ~np.isfinite(xyz).all(axis=1)
    drop("non_finite_xyz", non_finite)

    bbox_min = bbox_max = None
    if args.bbox is not None:
        bbox_min = np.array(args.bbox[:3], dtype=np.float64)
        bbox_max = np.array(args.bbox[3:], dtype=np.float64)
        if np.any(bbox_max <= bbox_min):
            raise ValueError("--bbox 的 max 分量必须大于 min 分量")
    elif args.bbox_percentile is not None:
        valid = xyz[np.isfinite(xyz).all(axis=1)]
        if len(valid):
            bbox_min, bbox_max = percentile_bbox(valid, args.bbox_percentile[0], args.bbox_percentile[1])
    if bbox_min is not None:
        outside = np.any((xyz < bbox_min) | (xyz > bbox_max), axis=1)
        drop("outside_bbox", outside)

    has_opacity = "opacity" in names
    if args.min_opacity > 0.0:
        if not has_opacity:
            raise ValueError("PLY 缺少 opacity 属性，无法按不透明度裁剪")
        prob = sigmoid_raw_to_prob(data["opacity"])
        drop("below_min_opacity", prob < args.min_opacity)

    has_scale = all(k in names for k in SCALE_KEYS)
    if args.min_scale > 0.0 or args.max_scale > 0.0:
        if not has_scale:
            raise ValueError("PLY 缺少 scale_0..2 属性，无法按尺度裁剪")
        scale_linear = np.exp(np.column_stack([data[k] for k in SCALE_KEYS]).astype(np.float64))
        largest = scale_linear.max(axis=1)
        if args.min_scale > 0.0:
            drop("below_min_scale", largest < args.min_scale)
        if args.max_scale > 0.0:
            drop("above_max_scale", largest > args.max_scale)

    if args.bbox is None and args.bbox_percentile is None and args.min_opacity <= 0.0 \
            and args.min_scale <= 0.0 and args.max_scale <= 0.0:
        raise ValueError("至少需要提供一个裁剪条件（--bbox / --bbox-percentile / --min-opacity / --min-scale）")

    kept_data = data[alive]
    keep_indices = np.flatnonzero(alive).astype(np.int64)

    before_bytes = source.stat().st_size
    report: dict = {
        "input": str(source),
        "thresholds": {
            "bbox": None if bbox_min is None else {
                "min": [round(float(v), 4) for v in bbox_min],
                "max": [round(float(v), 4) for v in bbox_max],
                "source": "explicit" if args.bbox is not None else "percentile",
            },
            "min_opacity_probability": args.min_opacity,
            "min_scale_linear": args.min_scale,
            "max_scale_linear": args.max_scale,
        },
        "counts": {
            "input": total,
            "kept": int(len(kept_data)),
            "removed_total": int(total - len(kept_data)),
            "removed_by_reason": removed_by_reason,
        },
        "kept_ratio": round(float(len(kept_data)) / total, 6) if total else None,
        "size_bytes": {
            "ply_before": int(before_bytes),
            "splat32_before_estimate": int(total * 32),
        },
        "spatial_before": summarize_axis(xyz[np.isfinite(xyz).all(axis=1)]),
        "spatial_after": summarize_axis(np.column_stack(
            [kept_data["x"], kept_data["y"], kept_data["z"]]).astype(np.float64)) if len(kept_data) else None,
        "removed_spatial": summarize_axis(xyz[~alive]) if (~alive).any() else None,
    }

    if has_opacity:
        for label, mask in (("before", np.ones(total, dtype=bool)), ("after", alive)):
            prob = sigmoid_raw_to_prob(data["opacity"][mask])
            if len(prob):
                report[f"opacity_probability_{label}"] = {
                    "min": round(float(prob.min()), 6),
                    "median": round(float(np.median(prob)), 6),
                    "max": round(float(prob.max()), 6),
                }
    if has_scale:
        scale_linear = np.exp(np.column_stack([data[k] for k in SCALE_KEYS]).astype(np.float64))
        largest = scale_linear.max(axis=1)
        if alive.any():
            report["scale_linear_after"] = {
                "min_largest_axis": round(float(largest[alive].min()), 6),
                "median_largest_axis": round(float(np.median(largest[alive])), 6),
                "max_largest_axis": round(float(largest[alive].max()), 6),
            }

    if args.dry_run:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    destination = args.output.resolve()
    write_ply_vertices(destination, properties, kept_data)
    report["output"] = str(destination)
    report["size_bytes"]["ply_after"] = int(destination.stat().st_size)
    report["size_bytes"]["ply_saved_ratio"] = round(
        1.0 - report["size_bytes"]["ply_after"] / before_bytes, 6) if before_bytes else None

    # Splat order is re-sorted by importance, so it is recorded separately from keep_indices.
    splat_order = np.array([], dtype=np.int64)
    if all(k in names for k in (*SCALE_KEYS, "opacity")):
        scale_kept = np.exp(np.column_stack([kept_data[k] for k in SCALE_KEYS]).astype(np.float64))
        volume = scale_kept.prod(axis=1)
        importance = volume * sigmoid_raw_to_prob(kept_data["opacity"])
        splat_order = np.argsort(-importance).astype(np.int64)

    if args.to_splat is not None:
        from inspect_ply import convert_ply_to_splat
        report["splat_export"] = convert_ply_to_splat(destination, args.to_splat.resolve())
        report["size_bytes"]["splat_after"] = int(args.to_splat.resolve().stat().st_size)

    if args.index_map is not None:
        index_path = args.index_map.resolve()
        index_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            index_path,
            keep_indices=keep_indices,
            splat_order=splat_order,
            property_names=np.array([n for n, _ in properties]),
        )
        report["index_map"] = {
            "path": str(index_path),
            "keep_indices": "keep_indices[k] = 原 PLY 行号，对应裁剪后第 k 行",
            "splat_order": "splat_order[k] = 裁剪后第 k 行在 .splat 中的位置来源",
            "note": ".splat 按体积累积不透明度降序重排，与 PLY 行序不同，二者都需保留。",
        }

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="按包围盒、不透明度与尺度裁剪 3DGS PLY 中的漂浮高斯，并输出可对比的裁剪报告")
    p.add_argument("ply", type=Path, help="输入的 3DGS .ply 文件")
    p.add_argument("--output", type=Path, required=True, help="裁剪后的 .ply 输出路径")
    p.add_argument("--bbox", nargs=6, type=float, metavar=("XMIN", "YMIN", "ZMIN", "XMAX", "YMAX", "ZMAX"),
                   help="显式包围盒，保留盒内的点")
    p.add_argument("--bbox-percentile", nargs=2, type=float, metavar=("LOW", "HIGH"),
                   help="按坐标百分位自动取包围盒，例如 1 99；只能剔除少量外围散点，"
                        "漂浮点占比较高时会被一起统计进去，此时应改用 --bbox 显式给范围")
    p.add_argument("--min-opacity", type=float, default=0.0,
                   help="最小不透明度概率（0..1），低于该值的点被删除；PLY 内为 logit，内部自动换算")
    p.add_argument("--min-scale", type=float, default=0.0,
                   help="最小线性尺度（最大轴，线性 sigma），小于该值的碎点被删除")
    p.add_argument("--max-scale", type=float, default=0.0,
                   help="最大线性尺度（最大轴），大于该值的异常大高斯被删除；0 表示不限制")
    p.add_argument("--to-splat", type=Path, help="可选：同时导出标准 32 字节 .splat")
    p.add_argument("--index-map", type=Path, help="可选：保存 .npz 点序映射（keep_indices / splat_order）")
    p.add_argument("--json-out", type=Path, help="可选：保存裁剪报告 JSON")
    p.add_argument("--dry-run", action="store_true", help="只统计不落盘，用于先看阈值效果")
    args = p.parse_args()

    try:
        return prune(args)
    except (ValueError, OSError) as exc:
        print(f"裁剪失败：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
