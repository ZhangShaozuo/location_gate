import model from "./model-data.mjs";
import { normalize, predict, applyPolicy } from "./logic.mjs";
import { advanceOffset, compareAndroid, densityProfiles, distanceMeters, methods, newOffset } from "./android.mjs";
import { cases, cityFixtures, cityForLocation, locations } from "./fixtures.mjs";
import { enableTooltips } from "./tooltips.mjs";

const get = id => document.getElementById(id);
const form = get("experiment");
const examplesById = new Map(cases.map(example => [example.id, example]));
const pretty = value => JSON.stringify(value, null, 2);
const helpByChoice = {
  access: {
    granted: "系统允许提供原始坐标，实验台仍按任务要求决定返回精确、区域级或城市级。",
    approximate: "系统最多提供模糊位置。若任务需要精确位置，实验台会暂停返回。",
    denied: "系统拒绝定位。实验台仍会给出模型标签，工具只返回未授权状态。",
  },
  method: {
    android_grid: "区域级结果先加随机偏移，再按约 2 公里步长取整。",
    android_s2: "区域级结果先加随机偏移，再按模拟密度选取 S2 网格中心。",
    legacy_5km: "区域级结果使用实验台原有的约 5 公里网格，可与两种 Android 路径对照。",
  },
  density: {
    dense: "模拟人口密集地区。Level 13 是本实验台较小的网格。",
    medium: "模拟中等人口密度。Level 12 的网格大小介于另外两档之间。",
    sparse: "模拟人口稀疏地区。Level 10 是本实验台较大的网格。",
    unavailable: "模拟无法取得密度数据。S2 路径会回退到传统网格。",
  },
};
let offset = newOffset();
let offsetHours = 0;
let offsetChange = 0;

function option(select, value, text) {
  const choice = document.createElement("option");
  choice.value = value;
  choice.textContent = text;
  select.append(choice);
}

for (const title of [...new Set(Object.values(model.intents))].sort((a, b) => a.localeCompare(b, "zh-CN"))) {
  option(get("intent-options"), title, title);
}
for (const domain of new Set(cases.map(example => example.domain))) option(get("domain"), domain, domain);
for (const [key, point] of Object.entries(locations)) option(get("point"), key, point.name);
for (const [key, point] of Object.entries(cityFixtures)) option(get("city"), key, point.name);
for (const [key, name] of Object.entries(methods)) option(get("method"), key, name);
for (const [key, profile] of Object.entries(densityProfiles)) option(get("density"), key, profile.label);

function display(label, action, reason, payload, normalized, reference) {
  get("label").textContent = label;
  get("action").textContent = action;
  get("reason").textContent = reason;
  get("reference").textContent = normalized ? `规则参考 · ${reference ?? "待复核"}` : "";
  get("payload").textContent = pretty(payload);
  get("normalized").textContent = normalized ? pretty(normalized) : "暂无有效的标准输入";
  get("copy").disabled = false;
  get("copy").textContent = "复制 JSON";
  document.querySelector(".result").dataset.kind = payload.status ? "blocked" : "available";
}

function showComparison(raw, comparison) {
  const table = get("comparison-data");
  table.replaceChildren();
  const row = (label, point, detail) => {
    const tr = document.createElement("tr");
    const th = document.createElement("th");
    th.scope = "row";
    th.textContent = label;
    tr.append(th);
    const data = point
      ? [point.latitude.toFixed(7), point.longitude.toFixed(7), `${Math.round(distanceMeters(raw, point))} m`, detail]
      : ["—", "—", "—", detail];
    for (const value of data) {
      const td = document.createElement("td");
      td.textContent = value;
      tr.append(td);
    }
    table.append(tr);
  };
  if (!comparison) {
    row("等待坐标", null, "请输入有效的纬度和经度。");
  } else {
    row("原始模拟坐标", raw, "定位服务输入");
    row("加随机偏移", comparison.shifted, "两条路径共用");
    row("传统网格", comparison.traditional, "约 2 km，按纬度换算经度步长");
    row("人口密度 S2", comparison.s2, comparison.level === null
      ? "密度数据不可用，回退到传统网格" : `使用模拟档位 · Level ${comparison.level}`);
  }
  get("offset-status").textContent = offsetHours
    ? `模拟时间 ${offsetHours} 小时 · 本次随机偏移变化 ${offsetChange.toFixed(1)} 米`
    : "";
}

function run() {
  get("input-status").textContent = "";
  for (const [id, descriptions] of Object.entries(helpByChoice)) {
    get(`${id}-help`).textContent = descriptions[get(id).value];
  }
  const latitude = get("lat").valueAsNumber;
  const longitude = get("lon").valueAsNumber;
  let comparison;
  try {
    if (!Number.isFinite(latitude) || Math.abs(latitude) > 90 || !Number.isFinite(longitude) || Math.abs(longitude) > 180) {
      throw new Error("请输入有效的纬度和经度。");
    }
    comparison = compareAndroid(latitude, longitude, offset, get("density").value);
    let slots;
    try { slots = JSON.parse(get("slots").value); }
    catch { throw new Error("槽位 JSON 无法解析。请检查引号、逗号和括号。"); }
    const normalized = normalize(get("intent").value, slots);
    const prediction = predict(normalized);
    const result = applyPolicy(prediction, latitude, longitude, get("access").value, get("city").value,
      get("legacy").checked, { method: get("method").value, comparison });
    display(prediction.label, result.action, result.reason, result.payload, normalized, prediction.reference);
  } catch (error) {
    get("input-status").textContent = "请根据结果区的提示修改输入后重试。";
    display("未判定", "停止返回位置", error.message, { status: "invalid_input" });
  }
  showComparison({ latitude, longitude }, comparison);
}

function renderExampleChoices() {
  const domain = get("domain").value;
  const matching = domain ? cases.filter(example => example.domain === domain) : cases;
  const select = get("example");
  select.replaceChildren();
  const groups = new Map();
  for (const example of matching) {
    let group = groups.get(example.domain);
    if (!group) {
      group = document.createElement("optgroup");
      group.label = example.domain;
      groups.set(example.domain, group);
      select.append(group);
    }
    option(group, example.id, `${example.title} · ${locations[example.location].name}`);
  }
  get("example-count").textContent = `${matching.length} 个`;
}

function applyLocation(id) {
  const point = locations[id];
  if (!Object.hasOwn(locations, id)) return;
  get("lat").value = point.latitude;
  get("lon").value = point.longitude;
  get("city").value = cityForLocation(id);
  get("density").value = point.density;
}

function selectExample(id) {
  const example = examplesById.get(id);
  if (!example) return;
  if (get("domain").value && get("domain").value !== example.domain) {
    get("domain").value = example.domain;
    renderExampleChoices();
  }
  get("example").value = id;
  get("intent").value = example.intent;
  get("slots").value = pretty(example.slots);
  get("point").value = example.location;
  get("access").value = example.access ?? "granted";
  get("legacy").checked = false;
  applyLocation(example.location);
  if (id === "poi-fallback") get("method").value = "android_s2";
  run();
}

get("domain").addEventListener("change", renderExampleChoices);
get("load-example").addEventListener("click", () => selectExample(get("example").value));
form.addEventListener("submit", event => { event.preventDefault(); run(); });
form.addEventListener("input", event => {
  if (event.target.id === "lat" || event.target.id === "lon") {
    get("point").value = "";
    get("city").value = "";
  }
  get("input-status").textContent = "输入已更改，运行判定后更新结果。";
});
get("point").addEventListener("change", () => {
  applyLocation(get("point").value);
  if (!get("point").value) get("city").value = "";
  run();
});
for (const id of ["method", "density", "access", "city", "legacy"]) get(id).addEventListener("change", run);
get("advance-offset").addEventListener("click", () => {
  const next = advanceOffset(offset);
  offsetChange = Math.hypot(next.latitudeM - offset.latitudeM, next.longitudeM - offset.longitudeM);
  offset = next;
  offsetHours += 1;
  run();
});
get("copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(get("payload").textContent);
    get("copy").textContent = "已复制";
  } catch {
    get("copy").textContent = "请选中并复制";
  }
});

get("method").value = "android_grid";
renderExampleChoices();
selectExample("nearby");
enableTooltips();
