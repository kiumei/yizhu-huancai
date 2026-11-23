# 风格复现与导出交接记录：vangogh_v1

- 模块、版本、日期：`stylization`、`vangogh_v1`（公开示例风格验证）、2026-11-23
- 提交人、接收人：路杰然（现有产物归档与属性核查整理） → 夏廷翰（网页端加载验证）、许铭轩（局部保护接口备案）
- 仓库基线 SHA：`20a025f0eed7783a419ce021ae688679344479e4`（新增 `stylization/inspect_splat_diff.py` 核查工具）
- 第三方方法来源：文档命令 `styletransfer_splat.py ... --stylePath style_ims/style100.jpg --samplingRate 1.5` 对应开源项目 [davidmhart/FastSplatStyler](https://github.com/davidmhart/FastSplatStyler)（实际运行代码的精确提交 SHA 待路杰然补充确认）。

## 输入、参考与导出输出

- **输入公开模型**：`outputs/stylization/example-broche-rose-gold.splat`（`4,157,728` 字节，SHA-256：`62cccf0adfb4e5713985e8ee874fa30a6a37ae222a23ead7c6e4639a5802ab62`）
- **参考风格**：官方示例自带 `style_ims/style100.jpg`（《星月夜》风格方向：蓝黄高对比色彩、流动笔触倾向）
- **导出风格模型**：`outputs/stylization/vangogh_broche.splat`（原文件 `output梵高风.splat`，`4,149,408` 字节，SHA-256：`e000a2a7a6ad947d9c6689ed0ba3c54d4f33d70a64a8c77cd723af42986afd20`）
- **输出格式**：标准 32 字节/点 `.splat`（位置 `3f32`、线性尺度 `3f32`、RGBA `4u8`、归一化四元数 `4u8`），无需再做格式转换即可交给 Three.js / Spark 加载。

## 属性对比与实测纠偏（重要）

使用 `stylization/inspect_splat_diff.py` 对输入与输出二进制逐点比对，结果保存于 `outputs/stylization/vangogh_diff_report.json`：

- **点数更正**：原 `风格化.docx` 记为“提取节点数 258295，风格化前后点数完全保持一致”，**实测不准确**。真实二进制点数为：
  - 输入 `example-broche-rose-gold.splat`：**129,929** 点
  - 输出 `vangogh_broche.splat`：**129,669** 点
  - 实际减少：**260** 个点（已从原模型中剔除，被剔除点不透明度中位值 `alpha = 10`）。
- **点顺序与几何一致性**：输出全部 `129,669` 个点均能按精确三维位置（`pos`）在原模型中唯一匹配，且相对索引严格递增（顺序未打乱）。
- **属性变化**：
  - `scale`（尺度）：与保留子集**逐字节完全一致**。
  - `alpha`（不透明度字节）：与保留子集**逐字节完全一致**。
  - `rot`（旋转四元数字节）：最大绝对字节差 `1`（约 `64.23%` 完全相同，其余受编解码重归一化 8-bit 量化舍入影响）。
  - `RGB`（颜色）：整体由原版暖金色（均值 `[210.82, 164.10, 96.63]`）迁移为冷蓝黄风格（均值 `[83.63, 101.04, 113.37]`），无 `NaN/Inf`。

## 自采写实数据接入兼容性（第二阶段准备）

- **已核对部分**：李金华交付的 `capture01_v1` `model_10000.ply` 为标准 `binary_little_endian` 3DGS PLY（`464,680` 点，3 阶球谐共 `59` 属性），经 `inspect_ply.py --to-splat` 与 `inspect_splat_diff.py` 验证可直接导出为标准 32 字节 `model_10000.splat`（`14,869,760` 字节，SHA-256：`84d76b6ee8e67c754a429617d461ebc8b60330a62d296a48974622dcb85df6a7`）。
- **待转换与注意事项**：
  1. `FastSplatStyler` 针对静态颜色迁移生效；自采场景 `capture01_v1` 为室内大场景（`464,680` 点，主体范围跨度约 `30+` 单位），第二阶段接入前需在自采 `.ply` / `.splat` 上实测颜色迁移效果及采样参数 `--samplingRate` 对内存与点保留率的影响。
  2. 若从 `.ply` 转 `.splat` 再风格化，转 `.splat` 时会按重要度排序且风格化本身会删减部分低权重点，**第三阶段局部保护禁止直接假设点序号与原 `.ply` 相同**，需保存点映射或基于空间坐标/索引重绑定。

## 遗留阻塞与待补充项（方案 A 明确记录）

- **源码与参考图缺失（需路杰然补充）**：当前仅收到成品 `.splat` 模型、录屏与 Word 文档，仓库中尚无 `styletransfer_splat.py` 代码、依赖清单、`style100.jpg` 原图文件及第三方仓库固定 commit SHA，尚不满足“其他成员直接按仓库重跑风格生成命令”的条件。
- **网页联调**：此前仅在在线工具 SuperSplat 录屏检查；将在第 4 步接入本项目自建 `web/` 查看器完成真实加载验证。
