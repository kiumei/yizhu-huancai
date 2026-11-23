# 共享配置

本目录存放需要随代码追踪的配置，例如预处理参数、固定观察视角、场景显示变换、模型版本、热点和导览路线。

## 现有配置文件

- [capture01_v1_review.csv](capture01_v1_review.csv)：第一阶段 `capture01_raw.mp4`（`--sample-fps 2`）的人工复核表，记录 `v001_000077`–`v001_000087` 末尾倾斜及模糊过渡帧的剔除决定，供 `video_preprocessing/preprocess.py --review-file` 复现使用。
- [viewer_models.json](viewer_models.json)：第一阶段网页查看器的模型清单、本地路径、坐标对齐欧拉角（`rotationDeg` / `position`）与初始相机参数（`cameraPosition` / `cameraTarget`），由 `web/` 直接读取；坐标单位为模型自身无量纲重建尺度。

## 维护约定

在模块采用具体配置格式后再添加实际文件。每份配置说明读取它的程序、对应的数据或模型版本、字段含义与坐标单位。示例使用相对路径和占位值，本机路径保存在忽略文件中。

大体积高斯索引、掩码与模型放在 `outputs/` 或共享存储；本目录记录其版本、校验值和引用关系。
