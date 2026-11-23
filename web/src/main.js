import "./style.css";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { SparkRenderer, SplatMesh } from "@sparkjsdev/spark";
import viewerConfig from "../../configs/viewer_models.json";

const canvasWrap = document.getElementById("canvas-wrap");
const hud = document.getElementById("hud");
const togglePanelBtn = document.getElementById("toggle-panel-btn");
const modelSelect = document.getElementById("model-select");
const resetViewBtn = document.getElementById("reset-view-btn");
const reloadBtn = document.getElementById("reload-btn");
const statusBox = document.getElementById("status-box");
const statusBadge = document.getElementById("status-badge");
const statusMessage = document.getElementById("status-message");
const fpsCounter = document.getElementById("fps-counter");
const metaVersion = document.getElementById("meta-version");
const metaSplats = document.getElementById("meta-splats");
const metaTransform = document.getElementById("meta-transform");
const customUrlInput = document.getElementById("custom-url-input");
const loadUrlBtn = document.getElementById("load-url-btn");
const localFileInput = document.getElementById("local-file-input");
const toggleGridInput = document.getElementById("toggle-grid-input");
const testErrorBtn = document.getElementById("test-error-btn");
const centerOverlay = document.getElementById("center-overlay");
const overlayCard = centerOverlay.querySelector(".overlay-card");
const overlaySpinner = document.getElementById("overlay-spinner");
const overlayTitle = document.getElementById("overlay-title");
const overlayDetail = document.getElementById("overlay-detail");

const models = viewerConfig.models;
const modelById = new Map(models.map((item) => [item.id, item]));

let renderer;
let scene;
let camera;
let controls;
let spark;
let helpersGroup;
let activeMesh = null;
let activeEntry = null;
let loadSeq = 0;

function initScene() {
  renderer = new THREE.WebGLRenderer({ antialias: false, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
  renderer.setSize(canvasWrap.clientWidth, canvasWrap.clientHeight);
  canvasWrap.appendChild(renderer.domElement);

  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0f141b);

  camera = new THREE.PerspectiveCamera(
    55,
    canvasWrap.clientWidth / Math.max(1, canvasWrap.clientHeight),
    0.05,
    1000
  );

  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.minDistance = 0.2;
  controls.maxDistance = 120;

  spark = new SparkRenderer({ renderer });
  scene.add(spark);

  helpersGroup = new THREE.Group();
  helpersGroup.visible = false;
  const grid = new THREE.GridHelper(16, 16, 0x334155, 0x1e293b);
  grid.position.y = -2.8;
  helpersGroup.add(grid);
  helpersGroup.add(new THREE.AxesHelper(0.8));
  scene.add(helpersGroup);

  window.addEventListener("resize", onResize);

  let frames = 0;
  let lastFpsTime = performance.now();
  renderer.setAnimationLoop(() => {
    controls.update();
    renderer.render(scene, camera);
    frames += 1;
    const now = performance.now();
    if (now - lastFpsTime >= 600) {
      const fps = Math.round((frames * 1000) / (now - lastFpsTime));
      fpsCounter.textContent = `${fps} FPS`;
      frames = 0;
      lastFpsTime = now;
    }
  });
}

function onResize() {
  if (!renderer || !camera) return;
  const w = Math.max(1, canvasWrap.clientWidth);
  const h = Math.max(1, canvasWrap.clientHeight);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h);
}

function setStatus(state, badgeText, msg, { overlay = false, title = "", detail = "" } = {}) {
  statusBox.className = `status status-${state}`;
  statusBadge.textContent = badgeText;
  statusMessage.textContent = msg;

  if (!overlay) {
    centerOverlay.hidden = true;
    return;
  }
  centerOverlay.hidden = false;
  overlayCard.classList.toggle("is-error", state === "error");
  overlaySpinner.hidden = state !== "loading";
  overlayTitle.textContent = title || badgeText;
  overlayDetail.textContent = detail || msg;
}

function applyCameraPreset(entry) {
  const pos = entry.cameraPosition || [0, 1, 4];
  const target = entry.cameraTarget || [0, 0, 0];
  camera.position.set(pos[0], pos[1], pos[2]);
  controls.target.set(target[0], target[1], target[2]);
  controls.update();
}

function disposeActiveMesh() {
  if (!activeMesh) return;
  scene.remove(activeMesh);
  if (typeof activeMesh.dispose === "function") {
    activeMesh.dispose();
  }
  activeMesh = null;
}

function applyTransform(mesh, entry) {
  const rotDeg = entry.rotationDeg || [180, 0, 0];
  const pos = entry.position || [0, 0, 0];
  mesh.rotation.set(
    THREE.MathUtils.degToRad(rotDeg[0]),
    THREE.MathUtils.degToRad(rotDeg[1]),
    THREE.MathUtils.degToRad(rotDeg[2])
  );
  mesh.position.set(pos[0], pos[1], pos[2]);
  metaTransform.textContent = `rot(${rotDeg.join(",")})° · pos(${pos.join(",")})`;
}

async function fetchWithProgress(url, onBytes) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} ${response.statusText || ""} (${url})`.trim());
  }
  const contentType = (response.headers.get("content-type") || "").toLowerCase();
  if (contentType.includes("text/html")) {
    throw new Error(`未找到模型文件（服务端返回了 HTML 页面，请检查文件是否存在）：${url}`);
  }
  const total = Number(response.headers.get("content-length")) || 0;
  if (!response.body) {
    const buf = new Uint8Array(await response.arrayBuffer());
    onBytes(buf.byteLength, total || buf.byteLength);
    return buf;
  }
  const reader = response.body.getReader();
  const chunks = [];
  let loaded = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    loaded += value.byteLength;
    onBytes(loaded, total);
  }
  const combined = new Uint8Array(loaded);
  let offset = 0;
  for (const chunk of chunks) {
    combined.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return combined;
}

async function loadModel(entry, localFile = null) {
  const seq = ++loadSeq;
  activeEntry = entry;
  metaVersion.textContent = entry.sourceVersion || entry.url || "-";
  metaSplats.textContent = "解析中…";
  metaTransform.textContent = "-";

  setStatus("loading", "加载中", `正在获取 ${entry.label}…`, {
    overlay: true,
    title: `正在加载：${entry.label}`,
    detail: localFile ? `本地文件 ${localFile.name}` : entry.url,
  });

  try {
    let bytes;
    let fileName;
    if (localFile) {
      bytes = new Uint8Array(await localFile.arrayBuffer());
      fileName = localFile.name;
    } else {
      bytes = await fetchWithProgress(entry.url, (loaded, total) => {
        if (seq !== loadSeq) return;
        const mb = (loaded / (1024 * 1024)).toFixed(2);
        const progressText = total
          ? `已下载 ${mb} / ${(total / (1024 * 1024)).toFixed(2)} MB (${Math.round((loaded * 100) / total)}%)`
          : `已下载 ${mb} MB`;
        statusMessage.textContent = progressText;
        overlayDetail.textContent = progressText;
      });
      fileName = entry.url.split("?")[0].split("/").pop() || "model.splat";
    }

    if (seq !== loadSeq) return;
    if (bytes.byteLength === 0) {
      throw new Error(`模型文件为空（0 字节）：${fileName}`);
    }

    overlayDetail.textContent = "正在解析高斯数据并上传 GPU…";
    const mesh = new SplatMesh({ fileBytes: bytes, fileName });
    applyTransform(mesh, entry);
    await mesh.initialized;

    if (seq !== loadSeq) {
      mesh.dispose();
      return;
    }

    disposeActiveMesh();
    activeMesh = mesh;
    scene.add(mesh);
    applyCameraPreset(entry);

    const splatCount = mesh.splats?.getNumSplats?.();
    metaSplats.textContent = typeof splatCount === "number" ? splatCount.toLocaleString("zh-CN") : "未知";
    setStatus("ready", "加载成功", `${entry.notes || "模型已就绪，可拖拽旋转或缩放查看。"}`);
  } catch (err) {
    if (seq !== loadSeq) return;
    const message = err instanceof Error ? err.message : String(err);
    console.error("[Viewer Load Error]", err);
    metaSplats.textContent = "加载失败";
    setStatus("error", "加载失败", `错误详情：${message}`, {
      overlay: true,
      title: "模型加载失败",
      detail: `${message} — 请检查模型文件是否位于 web/public/models/ 或更换可用入口。`,
    });
  }
}

function populateSelect() {
  for (const item of models) {
    const opt = document.createElement("option");
    opt.value = item.id;
    opt.textContent = item.label;
    modelSelect.appendChild(opt);
  }
  const initialId = modelById.has(viewerConfig.defaultModelId)
    ? viewerConfig.defaultModelId
    : models[0].id;
  modelSelect.value = initialId;
}

function bindEvents() {
  togglePanelBtn.addEventListener("click", () => {
    const collapsed = hud.classList.toggle("collapsed");
    togglePanelBtn.textContent = collapsed ? "展开" : "收起";
  });

  modelSelect.addEventListener("change", () => {
    const item = modelById.get(modelSelect.value);
    if (item) loadModel(item);
  });

  resetViewBtn.addEventListener("click", () => {
    if (activeEntry) applyCameraPreset(activeEntry);
  });

  reloadBtn.addEventListener("click", () => {
    if (activeEntry) loadModel(activeEntry);
  });

  loadUrlBtn.addEventListener("click", () => {
    const url = customUrlInput.value.trim();
    if (!url) {
      setStatus("error", "输入无效", "请先填写模型 URL 再点击加载。");
      return;
    }
    loadModel({
      id: "custom_url",
      label: `自定义 URL (${url.split("/").pop() || url})`,
      url,
      sourceVersion: url,
      rotationDeg: [180, 0, 0],
      position: [0, 0, 0],
      cameraPosition: [0, 1.0, 3.2],
      cameraTarget: [0, 0, 0],
      notes: "来自自定义 URL 测试入口；若倒置请核对源坐标系。",
    });
  });

  localFileInput.addEventListener("change", () => {
    const file = localFileInput.files?.[0];
    if (!file) return;
    loadModel(
      {
        id: "local_file",
        label: `本地文件 (${file.name})`,
        url: file.name,
        sourceVersion: `${file.name} (${(file.size / (1024 * 1024)).toFixed(2)} MB)`,
        rotationDeg: [180, 0, 0],
        position: [0, 0, 0],
        cameraPosition: [0, 1.0, 3.2],
        cameraTarget: [0, 0, 0],
        notes: "来自本机文件测试入口。",
      },
      file
    );
  });

  toggleGridInput.addEventListener("change", () => {
    if (helpersGroup) helpersGroup.visible = toggleGridInput.checked;
  });

  testErrorBtn.addEventListener("click", () => {
    const missingUrl = "/models/__missing_test_model__.splat";
    customUrlInput.value = missingUrl;
    loadModel({
      id: "error_test",
      label: "失败提示测试样例",
      url: missingUrl,
      sourceVersion: missingUrl,
      rotationDeg: [180, 0, 0],
      position: [0, 0, 0],
      cameraPosition: [0, 1, 3],
      cameraTarget: [0, 0, 0],
    });
  });
}

try {
  initScene();
  populateSelect();
  bindEvents();
  const initial = modelById.get(modelSelect.value) || models[0];
  loadModel(initial);
} catch (err) {
  const message = err instanceof Error ? err.message : String(err);
  console.error("[WebGL / Spark Init Error]", err);
  setStatus("error", "初始化失败", `WebGL 或渲染器初始化异常：${message}`, {
    overlay: true,
    title: "三维渲染器启动失败",
    detail: `${message} — 请确认浏览器已开启 WebGL2 / 硬件加速。`,
  });
}
