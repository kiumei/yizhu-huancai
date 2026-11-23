# 第一阶段验收与进展汇总

对照 [校史馆第一阶段.docx](../plans/校史馆第一阶段.docx) 的 8 项检查标准，结合本轮基于替代实拍视频 `83fbad286b95fc6e19a45ca2eeb22d5a_raw.mp4` 与公开风格示例的实施情况，汇总验收结论如下：

| 检查项 | 通过标准 | 主负责人 | 当前状态 | 实测依据与剩余说明 |
| --- | --- | --- | --- | --- |
| **1. 素材完整** | 保留原始素材，训练图像可追溯来源 | 许铭轩 | **基本通过（测试场景）** | 原视频已归档于 `data/raw/capture01_raw.mp4`（SHA-256 已校验），`frames.csv` 与 `source_manifest.json` 完整追溯 76 张图像；*注：正式校史馆展区实拍与正面展板内容图待后续补采* |
| **2. 处理可重复** | 另一成员能按说明生成筛选图像 | 许铭轩 | **通过** | 已使用 [capture01_v1_review.csv](../../configs/capture01_v1_review.csv) 在独立目录重跑 `preprocess.py`，`images/` 与 `splits/` 共 `81` 个文件 SHA-256 字节级一致 |
| **3. 位姿可靠** | 主要区域连贯，相机分布合理，缺失已记录 | 李金华 | **通过** | 已验证 `south-building` 公开示例（24/24）；自采 `capture01_v1` 经 `global_mapper` 合并为 **1 个连通模型，`68/68`（100%）注册**，`19,955` 点，平均重投影误差 `0.490 px`（见 [reconstruction-capture01_v1.md](reconstruction-capture01_v1.md)） |
| **4. 自采模型可用** | 推荐范围内可辨认主要空间与展陈 | 李金华 | **通过（含缺陷清单）** | `model_10000.ply`（`464,680` 点）与 `model_10000.splat` 已生成；7 张独立评测渲染图显示主空间、书架、铭牌与桌椅清晰可辨，已记录 4 项局部缺陷及补拍建议 |
| **5. 网页可操作** | 自采模型可打开、观察、复位，电脑手机有记录 | 夏廷翰 | **桌面与窄屏通过；缺实体手机记录** | `web/`（Three.js + `@sparkjsdev/spark`）已完成构建并在 `1280×800` 桌面端及 `390×844` 移动端视口实测加载、旋转缩放、复位及恢复正常；待成员用 `npm run dev:host` 补填实体手机实测 |
| **6. 风格可复现** | 输入、参考、参数与结果对应明确 | 路杰然 | **部分通过（缺源码）** | 已归档 `example-broche-rose-gold.splat` 与 `vangogh_broche.splat` 并撰写 [stylization-vangogh_v1.md](stylization-vangogh_v1.md)；按方案 A 保留说明，但**仓库尚缺 `styletransfer_splat.py` 源码、`style100.jpg` 原图及第三方仓库固定 SHA**，需路杰然补充 |
| **7. 导出有结论** | 实际加载示例风格模型；未通过时有具体阻塞与任务 | 路杰然、夏廷翰 | **通过** | 已实测在自建 `web/` 查看器加载 `vangogh_broche.splat`（`129,669` 点），颜色、透明度与几何均正常；同时通过 [inspect_splat_diff.py](../../stylization/inspect_splat_diff.py) 修正原文档点数误差（实测比输入少 `260` 点，保留子集按原序递增），并备案第二阶段 `.ply` 接口与点序映射注意事项 |
| **8. 材料齐全** | 数据、模型、代码、环境和版本对应 | 各人提交 许铭轩汇总 | **代码与文档已齐全** | 预处理、重建、风格核查、网页工程与共享配置均已打通版本对应关系与 `docs/handoffs/` 交接记录（大体积文件按 `.gitignore` 存放在本地 `data/`、`outputs/` 与 `web/public/models/`） |

## 本阶段核心交接入口

- 数据预处理交接：[preprocessing-capture01_v1.md](preprocessing-capture01_v1.md)
- 重建与写实模型交接：[reconstruction-capture01_v1.md](reconstruction-capture01_v1.md)
- 风格化核查交接：[stylization-vangogh_v1.md](stylization-vangogh_v1.md)
- 网页查看器交接：[web-viewer_v1.md](web-viewer_v1.md)

## 进入第二阶段前的建议收尾事项（供团队确认）

1. **路杰然**：将 `styletransfer_splat.py`（及 `FastSplatStyler` 固定版本 SHA、依赖、`style100.jpg`）提交到 `stylization/`，并测试接收 `outputs/reconstruction/capture01_v1_3dgs/model_10000.ply` / `.splat`。
2. **夏廷翰 / 全员**：在本机执行 `cd web && npm run dev:host`，用实体手机打开并补填手机型号、浏览器与帧率到 [web-viewer_v1.md](web-viewer_v1.md)。
3. **全员**：若下阶段直接用于校史馆正式展陈，需到校史馆选定展区按第一阶段采集规范录制正式视频及正面展板高清照片。
