"""Compare two image directories and report PSNR / SSIM per image plus aggregates.

Pure numpy implementation: no scipy or scikit-image required. Intended for checking
3DGS eval renders against undistorted reference frames, and for proving that a
lightweight model did not damage content.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
SSIM_KERNEL = 11
SSIM_SIGMA = 1.5
SSIM_K1 = 0.01
SSIM_K2 = 0.03


def gaussian_kernel(size: int, sigma: float) -> np.ndarray:
    """Return a normalized 1D gaussian kernel."""
    coords = np.arange(size, dtype=np.float64) - (size - 1) / 2.0
    kernel = np.exp(-(coords ** 2) / (2.0 * sigma ** 2))
    return kernel / kernel.sum()


def _pad_channel(a: np.ndarray, pad: int, axis: int) -> np.ndarray:
    """Pad along one axis, falling back to edge mode when the image is smaller than the kernel."""
    widths = [(0, 0), (0, 0)]
    widths[axis] = (pad, pad)
    mode = "reflect" if a.shape[axis] > pad else "edge"
    return np.pad(a, widths, mode=mode)


def filter_channel(channel: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Separable gaussian filter on a single 2D channel."""
    pad = len(kernel) // 2
    rows = _pad_channel(channel, pad, 0)
    vertical = np.zeros_like(channel)
    for i, weight in enumerate(kernel):
        vertical += weight * rows[i:i + channel.shape[0], :]
    cols = _pad_channel(vertical, pad, 1)
    horizontal = np.zeros_like(vertical)
    for i, weight in enumerate(kernel):
        horizontal += weight * cols[:, i:i + vertical.shape[1]]
    return horizontal


def psnr(reference: np.ndarray, test: np.ndarray, peak: float = 1.0) -> float:
    """Peak signal-to-noise ratio; returns inf for identical inputs."""
    mse = float(np.mean((reference - test) ** 2))
    if mse <= 0.0:
        return float("inf")
    return float(10.0 * np.log10((peak ** 2) / mse))


def ssim_channel(reference: np.ndarray, test: np.ndarray, peak: float = 1.0) -> float:
    """Structural similarity for one channel using the standard gaussian window."""
    kernel = gaussian_kernel(SSIM_KERNEL, SSIM_SIGMA)
    mu_ref = filter_channel(reference, kernel)
    mu_test = filter_channel(test, kernel)
    mu_ref_sq = mu_ref ** 2
    mu_test_sq = mu_test ** 2
    mu_cross = mu_ref * mu_test
    var_ref = filter_channel(reference ** 2, kernel) - mu_ref_sq
    var_test = filter_channel(test ** 2, kernel) - mu_test_sq
    cov = filter_channel(reference * test, kernel) - mu_cross
    c1 = (SSIM_K1 * peak) ** 2
    c2 = (SSIM_K2 * peak) ** 2
    numerator = (2.0 * mu_cross + c1) * (2.0 * cov + c2)
    denominator = (mu_ref_sq + mu_test_sq + c1) * (var_ref + var_test + c2)
    return float(np.mean(numerator / np.maximum(denominator, 1e-12)))


def load_image(path: Path, gray: bool) -> np.ndarray:
    """Load an image as float64 in [0, 1] with shape (H, W, C) or (H, W)."""
    with Image.open(path) as handle:
        image = handle.convert("L" if gray else "RGB")
        return np.asarray(image, dtype=np.float64) / 255.0


def collect(directory: Path, recursive: bool) -> dict[str, list[Path]]:
    """Group image files by relative path without suffix.

    Brush writes eval renders as .png while the reference frames are .jpg, so pairing
    must ignore the suffix; a key maps to a list because a directory may hold both.
    """
    pattern = "**/*" if recursive else "*"
    grouped: dict[str, list[Path]] = {}
    for path in directory.glob(pattern):
        if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        key = path.relative_to(directory).with_suffix("").as_posix()
        grouped.setdefault(key, []).append(path)
    for paths in grouped.values():
        paths.sort()
    return grouped


def pair_files(reference_files: dict[str, list[Path]],
               test_files: dict[str, list[Path]]) -> tuple[list[tuple[str, Path, Path]], list[str], list[str], str]:
    """Pair images by stem, preferring identical suffixes when a stem is ambiguous."""
    shared = sorted(set(reference_files) & set(test_files))
    pairs: list[tuple[str, Path, Path]] = []
    ambiguous: list[str] = []
    for key in shared:
        refs = reference_files[key]
        tests = test_files[key]
        if len(refs) == 1 and len(tests) == 1:
            pairs.append((key, refs[0], tests[0]))
            continue
        matched = False
        for ref in refs:
            for test in tests:
                if ref.suffix.lower() == test.suffix.lower():
                    pairs.append((f"{key}{ref.suffix}", ref, test))
                    matched = True
                    break
            if matched:
                break
        if not matched:
            ambiguous.append(key)
    missing_in_test = sorted(set(reference_files) - set(test_files))
    missing_in_reference = sorted(set(test_files) - set(reference_files))
    return pairs, missing_in_test, missing_in_reference, ambiguous


def match_ratio(reference: np.ndarray, test: np.ndarray, resize: str) -> tuple[np.ndarray, np.ndarray]:
    """Align shapes when eval renders and reference frames differ in size."""
    if reference.shape == test.shape:
        return reference, test
    if resize == "error":
        raise ValueError(
            f"尺寸不一致：参考 {reference.shape[1]}x{reference.shape[0]}，"
            f"对比 {test.shape[1]}x{test.shape[0]}；可用 --resize test 或 --resize reference 统一")
    target = test if resize == "test" else reference
    height, width = target.shape[:2]

    def to_image(array: np.ndarray) -> Image.Image:
        data = np.clip(array * 255.0, 0.0, 255.0)
        mode = "L" if array.ndim == 2 else "RGB"
        return Image.fromarray(data.astype(np.uint8), mode=mode)

    if resize == "test":
        reference = np.asarray(to_image(reference).resize((width, height), Image.BICUBIC),
                               dtype=np.float64) / 255.0
    else:
        test = np.asarray(to_image(test).resize((width, height), Image.BICUBIC),
                          dtype=np.float64) / 255.0
    return reference, test


def evaluate(args: argparse.Namespace) -> int:
    reference_dir = args.reference.resolve()
    test_dir = args.test.resolve()
    for directory in (reference_dir, test_dir):
        if not directory.is_dir():
            raise ValueError(f"目录不存在：{directory}")

    reference_files = collect(reference_dir, args.recursive)
    test_files = collect(test_dir, args.recursive)
    pairs, missing_in_test, missing_in_reference, ambiguous = pair_files(reference_files, test_files)
    if not pairs:
        raise ValueError("两个目录没有同名图像可比对，请检查文件名或加 --recursive")

    rows = []
    skipped_shape: list[dict] = []
    for name, reference_path, test_path in pairs:
        reference = load_image(reference_path, args.gray)
        test = load_image(test_path, args.gray)
        if reference.shape != test.shape and args.resize == "error":
            skipped_shape.append({
                "image": name,
                "reference_hw": [int(reference.shape[0]), int(reference.shape[1])],
                "test_hw": [int(test.shape[0]), int(test.shape[1])],
            })
            continue
        reference, test = match_ratio(reference, test, args.resize)
        if args.gray:
            ssim_value = ssim_channel(reference, test)
        else:
            ssim_value = float(np.mean([
                ssim_channel(reference[:, :, c], test[:, :, c]) for c in range(reference.shape[2])
            ]))
        rows.append({
            "image": name,
            "reference_file": reference_path.name,
            "test_file": test_path.name,
            "psnr": psnr(reference, test),
            "ssim": ssim_value,
            "mae": float(np.mean(np.abs(reference - test))),
        })

    if not rows:
        raise ValueError(
            f"{len(skipped_shape)} 组图像尺寸全部不一致，无法评估；"
            "请改用 --resize test 或 --resize reference")

    psnr_values = np.array([r["psnr"] for r in rows if np.isfinite(r["psnr"])], dtype=np.float64)
    ssim_values = np.array([r["ssim"] for r in rows], dtype=np.float64)
    aggregate = {
        "matched": len(rows),
        "paired_by": "stem（忽略 png/jpg 后缀差异）",
        "ambiguous_stems": ambiguous,
        "skipped_shape_mismatch": skipped_shape,
        "resize_policy": args.resize,
        "missing_in_test": missing_in_test,
        "missing_in_reference": missing_in_reference,
        "identical_images": int(len(rows) - len(psnr_values)),
        "psnr_mean": round(float(psnr_values.mean()), 4) if len(psnr_values) else None,
        "psnr_min": round(float(psnr_values.min()), 4) if len(psnr_values) else None,
        "psnr_max": round(float(psnr_values.max()), 4) if len(psnr_values) else None,
        "ssim_mean": round(float(ssim_values.mean()), 6),
        "ssim_min": round(float(ssim_values.min()), 6),
        "ssim_max": round(float(ssim_values.max()), 6),
        "ssim_std": round(float(ssim_values.std()), 6),
    }

    rows.sort(key=lambda r: r["ssim"])
    report = {
        "reference_dir": str(reference_dir),
        "test_dir": str(test_dir),
        "color_mode": "gray" if args.gray else "rgb",
        "aggregate": aggregate,
        "worst_images": [
            {**r, "psnr": None if not np.isfinite(r["psnr"]) else round(r["psnr"], 4),
             "ssim": round(r["ssim"], 6), "mae": round(r["mae"], 6)}
            for r in rows[: args.top]
        ],
    }

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        payload = {**report, "all_images": [
            {**r, "psnr": None if not np.isfinite(r["psnr"]) else round(r["psnr"], 4),
             "ssim": round(r["ssim"], 6), "mae": round(r["mae"], 6)} for r in rows]}
        args.json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="对比两组图像的 PSNR / SSIM，用于重建与轻量化前后评估")
    p.add_argument("reference", type=Path, help="参考图像目录（例如 undistorted/images）")
    p.add_argument("test", type=Path, help="待评估图像目录（例如 eval_10000 渲染结果）")
    p.add_argument("--recursive", action="store_true", help="递归子目录并按相对路径配对")
    p.add_argument("--gray", action="store_true", help="转灰度后比较，仅评估结构")
    p.add_argument("--resize", choices=("error", "test", "reference"), default="error",
                   help="尺寸不一致时的处理：error 跳过该图并在报告中列出、test 对齐到参考、reference 对齐到待评估")
    p.add_argument("--top", type=int, default=5, help="列出 SSIM 最差的 N 张，默认 5")
    p.add_argument("--json-out", type=Path, help="可选：保存完整结果 JSON（含逐图数值）")
    args = p.parse_args()

    try:
        return evaluate(args)
    except (ValueError, OSError) as exc:
        print(f"评估失败：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
