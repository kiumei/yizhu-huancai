# 视频预处理

负责人：许铭轩。

现有源码包括 `preprocess.py` 命令行程序和 `desktop_app.py` 桌面界面。两者使用相同的处理引擎。

## 环境与运行

在仓库根目录创建 Python 3.10 或以上版本的虚拟环境，安装本模块 `requirements.txt`。以下命令使用根目录 `.venv`：

```powershell
.\.venv\Scripts\python.exe -m pip install -r video_preprocessing/requirements.txt
.\.venv\Scripts\python.exe video_preprocessing/preprocess.py --help
```

将现场视频放到本地 `data/raw/` 后运行，例如：

```powershell
.\.venv\Scripts\python.exe video_preprocessing/preprocess.py --input data/raw/capture01.mp4 --output data/processed/capture01_v1 --sample-fps 2 --location "校史馆选定展区"
```

输出目录必须是新的目录，程序拒绝覆盖已有结果。每秒抽帧数根据移动速度和覆盖情况调整。

启动桌面界面：

```powershell
.\.venv\Scripts\python.exe video_preprocessing/desktop_app.py
```

## 输出与交接

- `candidates/`、`images/`：候选帧和筛选后图像。
- `frames.csv`、`review.csv`：质量标记、来源与人工复核记录。
- `splits/`：训练和检验图像列表及来源映射。
- `config.json`、`source_manifest.json`、`summary.json`：参数、原始素材信息和汇总。
- `report.html`、`previews/`、`run_state.json`：复核报告、缩略图与运行状态。

向重建负责人交付完整输出目录、原始素材版本和复核说明。评分结果需要结合侧面、转角与连接视角人工判断。同视频留出的检验帧用于流程检查，独立新视角的质量评价需另行采集。

完整数据保存在共享存储，版本和交接说明记录到 `docs/handoffs/`。现有打包程序 `VideoFrameTool.exe` 通过单独的分发渠道提供。
