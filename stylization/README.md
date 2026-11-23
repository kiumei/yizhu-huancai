# 风格训练与模型导出

负责人：路杰然。

本目录维护风格复现、导出检查脚本、属性差异核查工具与第二阶段自采接口规范。

## 第一阶段现有内容（方案 A 归档）

根据路杰然交付的 [风格化示例(1)/3DGS/](../../风格化示例(1)/3DGS) 现有产物，本仓库已补充二进制属性核查工具：

- [inspect_splat_diff.py](inspect_splat_diff.py)：校验标准 32 字节 `.splat` 文件结构，并逐点比对风格化前后位置、尺度、透明度、旋转四元数与 RGB 颜色的变化。
- [requirements.txt](requirements.txt)：仅依赖 `numpy>=1.24,<3`。

### 已有风格示例说明

- **方法线索**：文档记录命令行 `python styletransfer_splat.py example-broche-rose-gold.splat --stylePath style_ims/style100.jpg --samplingRate 1.5`（对应开源实现候选：[davidmhart/FastSplatStyler](https://github.com/davidmhart/FastSplatStyler)，具体提交 SHA 与源码待路杰然补充提交）。
- **候选风格**：梵高《星月夜》方向（参考图 `style100.jpg`，蓝黄冷暖对比、流动笔触与厚涂油画色彩特征）。
- **本地模型产物**（存放于 `outputs/stylization/`，不纳入 Git）：
  - 原版输入：`example-broche-rose-gold.splat`（`4,157,728` 字节，`129,929` 个高斯点）
  - 风格输出：`vangogh_broche.splat`（原名 `output梵高风.splat`，`4,149,408` 字节，`129,669` 个高斯点）
  - 对比报告：`vangogh_diff_report.json`

## 运行属性对比检查

在仓库根目录执行：

```powershell
.\.venv\Scripts\python.exe stylization/inspect_splat_diff.py `
  outputs/stylization/example-broche-rose-gold.splat `
  --styled outputs/stylization/vangogh_broche.splat `
  --json-out outputs/stylization/vangogh_diff_report.json
```

## 与自采写实模型（第二阶段）的接口说明

- **输入兼容性**：李金华第二阶段产出的 `model_*.ply`（59 个属性，3 阶球谐）可直接用 [reconstruction/inspect_ply.py](../reconstruction/inspect_ply.py) 的 `--to-splat` 转换为标准 32 字节 `.splat`（已针对 `capture01_v1` `model_10000.splat` 验证 `464,680` 点格式完全合法），或直接由支持 `.ply` 的风格训练/推理脚本读取。
- **关键注意事项（影响第三阶段局部保护）**：
  1. 实测 `vangogh_broche.splat` 比输入少了 `260` 个点，虽然保留点按原顺序递增且位置/尺度/透明度逐字节不变，但若后续局部保护采用按点序号索引的掩码，必须由风格脚本输出“保留点索引映射”或在保护阶段基于保留集重新匹配坐标。
  2. 当前仓库尚缺 `styletransfer_splat.py` 源码、依赖文件及 `style100.jpg` 原图文件，须在进入第二阶段自采风格前由路杰然补齐并验证跨成员复现。

局部保护与区域标记的接口见 [region_protection/README.md](../region_protection/README.md)。
