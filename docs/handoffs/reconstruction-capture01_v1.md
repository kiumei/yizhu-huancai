# 位姿解算与写实重建交接记录：capture01_v1

- 模块、版本、日期：`reconstruction`、`capture01_v1`（初版写实模型）、2026-11-23
- 提交人、接收人：李金华（当前代执行整理） → 夏廷翰（网页展示）、路杰然（风格训练与导出）
- 仓库基线 SHA：`20a025f0eed7783a419ce021ae688679344479e4`（新增 `reconstruction/` 模块脚本）
- 第三方工具版本：
  - `COLMAP 4.2.1`（Commit `bd1fcf6`，2026-09-29，Windows CUDA 版，[releases/tag/4.2.1](https://github.com/colmap/colmap/releases/tag/4.2.1)）
  - `Brush v0.3.0`（Windows x64 预编译版，[releases/tag/v0.3.0](https://github.com/ArthurBrussee/brush/releases/tag/v0.3.0)）
  - 硬件环境：`NVIDIA GeForce RTX 4060 Laptop GPU`（8188 MiB 显存，驱动 `617.14`）

## 输入数据版本与校验值

- 来自 `video_preprocessing` 交付的 `data/processed/capture01_v1/`（原视频 SHA-256：`131130ed6ec9d63d1656614314e24e6bc8cd6035b7650d6ecbeb6d8e271e9fa9`）。
- 仅使用训练集 `splits/train.txt`（`68` 张 `1080×1920` 竖屏 JPEG）；`splits/val.txt`（`8` 张）未用于 3DGS 训练输入。

## 公开示例环境验证（前置检查）

- 公开数据：COLMAP 官方 `south-building` 前 `24` 张（`P1180141.JPG`–`P1180164.JPG`，位于 `data/public/south-building/`）。
- COLMAP 结果（`outputs/reconstruction/env_check_south_building_colmap/`）：`24/24` 注册（1 个子模型），`7,098` 稀疏点，平均重投影误差 `0.528 px`，耗时 `10.59s`。
- Brush 3DGS 结果（`outputs/reconstruction/env_check_south_building_3dgs/`，`2000` 步）：导出 `model_2000.ply`（`12,213` 点，0 个非有限坐标）及 `model_2000.splat`，耗时 `40.48s`；已检查 `eval_2000/P1180141.png` 等渲染图，确认环境可正常训练并查看结果。

## 自采运行命令与参数

在 `yizhu-huancai/` 根目录执行：

```powershell
# 1. COLMAP 特征提取、全量匹配、全局位姿解算与去畸变
.\.venv\Scripts\python.exe reconstruction/run_colmap.py `
  --images data/processed/capture01_v1/images `
  --image-list data/processed/capture01_v1/splits/train.txt `
  --output outputs/reconstruction/capture01_v1_colmap `
  --matcher exhaustive `
  --mapper global `
  --camera-model SIMPLE_RADIAL `
  --overwrite

# 2. Brush 3DGS 写实初版训练与 .splat 导出
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

### 匹配与建图选型对比（问题定位记录）

- **初试默认增量建图（`mapper`）**：虽然 `exhaustive_matcher` 成功跑通，但因 `splits/train.txt` 在 `v001_000043`、`000053`、`000062` 处留出了检验帧，且 `000046`–`000070` 段经过白墙与门框转角时视角变化快，增量 `mapper` 分裂为 `7` 个子模型，最大子模型仅注册 `47/68`（`69.12%`），遗漏 `v001_000046`–`000059` 与 `000063`–`000070` 区间。
- **改用全局建图（`global_mapper`）**：在同一份 `exhaustive_matcher` 数据库上全局求解旋转与平移，成功将全部 **`68/68`（`100%`）** 图像合并为 **1 个完整连通场景**，生成 `19,955` 个稀疏 3D 点，平均轨迹长度 `8.0077`，平均重投影误差 `0.4899 px`，耗时 `121.03s`。

## 输出文件、格式与存储位置

所有大体积产物保存在本地 `outputs/reconstruction/`（不纳入 Git）：

- **COLMAP 与去畸变输入**：`outputs/reconstruction/capture01_v1_colmap/`
  - 稀疏模型：`sparse/0/`（`BIN`）与 `sparse_txt/0/`（`TXT`）
  - 相机内参（单相机 `SIMPLE_RADIAL` `1080×1920`）：`f = 1698.40 px`、`cx = 540.0`、`cy = 960.0`、`k1 = 0.007071`
  - 去畸变 3DGS 训练集：`undistorted/images/`（68 张 `1080×1916` 级去畸变图像）与 `undistorted/sparse/`
  - 统计与日志：`sfm_report.json`、`colmap.log`
- **3DGS 写实初版模型**：`outputs/reconstruction/capture01_v1_3dgs/`
  - 训练耗时：`392.05s`（`10,000` 步，`max-resolution=1600`，`eval-split-every=10`）
  - 标准 3DGS 模型：`model_10000.ply`（`109,666,031` 字节，**464,680** 个高斯点，`binary_little_endian`，含 `59` 个属性：`f_dc_0..2`、`f_rest_0..44` 共 3 阶球谐、`opacity`、`rot_0..3`、`scale_0..2`、`x,y,z`，0 个 `NaN/Inf`）
  - 网页轻量导出：`model_10000.splat`（`14,869,760` 字节，**464,680** 个点，标准 32 字节/高斯格式，按 `exp(scale)` 体积 × `sigmoid(opacity)` 降序重排）
  - 评测渲染图：`eval_10000/v001_000001.png`、`000012.png`、`000023.png`、`000035.png`、`000046.png`、`000057.png`、`000068.png`
  - 报告与日志：`train_report.json`、`train.log`

## 坐标、尺度与接口参数（供网页与风格模块）

- **坐标系方向**：沿用 COLMAP 世界坐标系（相机上方向平均向量 `mean_camera_up_world ≈ [0.021, -0.998, 0.059]`，即 **COLMAP 世界 `-Y` 为向上方向**；在 Three.js 默认 `+Y` 向上坐标系中加载时，通常需绕 X 轴旋转 `180°`）。
- **相机范围**：68 个相机中心分布在 `[-10.058, -3.158, -6.693]` 至 `[6.715, 1.382, 17.755]`，中心均值 `[0.004, -0.061, 0.387]`；首帧相机位置 `[-10.058, 0.009, -6.693]`，朝向 `[0.723, 0.288, 0.628]`。
- **高斯点分布**：中位中心 `[7.018, 1.922, 10.010]`；第 5–95 百分位主体范围 `x: [-120.12, 24.45]`、`y: [-8.48, 10.54]`、`z: [-8.87, 29.57]`；外围绝对包围盒受少量远景/窗外漂浮高斯影响扩展到 `[-207.90, -201.03, -224.06]` 至 `[110.90, 214.95, 248.19]`。
- **给风格模块（路杰然）说明**：`model_10000.ply` 为标准 3 阶球谐 3DGS PLY（无多余自定义字段），`undistorted/` 为去畸变后的标准 COLMAP 图像与位姿输入；需注意若使用 `.splat` 转换，点顺序已按重要度重排，不可与原 `.ply` 按行号一对一索引。

## 初版质量评估、缺陷清单与补拍建议

基于 `eval_10000/` 7 张独立评测视角渲染图的人工检查结论：**室内主空间、书架、桌椅、“大学生读书社”铭牌、空调与墙面挂画、背包书桌角均已清晰可辨，满足第一阶段自采写实初版要求。** 已定位缺陷与原因如下：

1. **近景柜体侧边与画面边缘拖影（采集覆盖问题）**
   - 位置：`eval_10000/v001_000001.png` 底部及左右边缘、`eval_10000/v001_000012.png` 左侧贴近的木柜正面/侧面。
   - 原因：机位过于贴近左侧柜体且缺少多角度回看覆盖，同时评测集留出了关键过渡帧。
   - 补拍建议：经过窄处柜体时保持 `1.2m` 以上退距，从正前、左斜、右斜三角度缓扫。
2. **桌旁人物重影与局部糊化（动态目标问题）**
   - 位置：`eval_10000/v001_000001.png`、`000023.png`、`000035.png` 中的就座人员与笔记本屏幕反光区域。
   - 原因：38 秒拍摄期间人物有轻微低头/移动，违背静态多视角假设。
   - 补拍建议：正式校史馆展区采集应尽量清场或避开走动人员。
3. **门框 `J003` 与玻璃门立柜转角竖向拉丝/玻璃重影（转角视角少 + 反光）**
   - 位置：`eval_10000/v001_000057.png` 右侧绿门边缘、`eval_10000/v001_000068.png` 玻璃门立柜及书架过渡处。
   - 原因：在门框与玻璃柜转角处扫掠较快，且玻璃柜门存在镜面反光，导致多视角特征一致性下降。
   - 补拍建议：转角处放慢脚步，停留补拍 2–3 个大重叠过渡视角，并正斜多角度覆盖立柜。
4. **外围远距漂浮高斯（窗外景物 + 边界散点）**
   - 位置：主体包围盒之外（`bbox` 达 `±200+` 量级，透过窗户看到室外车辆与建筑）。
   - 原因：大面积玻璃窗透出室外远景，稀疏三角化在远距产生少量低不透明度散点（`opacity` 中位值 `0.068`）。
   - 后续处理（第二阶段）：在 `reconstruction/` 中增加包围盒裁剪与低透明度漂浮物清理工具。

## 接收检查与下一步

- **当前状态**：已完成环境验证与自采写实初版生成，模型已就绪等待网页端（夏廷翰）加载检查方向/尺度，以及风格端（路杰然）核对第二阶段接口兼容性。
