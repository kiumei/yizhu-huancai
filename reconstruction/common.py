"""Shared helpers for COLMAP / Brush 3DGS reconstruction scripts."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Iterable


DEFAULT_COLMAP_CANDIDATES = (
    Path(r"C:\tools\colmap\bin\colmap.exe"),
    Path(r"C:\Program Files\COLMAP\bin\colmap.exe"),
)
DEFAULT_BRUSH_CANDIDATES = (
    Path(r"C:\tools\brush\brush_app.exe"),
    Path(r"C:\tools\brush\brush.exe"),
)


def find_executable(
    explicit: Path | None,
    env_name: str,
    path_names: Iterable[str],
    fallbacks: Iterable[Path],
    label: str,
) -> Path:
    """Locate a required external executable without hardcoding user-specific paths."""
    if explicit is not None:
        resolved = explicit.expanduser().resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"找不到指定的 {label} 可执行文件：{resolved}")
        return resolved

    env_value = os.environ.get(env_name, "").strip()
    if env_value:
        candidate = Path(env_value).expanduser().resolve()
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(f"环境变量 {env_name} 指向的文件不存在：{candidate}")

    for name in path_names:
        found = shutil.which(name)
        if found:
            return Path(found).resolve()

    for candidate in fallbacks:
        if candidate.is_file():
            return candidate.resolve()

    raise FileNotFoundError(
        f"未找到 {label}；请添加到 PATH、设置环境变量 {env_name} 或通过命令行参数传入路径。"
    )


def colmap_env(colmap_bin: Path) -> dict[str, str]:
    """Prepare PATH and QT_PLUGIN_PATH so portable Windows COLMAP binaries run reliably."""
    env = os.environ.copy()
    bin_dir = colmap_bin.parent
    root_dir = bin_dir.parent
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    plugins_dir = root_dir / "plugins"
    if plugins_dir.is_dir():
        existing = env.get("QT_PLUGIN_PATH", "")
        env["QT_PLUGIN_PATH"] = f"{plugins_dir}{os.pathsep}{existing}" if existing else str(plugins_dir)
    return env


def run_logged(
    cmd: list[str],
    log_handle,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> None:
    """Run a subprocess, streaming output to both console and a log file."""
    cmd_line = subprocess.list2cmdline([str(x) for x in cmd])
    header = f"\n$ {cmd_line}\n"
    print(header, end="", flush=True)
    log_handle.write(header)
    log_handle.flush()

    proc = subprocess.Popen(
        [str(x) for x in cmd],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=str(cwd) if cwd else None,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        print(line, end="", flush=True)
        log_handle.write(line)
    code = proc.wait()
    log_handle.flush()
    if code != 0:
        raise RuntimeError(f"命令执行失败（退出码 {code}）：{cmd_line}")


def write_json(path: Path, payload: object) -> None:
    """Write formatted UTF-8 JSON with trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_colmap_txt_model(sparse_txt_dir: Path) -> dict:
    """Parse COLMAP TXT sparse model files into summary metrics and image lists."""
    cameras_file = sparse_txt_dir / "cameras.txt"
    images_file = sparse_txt_dir / "images.txt"
    points_file = sparse_txt_dir / "points3D.txt"

    cameras = []
    if cameras_file.is_file():
        for raw in cameras_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            cameras.append({
                "camera_id": int(parts[0]),
                "model": parts[1],
                "width": int(parts[2]),
                "height": int(parts[3]),
                "params": [float(x) for x in parts[4:]],
            })

    registered_images: list[str] = []
    if images_file.is_file():
        lines = [
            raw.strip()
            for raw in images_file.read_text(encoding="utf-8", errors="replace").splitlines()
            if raw.strip() and not raw.lstrip().startswith("#")
        ]
        # COLMAP images.txt stores two lines per registered image: pose line, then 2D points line.
        for pose_line in lines[0::2]:
            parts = pose_line.split(maxsplit=9)
            if len(parts) >= 10:
                registered_images.append(parts[9])

    point_count = 0
    errors: list[float] = []
    track_lengths: list[int] = []
    if points_file.is_file():
        for raw in points_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 8:
                point_count += 1
                errors.append(float(parts[7]))
                track_lengths.append((len(parts) - 8) // 2)

    return {
        "cameras": cameras,
        "registered_count": len(registered_images),
        "registered_images": sorted(registered_images),
        "points3d_count": point_count,
        "mean_reprojection_error": round(sum(errors) / len(errors), 6) if errors else None,
        "mean_track_length": round(sum(track_lengths) / len(track_lengths), 4) if track_lengths else None,
    }
