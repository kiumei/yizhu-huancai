# 遗筑·幻彩

基于手机视频的三维重建、艺术风格化与网页漫游项目。近期以南昌大学校史馆内的一段连续展区为对象，完成写实与风格化展示、重要内容局部保护、三个知识点和一条导览路线。

## 技术流程

手机视频或照片 → 抽帧与质量复核 → COLMAP 相机位姿与稀疏重建 → 3D Gaussian Splatting 写实模型 → 风格训练与模型导出 → 网页交互展示。

## 目录与分工

| 目录 | 内容 | 主负责人 |
| --- | --- | --- |
| `video_preprocessing/` | 抽帧、初筛、人工复核、来源追溯与数据划分 | 许铭轩 |
| `reconstruction/` | 相机位姿、写实重建、模型清理 | 李金华 |
| `stylization/` | 风格复现、训练、属性转换与模型导出 | 路杰然 |
| `region_protection/` | 保护区域生成与保护效果实现 | 许铭轩、路杰然 |
| `evaluation/` | 固定条件比较、性能记录、实验评价 | 许铭轩组织，各模块配合 |
| `web/` | 高斯渲染、模型切换、热点与导览 | 夏廷翰 |
| `configs/` | 可共享的参数、场景变换及路线配置 | 各模块维护 |
| `docs/` | 项目方案、运行说明与交接记录 | 全员 |
| `data/` | 本地原始素材与预处理图像 | 不纳入 Git |
| `outputs/` | 本地重建、风格模型和实验产物 | 不纳入 Git |

## 当前内容

仓库已实现第一阶段核心链路源码与交接记录：

- `video_preprocessing/`：视频抽帧、初筛、人工复核与桌面界面。
- `reconstruction/`：COLMAP 位姿解算（支持 `global_mapper`）、Brush 3DGS 训练及 `.ply`/`.splat` 检查转换脚本。
- `stylization/`：`.splat` 属性审计与风格前后逐点比对工具（待补充风格训练/推理上游源码）。
- `web/`：基于 Vite + Three.js + Spark（`@sparkjsdev/spark`）的最小模型查看器，读取 `configs/viewer_models.json`。
- `docs/handoffs/`：第一阶段各模块交接记录与 [第一阶段验收汇总](docs/handoffs/stage1-acceptance.md)。

项目方案总入口见 [文档入口](docs/README.md)。

## 启动现有预处理工具

需要 Python 3.10 或以上版本。以下命令在 Windows PowerShell 的仓库根目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r video_preprocessing/requirements.txt
.\.venv\Scripts\python.exe video_preprocessing/preprocess.py --help
```

启动桌面界面：

```powershell
.\.venv\Scripts\python.exe video_preprocessing/desktop_app.py
```

命令行处理示例与输出说明见 [预处理模块](video_preprocessing/README.md)。

## 四阶段目标

1. 采集与基础验证：自采写实初版、网页查看器、风格示例及导出验证。
2. 稳定重建与风格对照：两版自采模型在同一视角切换。
3. 局部保护与校史导览：保护实验、三个知识点与约 2—3 分钟路线。
4. 测试优化与交付：设备测试、用户试用、跨成员复现和资料归档。

每阶段约两周，具体推进以运行成果和验收记录为准。

## 协作与文件管理

- 从 `main` 创建功能分支，例如 `feat/preprocessing`、`feat/reconstruction`、`feat/stylization` 或 `feat/viewer`，完成后提交 Pull Request。
- 每个模块维护自己的依赖、启动命令、输入输出格式和已知问题。
- 视频、图像数据、训练检查点与大模型保存在共享存储；仓库中的交接记录保留版本、校验值与获取方式。
- 模型点顺序、几何或显示变换改变后，重新核对保护标记、热点和路线。
- 第三方实现的来源链接、固定版本和使用方式写入各模块说明。
