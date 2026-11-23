"""Inspect 32-byte .splat files and compare base vs stylized Gaussian models."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np


SPLAT_DTYPE = np.dtype([
    ("pos", "<f4", 3),
    ("scale", "<f4", 3),
    ("rgba", "u1", 4),
    ("rot", "u1", 4),
])


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_splat(path: Path) -> np.ndarray:
    size = path.stat().st_size
    if size == 0 or size % 32 != 0:
        raise ValueError(f"不是标准的 32 字节/点 .splat 文件（大小 {size} 字节）：{path}")
    return np.fromfile(path, dtype=SPLAT_DTYPE)


def summarize_splat(path: Path) -> dict:
    arr = load_splat(path)
    pos = arr["pos"].astype(np.float64)
    scale = arr["scale"].astype(np.float64)
    rgba = arr["rgba"]
    rot = (arr["rot"].astype(np.float64) - 128.0) / 128.0
    rot_norms = np.linalg.norm(rot, axis=1)
    finite_mask = np.isfinite(pos).all(axis=1) & np.isfinite(scale).all(axis=1)
    valid_pos = pos[finite_mask]

    return {
        "file": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": file_sha256(path),
        "splat_count": int(len(arr)),
        "non_finite_count": int((~finite_mask).sum()),
        "bbox_min": [round(float(x), 6) for x in valid_pos.min(axis=0)] if len(valid_pos) else None,
        "bbox_max": [round(float(x), 6) for x in valid_pos.max(axis=0)] if len(valid_pos) else None,
        "percentile_05": [round(float(x), 6) for x in np.percentile(valid_pos, 5, axis=0)] if len(valid_pos) else None,
        "median_center": [round(float(x), 6) for x in np.percentile(valid_pos, 50, axis=0)] if len(valid_pos) else None,
        "percentile_95": [round(float(x), 6) for x in np.percentile(valid_pos, 95, axis=0)] if len(valid_pos) else None,
        "scale_median": [round(float(x), 6) for x in np.median(scale, axis=0)],
        "alpha_stats": {
            "min": int(rgba[:, 3].min()),
            "median": float(np.median(rgba[:, 3])),
            "max": int(rgba[:, 3].max()),
        },
        "rgb_mean": [round(float(x), 2) for x in rgba[:, :3].mean(axis=0)],
        "rot_norm_mean": round(float(rot_norms.mean()), 6),
    }


def compare_splats(base_path: Path, styled_path: Path) -> dict:
    a = load_splat(base_path)
    b = load_splat(styled_path)

    index_map: dict[bytes, list[int]] = {}
    for idx, row in enumerate(a["pos"]):
        index_map.setdefault(row.tobytes(), []).append(idx)

    matched_indices: list[int] = []
    unmatched_in_styled = 0
    for row in b["pos"]:
        hits = index_map.get(row.tobytes())
        if hits:
            matched_indices.append(hits.pop(0))
        else:
            unmatched_in_styled += 1

    order_preserved = all(x < y for x, y in zip(matched_indices, matched_indices[1:])) if matched_indices else False
    comparison: dict = {
        "base_count": int(len(a)),
        "styled_count": int(len(b)),
        "point_count_delta": int(len(b) - len(a)),
        "matched_by_exact_pos": int(len(matched_indices)),
        "unmatched_in_styled": int(unmatched_in_styled),
        "relative_order_preserved": bool(order_preserved),
    }

    if len(matched_indices) == len(b) and len(b) > 0:
        a_sub = a[matched_indices]
        rot_diff = np.abs(a_sub["rot"].astype(np.int32) - b["rot"].astype(np.int32))
        rgb_diff = np.abs(a_sub["rgba"][:, :3].astype(np.int32) - b["rgba"][:, :3].astype(np.int32))
        dropped_mask = np.ones(len(a), dtype=bool)
        dropped_mask[matched_indices] = False
        dropped = a[dropped_mask]

        comparison.update({
            "scale_bitwise_identical": bool(np.array_equal(a_sub["scale"], b["scale"])),
            "alpha_bitwise_identical": bool(np.array_equal(a_sub["rgba"][:, 3], b["rgba"][:, 3])),
            "rgb_bitwise_identical": bool(np.array_equal(a_sub["rgba"][:, :3], b["rgba"][:, :3])),
            "rgb_mean_abs_byte_diff": [round(float(x), 2) for x in rgb_diff.mean(axis=0)],
            "rot_bitwise_identical": bool(np.array_equal(a_sub["rot"], b["rot"])),
            "rot_max_abs_byte_diff": int(rot_diff.max()),
            "rot_identical_fraction": round(float((rot_diff == 0).all(axis=1).mean()), 6),
            "dropped_from_base": {
                "count": int(len(dropped)),
                "alpha_min": int(dropped["rgba"][:, 3].min()) if len(dropped) else None,
                "alpha_median": float(np.median(dropped["rgba"][:, 3])) if len(dropped) else None,
                "alpha_max": int(dropped["rgba"][:, 3].max()) if len(dropped) else None,
            },
        })
    return comparison


def main() -> int:
    p = argparse.ArgumentParser(description="检查标准 .splat 模型属性并对比风格化前后变化")
    p.add_argument("base", type=Path, help="基准或待检 .splat 文件")
    p.add_argument("--styled", type=Path, help="可选：风格化后的 .splat 文件，用于逐点比对")
    p.add_argument("--json-out", type=Path, help="可选：将检查报告写入 JSON")
    args = p.parse_args()

    try:
        base_path = args.base.resolve()
        report: dict = {"base": summarize_splat(base_path)}
        if args.styled is not None:
            styled_path = args.styled.resolve()
            report["styled"] = summarize_splat(styled_path)
            report["comparison"] = compare_splats(base_path, styled_path)
        if args.json_out is not None:
            out = args.json_out.resolve()
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError) as exc:
        print(f"检查失败：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
