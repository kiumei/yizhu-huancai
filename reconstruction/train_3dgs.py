"""Train a 3D Gaussian Splatting model with Brush from a COLMAP dataset."""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import shutil
import sys
import time

from common import DEFAULT_BRUSH_CANDIDATES, find_executable, run_logged, write_json
from inspect_ply import convert_ply_to_splat, inspect_ply


def validate_colmap_dataset(dataset_dir: Path) -> None:
    """Verify the input directory contains COLMAP images and sparse reconstruction."""
    if not (dataset_dir / "images").is_dir():
        raise ValueError(f"输入数据集缺少 images 目录：{dataset_dir}")
    sparse_dir = dataset_dir / "sparse"
    if not sparse_dir.is_dir():
        raise ValueError(f"输入数据集缺少 sparse 目录：{dataset_dir}")


def run_training(args) -> dict:
    brush_bin = find_executable(
        args.brush_bin, "BRUSH_BIN", ("brush_app", "brush_app.exe", "brush"), DEFAULT_BRUSH_CANDIDATES, "Brush"
    )
    dataset_dir = args.dataset.resolve()
    validate_colmap_dataset(dataset_dir)
    output_dir = args.output.resolve()

    if output_dir.exists() and any(output_dir.iterdir()):
        if not args.overwrite:
            raise ValueError(f"输出目录已存在且非空，请换新目录或显式传入 --overwrite：{output_dir}")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    export_every = args.export_every if args.export_every is not None else args.total_steps
    eval_every = args.eval_every if args.eval_every is not None else args.total_steps

    cmd = [
        str(brush_bin),
        str(dataset_dir),
        "--total-steps", str(args.total_steps),
        "--max-resolution", str(args.max_resolution),
        "--max-splats", str(args.max_splats),
        "--sh-degree", str(args.sh_degree),
        "--seed", str(args.seed),
        "--export-every", str(export_every),
        "--export-path", str(output_dir),
        "--export-name", args.export_name,
        "--eval-every", str(eval_every),
    ]
    if args.eval_split_every:
        cmd.extend(["--eval-split-every", str(args.eval_split_every)])
    if args.eval_save_to_disk:
        cmd.append("--eval-save-to-disk")
    if args.with_viewer:
        cmd.append("--with-viewer")

    log_path = output_dir / "train.log"
    started = time.perf_counter()
    with log_path.open("w", encoding="utf-8") as log_file:
        run_logged(cmd, log_file, cwd=output_dir)

    final_name = args.export_name.replace("{iter}", str(args.total_steps))
    final_ply = output_dir / final_name
    if not final_ply.is_file():
        ply_files = sorted(output_dir.glob("*.ply"), key=lambda p: p.stat().st_mtime)
        if not ply_files:
            raise RuntimeError(f"训练结束但未在 {output_dir} 找到导出的 .ply 模型")
        final_ply = ply_files[-1]

    ply_stats = inspect_ply(final_ply)
    splat_info = None
    if args.export_splat:
        splat_path = final_ply.with_suffix(".splat")
        splat_info = convert_ply_to_splat(final_ply, splat_path)

    report = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "brush_bin": str(brush_bin),
        "dataset_dir": str(dataset_dir),
        "output_dir": str(output_dir),
        "parameters": {
            "total_steps": args.total_steps,
            "max_resolution": args.max_resolution,
            "max_splats": args.max_splats,
            "sh_degree": args.sh_degree,
            "seed": args.seed,
            "eval_split_every": args.eval_split_every,
            "eval_save_to_disk": args.eval_save_to_disk,
        },
        "final_ply": str(final_ply),
        "ply_inspection": ply_stats,
        "splat_export": splat_info,
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "log_file": str(log_path),
    }
    write_json(output_dir / "train_report.json", report)
    return report


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="使用 Brush 训练 3D Gaussian Splatting 模型并检查输出")
    p.add_argument("--dataset", type=Path, required=True, help="含 images/ 与 sparse/ 的 COLMAP 数据集目录")
    p.add_argument("--output", type=Path, required=True, help="训练输出目录")
    p.add_argument("--total-steps", type=int, default=15000, help="训练步数，默认 15000")
    p.add_argument("--max-resolution", type=int, default=1600, help="训练图像最大边分辨率，默认 1600")
    p.add_argument("--max-splats", type=int, default=2000000, help="最大高斯点数上限，默认 2000000")
    p.add_argument("--sh-degree", type=int, default=3, help="球谐阶数，默认 3")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--export-every", type=int, help="导出周期，默认等于 total-steps")
    p.add_argument("--export-name", default="model_{iter}.ply", help="导出 PLY 文件名模板")
    p.add_argument("--eval-split-every", type=int, help="可选：每 N 张划出 1 张作训练期评测视角")
    p.add_argument("--eval-every", type=int, help="评测周期，默认等于 total-steps")
    p.add_argument("--eval-save-to-disk", action="store_true", help="将评测对比图保存到输出目录")
    p.add_argument("--export-splat", action="store_true", help="额外导出标准 32 字节 .splat 文件")
    p.add_argument("--with-viewer", action="store_true", help="训练时同时打开 Brush 桌面窗口")
    p.add_argument("--overwrite", action="store_true", help="覆盖非空输出目录")
    p.add_argument("--brush-bin", type=Path, help="显式指定 brush_app.exe 路径")
    return p


def main() -> int:
    args = build_parser().parse_args()
    try:
        report = run_training(args)
        print({
            "final_ply": report["final_ply"],
            "splat_count": report["ply_inspection"]["splat_count"],
            "non_finite_xyz": report["ply_inspection"]["non_finite_xyz_count"],
            "elapsed_seconds": report["elapsed_seconds"],
        })
        return 0
    except (ValueError, FileNotFoundError, RuntimeError, OSError) as exc:
        print(f"3DGS 训练失败：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
