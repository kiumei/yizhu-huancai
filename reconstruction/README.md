# 位姿解算与写实重建

负责人：李金华。

本目录维护从预处理图像到 COLMAP 位姿解算、去畸变整理、3DGS 写实模型训练及格式检查的可重复脚本。

## 工具链与环境配置

为避免本机缺少 Visual Studio / `nvcc` 编译环境导致 CUDA 算子构建受阻，本模块统一采用预编译工具链 + Python 调度脚本：

| 组件 | 版本与来源 | 安装路径 / 发现方式 | 用途 |
| --- | --- | --- | --- |
| Python 环境 | 仓库 `.venv`（`Python 3.12.9`） | 仅依赖 `numpy>=1.24,<3` | 脚本调度、`TXT` 解析与 `.ply`/`.splat` 检查转换 |
| COLMAP | `4.2.1`（Commit `bd1fcf6`，CUDA 版）<br>[colmap/colmap releases](https://github.com/colmap/colmap/releases/tag/4.2.1) | `C:\tools\colmap\bin\colmap.exe`（或设 `COLMAP_BIN` / 加入 `PATH`） | SIFT 特征提取、匹配、SfM 位姿解算与去畸变 |
| Brush | `v0.3.0`（Windows x64 预编译版）<br>[ArthurBrussee/brush releases](https://github.com/ArthurBrussee/brush/releases/tag/v0.3.0) | `C:\tools\brush\brush_app.exe`（或设 `BRUSH_BIN` / 加入 `PATH`） | 基于 WebGPU/Vulkan 后端的 3DGS 训练与 `.ply` 导出 |

- 已验证 GPU：`NVIDIA GeForce RTX 4060 Laptop GPU`（8188 MiB 显存，驱动 `617.14` / CUDA `13.4`）。
- 若在其他成员机器运行且工具安装位置不同，可通过环境变量 `COLMAP_BIN`、`BRUSH_BIN` 或命令行 `--colmap-bin`、`--brush-bin` 指定。

### 依赖安装

在仓库根目录（沿用 `.venv`）执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r reconstruction/requirements.txt
```

## 目录脚本说明

- `common.py`：外部工具路径发现、COLMAP 运行环境（`PATH`/`QT_PLUGIN_PATH`）设置、日志同步写入与 COLMAP `TXT` 模型指标解析。
- `run_colmap.py`：执行 `feature_extractor` → `sequential_matcher`/`exhaustive_matcher` → `mapper`/`global_mapper` → `model_converter` → `model_analyzer` → `image_undistorter`，输出 `sfm_report.json` 与 `colmap.log`。
- `train_3dgs.py`：调用 Brush 训练去畸变数据集，输出标准 `binary_little_endian` `.ply` 模型、`train_report.json`，并支持可选转换 32 字节 `.splat`。
- `inspect_ply.py`：检查 `.ply` 顶点数、属性列表、推断球谐阶数、包围盒、`NaN/Inf` 异常，并可导出标准 `.splat`。

## 运行命令

### 1. COLMAP 位姿解算与去畸变

针对环绕闭环或小规模图像集，建议使用 `--matcher exhaustive --mapper global`（实测可避免增量建图在转角缺口处分裂）：

```powershell
.\.venv\Scripts\python.exe reconstruction/run_colmap.py `
  --images data/processed/capture01_v1/images `
  --image-list data/processed/capture01_v1/splits/train.txt `
  --output outputs/reconstruction/capture01_v1_colmap `
  --matcher exhaustive `
  --mapper global `
  --camera-model SIMPLE_RADIAL `
  --overwrite
```

### 2. 3DGS 写实模型训练

```powershell
.\.venv\Scripts\python.exe reconstruction/train_3dgs.py `
  --dataset outputs/reconstruction/capture01_v1_colmap/undistorted `
  --output outputs/reconstruction/capture01_v1_3dgs `
  --total-steps 10000 `
  --max-resolution 1600 `
  --eval-split-every 10 `
  --eval-save-to-disk `
  --export-splat `
  --overwrite
```

### 3. 模型格式检查与 `.splat` 转换

```powershell
.\.venv\Scripts\python.exe reconstruction/inspect_ply.py outputs/reconstruction/capture01_v1_3dgs/model_10000.ply --to-splat outputs/reconstruction/capture01_v1_3dgs/model_10000.splat
```

## 格式区分与交接说明

- **COLMAP 稀疏点云**：位于 `sparse/0/`（`BIN`）与 `sparse_txt/0/`（`cameras.txt`、`images.txt`、`points3D.txt`），仅为相机位姿与稀疏三角化特征点，不可直接作为高斯泼溅模型渲染。
- **3DGS 写实模型（`.ply`）**：`binary_little_endian` 格式，含 `59` 个属性（`x,y,z`、`f_dc_0..2`、`f_rest_0..44` 共 3 阶球谐、`opacity`、`scale_0..2`、`rot_0..3`），用于后续风格化或渲染。
- **网页轻量格式（`.splat`）**：标准 32 字节/高斯（位置 `3f32`、线性尺度 `3f32`、RGBA `4u8`、归一化四元数 `4u8`），按体积极大到极小降序排列；转换会改变点顺序，供第一阶段网页查看器快速加载。

## 公开示例环境验证记录（`south-building`）

- 数据来源：COLMAP 官方示例数据集 [south-building.zip](https://github.com/colmap/colmap/releases/download/3.11.1/south-building.zip) 前 24 张图像（`P1180141.JPG`–`P1180164.JPG`，本地存放于 `data/public/south-building/`）。
- **COLMAP 验证结果**（`run_colmap.py --matcher sequential --max-image-size 1200`）：
  - 注册率：`24/24`（`100%`，1 个连通子模型）
  - 稀疏点云：`7,098` 点，平均重投影误差 `0.528 px`，耗时 `10.59s`
  - 日志与报告：`outputs/reconstruction/env_check_south_building_colmap/`
- **Brush 3DGS 验证结果**（`train_3dgs.py --total-steps 2000 --max-resolution 1024 --eval-split-every 8 --eval-save-to-disk --export-splat`）：
  - 导出模型：`model_2000.ply`（`2,883,818` 字节，`12,213` 个高斯点，SH 3 阶，0 个非有限坐标）与 `model_2000.splat`（`390,816` 字节），耗时 `40.48s`。
  - 已查看渲染评测图 `eval_2000/P1180141.png` 等输出，建筑立面、门窗、灌木与路面结构均正常重建。
  - 日志与报告：`outputs/reconstruction/env_check_south_building_3dgs/`

接收者实际打开结果后，将检查结论记入 `docs/handoffs/`。
