# 数据预处理交接记录：capture01_v1

- 模块、版本、日期：`video_preprocessing`（程序版本 `1.1.0`）、`capture01_v1`、2026-11-23
- 提交人、接收人：许铭轩（当前代执行整理） → 李金华（位姿与写实重建）
- 代码提交 SHA、第三方代码版本：基于仓库提交 `20a025f0eed7783a419ce021ae688679344479e4`；仅使用开源库 `opencv-python==5.1.0.95`、`numpy==2.5.5`、`Pillow==12.3.0`（无第三方业务源码）。

## 输入数据版本与校验值

- 原始视频：`data/raw/capture01_raw.mp4`（来自根目录上传文件 `83fbad286b95fc6e19a45ca2eeb22d5a_raw.mp4`）
- 原视频 SHA-256：`131130ed6ec9d63d1656614314e24e6bc8cd6035b7650d6ecbeb6d8e271e9fa9`
- 文件大小：`90,533,159` 字节
- 视频规格：`1080×1920`（竖屏）、`30.02 FPS`（`30.024593`）、`1288` 帧、时长 `42.92 秒`
- 拍摄地点：`南昌大学大学生读书社室内空间（第一阶段自采替代试拍）`
- 人工复核表：`configs/capture01_v1_review.csv`（SHA-256：`2879cd6d553307bde42615a3861f9f876ec4280549fa42f6d6a63fb22514d3c4`）

## 运行环境、命令与参数

- Python 环境：仓库根目录 `.venv`（Python `3.12.9`）
- 复现命令（在 `yizhu-huancai/` 根目录执行）：

```powershell
.\.venv\Scripts\python.exe video_preprocessing/preprocess.py `
  --input data/raw/capture01_raw.mp4 `
  --output data/processed/capture01_v1 `
  --sample-fps 2 `
  --review-file configs/capture01_v1_review.csv `
  --location "南昌大学大学生读书社室内空间（第一阶段自采替代试拍）" `
  --source-description "83fbad286b95fc6e19a45ca2eeb22d5a_raw.mp4 原始手机视频（已复核剔除末尾倾斜/模糊帧）"
```

- 关键参数：`sample_fps=2.0`、`blur_threshold=50.0`、`duplicate_hamming=2`、`duplicate_mad=2.0`、`max_keep_gap=2.0`、`val_ratio=0.1`、`jpeg_quality=95`。

## 输出文件、格式与存储位置

输出目录位于本地 `data/processed/capture01_v1/`（不纳入 Git）：

- `candidates/`：87 张候选 JPEG 帧（`v001_000001.jpg` 至 `v001_000087.jpg`）
- `images/`：76 张最终保留 JPEG 帧（`v001_000001.jpg` 至 `v001_000076.jpg`）
- `splits/train.txt`、`splits/train.json`：68 张训练集列表（`train`）
- `splits/val.txt`、`splits/val.json`：8 张流程检验集列表（`val`：`v001_000005`、`v001_000015`、`v001_000024`、`v001_000034`、`v001_000043`、`v001_000053`、`v001_000062`、`v001_000072`）
- `splits/all.txt`：全部 76 张保留图像文件名
- `frames.csv`、`review.csv`、`source_manifest.json`、`config.json`、`summary.json`、`report.html`、`previews/`

## 人工复核与覆盖检查结论

- **时间覆盖**：保留时间跨度 `0.000s` 至 `37.526s`，最大帧间隔 `0.533s`，无超限缺口（`gaps_above_limit=[]`）。
- **人工剔除（11 帧，`v001_000077` 至 `v001_000087`）**：
  - 前 76 帧已完成室内环绕一圈并回到起始书架区域（形成闭环），画面清晰度在 `290.1` 至 `1357.6` 之间，无黑场、白场或过度重复帧。
  - `v001_000077`–`v001_000078` 开始出现明显竖转横倾斜；`v001_000079`–`v001_000081` 为程序标记的 `blur_candidate`（清晰度 `19.9`–`45.9`，对准天花板灯带过渡）；`v001_000082`–`v001_000087` 为片尾横握 90 度旋转画面。为保证相机方向与训练输入干净一致，已通过 `configs/capture01_v1_review.csv` 全部标记 `drop`。

## 跨成员复现检查结果

- 已使用上述同一命令在独立目录 `data/processed/_repro_check/` 重跑预处理，对比 `images/` 与 `splits/` 全部 `81` 个文件的 SHA-256 校验值，**100% 字节级一致**。

## 已知问题与下游提醒

- **动态与反光区域**：图像中存在室内坐姿人员、门外走廊局部及玻璃窗反光，COLMAP 与 3DGS 初版在该区域可能产生局部模糊或漂浮物，请在重建缺陷清单中标注定位。
- **非正式校史馆场景**：本素材为替代性实拍测试视频，用于跑通第一阶段技术链路；正式进入校史馆展区时需按同样流程采集校史馆展区与正面展板内容图。
- **下游交接**：数据已可直接送入 `reconstruction/` 进行 COLMAP 特征匹配与位姿解算。
