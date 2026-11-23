# 本地网页测试模型目录

本目录用于存放网页端加载的 `.splat` / `.ply` 高斯模型文件，除本说明外均由 `.gitignore` 排除，不提交到 Git。

请将对应模型复制到本目录（保持文件名与 `configs/viewer_models.json` 一致）：

- `capture01_v1.splat`：来自 `outputs/reconstruction/capture01_v1_3dgs/model_10000.splat`（自采写实初版，464,680 点）
- `example-broche-rose-gold.splat`：来自 `outputs/stylization/example-broche-rose-gold.splat`（公开原版示例，129,929 点）
- `vangogh_broche.splat`：来自 `outputs/stylization/vangogh_broche.splat`（公开风格示例，129,669 点）

也可在网页右上角的测试入口中直接选择本地 `.splat` / `.ply` 文件或填写模型 URL 进行替换测试。
