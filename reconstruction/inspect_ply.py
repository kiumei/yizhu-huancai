"""Inspect 3DGS binary PLY / .splat files and optionally convert PLY to standard .splat."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np


PLY_DTYPES = {
    "char": "i1", "int8": "i1",
    "uchar": "u1", "uint8": "u1",
    "short": "<i2", "int16": "i2",
    "ushort": "<u2", "uint16": "u2",
    "int": "<i4", "int32": "<i4",
    "uint": "<u4", "uint32": "<u4",
    "float": "<f4", "float32": "<f4",
    "double": "<f8", "float64": "<f8",
}
SH_C0 = 0.28209479177387814


def read_ply_vertices(path: Path) -> tuple[list[tuple[str, str]], np.ndarray]:
    """Read a binary_little_endian 3DGS PLY vertex table into a structured numpy array."""
    with path.open("rb") as f:
        header_lines: list[str] = []
        while True:
            raw = f.readline()
            if not raw:
                raise ValueError(f"PLY 文件缺少 end_header：{path}")
            line = raw.decode("ascii", errors="strict").rstrip("\r\n")
            header_lines.append(line)
            if line == "end_header":
                break
        if not header_lines or header_lines[0] != "ply":
            raise ValueError(f"不是有效的 PLY 文件：{path}")

        fmt = None
        vertex_count = None
        in_vertex = False
        properties: list[tuple[str, str]] = []
        for line in header_lines[1:-1]:
            parts = line.split()
            if not parts:
                continue
            if parts[0] == "format":
                fmt = parts[1]
            elif parts[0] == "element":
                in_vertex = parts[1] == "vertex"
                if in_vertex:
                    vertex_count = int(parts[2])
            elif parts[0] == "property" and in_vertex:
                if parts[1] == "list":
                    raise ValueError(f"暂不支持 list 属性：{line}")
                properties.append((parts[2], parts[1]))

        if fmt != "binary_little_endian":
            raise ValueError(f"仅支持 binary_little_endian PLY，当前为：{fmt}")
        if vertex_count is None or not properties:
            raise ValueError(f"PLY 缺少 vertex 定义：{path}")

        dtype = np.dtype([(name, PLY_DTYPES[ptype]) for name, ptype in properties])
        data = np.fromfile(f, dtype=dtype, count=vertex_count)
        if len(data) != vertex_count:
            raise ValueError(f"PLY 顶点数量不足：声明 {vertex_count}，实际 {len(data)}")
    return properties, data


def inspect_ply(path: Path) -> dict:
    """Summarize geometry, Gaussian attributes, and sanity checks for a 3DGS PLY file."""
    properties, data = read_ply_vertices(path)
    names = [n for n, _ in properties]
    xyz = np.column_stack([data["x"], data["y"], data["z"]]).astype(np.float64)
    finite_mask = np.isfinite(xyz).all(axis=1)
    sh_rest_count = sum(1 for n in names if n.startswith("f_rest_"))
    sh_degree = round(math.sqrt(sh_rest_count / 3 + 1) - 1) if sh_rest_count > 0 else 0

    valid_xyz = xyz[finite_mask]
    p05 = np.percentile(valid_xyz, 5, axis=0) if len(valid_xyz) else np.zeros(3)
    p50 = np.percentile(valid_xyz, 50, axis=0) if len(valid_xyz) else np.zeros(3)
    p95 = np.percentile(valid_xyz, 95, axis=0) if len(valid_xyz) else np.zeros(3)

    summary = {
        "file": str(path),
        "format": "3dgs_ply_binary_little_endian",
        "size_bytes": path.stat().st_size,
        "splat_count": int(len(data)),
        "property_count": len(names),
        "properties": names,
        "sh_degree_inferred": sh_degree,
        "non_finite_xyz_count": int((~finite_mask).sum()),
        "bbox_min": [round(float(v), 6) for v in valid_xyz.min(axis=0)] if len(valid_xyz) else None,
        "bbox_max": [round(float(v), 6) for v in valid_xyz.max(axis=0)] if len(valid_xyz) else None,
        "percentile_05": [round(float(v), 6) for v in p05],
        "median_center": [round(float(v), 6) for v in p50],
        "percentile_95": [round(float(v), 6) for v in p95],
    }

    if "opacity" in names:
        opac_raw = data["opacity"].astype(np.float64)
        opac_sig = 1.0 / (1.0 + np.exp(-np.clip(opac_raw, -60.0, 60.0)))
        summary["opacity_sigmoid_stats"] = {
            "min": round(float(opac_sig.min()), 6),
            "median": round(float(np.median(opac_sig)), 6),
            "max": round(float(opac_sig.max()), 6),
        }
    if all(k in names for k in ("scale_0", "scale_1", "scale_2")):
        scales = np.exp(np.column_stack([data["scale_0"], data["scale_1"], data["scale_2"]]).astype(np.float64))
        summary["scale_exp_median"] = [round(float(v), 6) for v in np.median(scales, axis=0)]
    return summary


def convert_ply_to_splat(ply_path: Path, splat_path: Path) -> dict:
    """Convert standard 3DGS binary PLY to antimatter15 32-byte-per-splat .splat format."""
    properties, data = read_ply_vertices(ply_path)
    names = {n for n, _ in properties}
    required = {"x", "y", "z", "scale_0", "scale_1", "scale_2", "opacity", "f_dc_0", "f_dc_1", "f_dc_2",
                "rot_0", "rot_1", "rot_2", "rot_3"}
    missing = sorted(required - names)
    if missing:
        raise ValueError(f"PLY 缺少标准 3DGS 属性，无法导出 .splat：{', '.join(missing)}")

    scales = np.exp(np.column_stack([data["scale_0"], data["scale_1"], data["scale_2"]]).astype(np.float32))
    volume = scales[:, 0] * scales[:, 1] * scales[:, 2]
    opacity = 1.0 / (1.0 + np.exp(-np.clip(data["opacity"].astype(np.float32), -60.0, 60.0)))
    # Sort descending by importance (size * opacity), standard for progressive .splat viewers.
    order = np.argsort(-(volume * opacity))
    sorted_data = data[order]

    n = len(sorted_data)
    out = np.empty(n, dtype=[
        ("pos", "<f4", 3),
        ("scale", "<f4", 3),
        ("rgba", "u1", 4),
        ("rot", "u1", 4),
    ])
    out["pos"] = np.column_stack([sorted_data["x"], sorted_data["y"], sorted_data["z"]]).astype(np.float32)
    out["scale"] = np.exp(np.column_stack([
        sorted_data["scale_0"], sorted_data["scale_1"], sorted_data["scale_2"]
    ]).astype(np.float32))

    fdc = np.column_stack([sorted_data["f_dc_0"], sorted_data["f_dc_1"], sorted_data["f_dc_2"]]).astype(np.float32)
    rgb = np.clip((0.5 + SH_C0 * fdc) * 255.0, 0.0, 255.0)
    alpha = np.clip((1.0 / (1.0 + np.exp(-np.clip(sorted_data["opacity"].astype(np.float32), -60.0, 60.0)))) * 255.0,
                    0.0, 255.0)
    out["rgba"][:, :3] = np.rint(rgb).astype(np.uint8)
    out["rgba"][:, 3] = np.rint(alpha).astype(np.uint8)

    rot = np.column_stack([
        sorted_data["rot_0"], sorted_data["rot_1"], sorted_data["rot_2"], sorted_data["rot_3"]
    ]).astype(np.float32)
    norms = np.linalg.norm(rot, axis=1, keepdims=True)
    rot = np.divide(rot, np.maximum(norms, 1e-12))
    out["rot"] = np.clip(np.rint(rot * 128.0 + 128.0), 0.0, 255.0).astype(np.uint8)

    splat_path.parent.mkdir(parents=True, exist_ok=True)
    out.tofile(str(splat_path))
    return {
        "source_ply": str(ply_path),
        "output_splat": str(splat_path),
        "splat_count": int(n),
        "size_bytes": int(splat_path.stat().st_size),
        "note": "Sorted descending by exp(scale) volume * sigmoid(opacity); point order differs from source PLY.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="检查标准 3DGS PLY 属性并可选转换为 .splat")
    p.add_argument("ply", type=Path, help="输入的 3DGS .ply 文件")
    p.add_argument("--to-splat", type=Path, help="可选输出标准 32 字节 .splat 文件路径")
    p.add_argument("--json-out", type=Path, help="可选保存检查结果 JSON")
    args = p.parse_args()

    try:
        report = inspect_ply(args.ply.resolve())
        if args.to_splat is not None:
            report["splat_export"] = convert_ply_to_splat(args.ply.resolve(), args.to_splat.resolve())
        if args.json_out is not None:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError) as exc:
        print(f"检查失败：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
