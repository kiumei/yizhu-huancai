# 网页展示与导览

负责人：夏廷翰。

本目录已建立基于 **Vite + Three.js + Spark（`@sparkjsdev/spark`）** 的第一阶段最小高斯查看器工程，配置文件位于 [configs/viewer_models.json](../configs/viewer_models.json)。

## 依赖与启动方式

需要 `Node.js`（已自带 `npm`）。在仓库根目录或 `web/` 目录运行：

```powershell
cd web
npm install
npm run dev
```

默认本地访问地址：`http://localhost:5173/`。

若需用同一局域网下的手机浏览器实机访问测试，请执行：

```powershell
cd web
npm run dev:host
```

随后用手机打开终端打印的 `Network: http://<本机局域网IP>:5173/` 地址。

生产构建验证：

```powershell
cd web
npm run build
```

## 模型准备位置

按照 `.gitignore` 约定，大型模型文件不提交到 Git，需放置于 `web/public/models/`（见 [web/public/models/README.md](public/models/README.md)）：

- `capture01_v1.splat`（自采写实初版，464,680 点）
- `example-broche-rose-gold.splat`（公开原版示例，129,929 点）
- `vangogh_broche.splat`（梵高星月夜风格示例，129,669 点）

## 已实现功能（第一阶段）

- **多模型切换**：读取 [configs/viewer_models.json](../configs/viewer_models.json) 切换自采写实模型、公开原版与梵高风格示例，自动按模型应用欧拉角旋转与位移对齐。
- **基础交互与复位**：基于 `OrbitControls` 支持鼠标/触控旋转、缩放、平移，以及 **“返回初始视角”** 一键复位。
- **状态与错误定位**：明确区分 `加载中`（含字节下载进度）、`加载成功`（显示来源版本、实际点数、变换参数与实时 FPS）与 `加载失败`（捕获 HTTP 错误及静态服务返回的 HTML 回退页，弹出非静默错误提示）。
- **替换测试入口**：面板内折叠区支持自定义模型 URL、本机文件选择（`.splat` / `.ply` / `.spz`）、参考网格开关与一键触发 404/缺失提示测试。

## 后续阶段规划

- 第二阶段：统一自采写实与自采风格模型的对齐变换，实现同视角无缝切换。
- 第三阶段：增加三个知识热点、图文卡片与约 2—3 分钟导览路线。
- 第四阶段：多设备性能与用户试用优化。
