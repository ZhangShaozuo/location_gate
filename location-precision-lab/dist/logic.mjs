import model from "./model-data.mjs";
import { roundedCoordinate } from "./android.mjs";
import { cityFixtures } from "./fixtures.mjs";

const lookup = (object, key) => Object.hasOwn(object, key) ? object[key] : undefined;
const token = text => text.normalize("NFKC").replace(/[\s_\-:：、，。！？!?]+/gu, "").toLowerCase();
const ignore = new Set(model.ignored);
const semanticOps = new Set(model.semanticOps);
const sourceNames = new Set(model.positionSources);
const regex = Object.fromEntries(Object.entries(model.patterns).map(([key, pattern]) => {
  const fullMatch = key !== "NEARBY" && key !== "DEVICE_NEARBY";
  return [key, new RegExp(fullMatch ? `^(?:${pattern})$` : pattern, "i")];
}));

function sourceKind(value) {
  const kinds = new Set();
  const { current, named, unknown, saved } = model.histories;
  for (const atom of Array.isArray(value) ? value : [value]) {
    if (typeof atom !== "string") throw new Error("地点槽位须使用字符串或字符串列表。");
    const part = atom.normalize("NFKC").trim().replace(/(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])/gu, "");
    if (!part) continue;
    if (sourceNames.has(part)) kinds.add(part);
    else if (regex.CURRENT.test(part) || regex.DEVICE_NEARBY.test(part)) kinds.add(current);
    else if (regex.NEARBY.test(part) || regex.PRONOUN.test(part) || regex.SYMBOLIC_REFERENCE.test(part)
             || ["本地", "当地", "local"].includes(part)) kinds.add(unknown);
    else if (regex.SAVED_PLACE.test(part)) kinds.add(saved);
    else kinds.add(named);
  }
  return kinds.size === 1 ? [...kinds][0] : unknown;
}

function radiusBand(value) {
  if (typeof value !== "string" && typeof value !== "number") throw new Error("半径须使用数字或带单位的文本。");
  const parts = /^(\d+(?:\.\d+)?)\s*(km|m|公里|千米|米)?$/i.exec(String(value).normalize("NFKC").trim());
  if (!parts) throw new Error("半径支持 350 米、0.35 公里等写法。");
  const [, measurement, unit = "m"] = parts;
  const metres = Number(measurement) * (["km", "公里", "千米"].includes(unit.toLowerCase()) ? 1000 : 1);
  // Accommodate binary rounding at the metre boundary when converting kilometre text.
  const rounded = Math.round(metres);
  if (rounded <= 0 || rounded > 10000000 || Math.abs(metres - rounded) > 1e-8) {
    throw new Error("半径换算后须为正整数米，且不超过 1,000 万米。");
  }
  return rounded <= model.radiusThreshold ? "up_to_policy_limit" : "above_policy_limit";
}

export function normalize(intentText, slots) {
  const intent = lookup(model.intents, token(intentText));
  if (!intent) throw new Error("意图名称未登记。请选一个标准意图或使用已登记的别名。");
  if (!slots || typeof slots !== "object" || Array.isArray(slots)) throw new Error("槽位须填写 JSON 对象，可用 {} 表示空槽位。");
  const parsed = Object.create(null);
  function set(key, value) {
    if (Object.hasOwn(parsed, key) && JSON.stringify(parsed[key]) !== JSON.stringify(value)) throw new Error(`槽位冲突 · ${key}`);
    parsed[key] = value;
  }
  for (const [name, value] of Object.entries(slots)) {
    const field = lookup(model.slotKeys, token(name));
    if (!field) throw new Error(`未知槽位 · ${name}`);
    if (field === "radius_m") {
      set("radius_band", radiusBand(value));
    } else if (Object.hasOwn(model.slotValues, field)) {
      if (typeof value !== "string") throw new Error(`${name} 须使用文本取值。`);
      const canonical = lookup(model.slotValues[field], token(value));
      if (canonical) set(field, canonical);
      else if (field === "op" && /^[a-z][a-z0-9_]*$/.test(value)) set(field, value);
      else throw new Error(`${name} 不支持这个取值 · ${value}`);
    } else {
      set(field, value);
    }
  }
  for (const [source, fields] of Object.entries(model.locationFields)) {
    const evidence = fields.map(field => parsed[field]).find(value => Array.isArray(value) ? value.length : value);
    if (parsed[source] || !evidence) continue;
    const kind = sourceKind(evidence);
    if (kind !== model.histories.unknown) parsed[source] = kind;
  }
  if (!parsed.src && (Array.isArray(parsed.candidates) ? parsed.candidates.length : parsed.candidates)) {
    parsed.src = "previous_entity";
  }
  const retained = Object.keys(parsed).filter(key => !ignore.has(key)).sort();
  return { intent, slots: Object.fromEntries(retained.map(key => [key, parsed[key]])) };
}

export function predict(normalized) {
  const { intent, slots } = normalized;
  const keys = [`intent=${intent}`];
  for (const [key, value] of Object.entries(slots)) {
    if (key === "fence_src" || (key === "op" && !semanticOps.has(value))) continue;
    keys.push(`slot:${key}=${value}`);
  }
  const indices = keys.map(key => lookup(model.features, key)).filter(Number.isInteger);
  const scores = model.bias.map((bias, i) => indices.reduce((sum, feature) => sum + model.weights[i][feature], bias));
  const winner = scores.indexOf(Math.max(...scores));
  return { label: model.classes[winner], reference: lookup(model.rules, JSON.stringify([intent, slots])) };
}

const R = 6371008.8;
const EDGE = 5000;
const PI = Math.PI;

export function gridCenter(latitude, longitude) {
  const rowCount = Math.ceil(PI * R / EDGE);
  const row = Math.min(rowCount - 1, Math.floor((latitude + 90) * rowCount / 180));
  const centerLat = (row + 0.5) * 180 / rowCount - 90;
  const colCount = Math.max(1, Math.ceil(2 * PI * R * Math.cos(centerLat * PI / 180) / EDGE));
  const wrapped = longitude === 180 ? -180 : longitude;
  const column = Math.min(colCount - 1, Math.floor((wrapped + 180) * colCount / 360));
  return {
    latitude: roundedCoordinate(centerLat),
    longitude: roundedCoordinate((column + 0.5) * 360 / colCount - 180),
    nominalCellSizeM: EDGE,
  };
}

const limits = { "城市级模糊": 0, "区域级模糊": 1, "精确": 2 };
const byRank = ["城市级模糊", "区域级模糊", "精确"];

function regionalResult(latitude, longitude, access, method, comparison) {
  if (method === "legacy_5km") {
    // The extra 5 km policy must use the system's coarse output when the app lacks fine access.
    const point = access === "approximate" ? comparison.traditional : { latitude, longitude };
    return {
      action: "返回约 5 km 网格中心",
      reason: access === "approximate" ? "在系统传统模糊坐标上再做实验台 5 km 归格。"
        : "使用实验台原有的约 5 km 网格。",
      payload: { type: "grid_center", ...gridCenter(point.latitude, point.longitude), crs: "WGS84" },
    };
  }
  const useS2 = method === "android_s2" && comparison.level !== null;
  const point = useS2 ? comparison.s2 : comparison.traditional;
  const placement = access === "approximate" ? "模拟系统执行一次模糊化，定位代理沿用该结果。" : "定位代理按 Android 路径模拟模糊化。";
  const explanation = useS2 ? `使用模拟密度档位对应的 S2 Level ${comparison.level}。`
    : method === "android_s2" ? "密度数据不可用，回退到约 2 km 的传统网格。" : "使用约 2 km 的传统网格。";
  return {
    action: useS2 ? "返回 S2 网格中心" : "返回传统网格代表点",
    reason: placement + explanation,
    payload: {
      type: "grid_center", latitude: roundedCoordinate(point.latitude), longitude: roundedCoordinate(point.longitude),
      crs: "WGS84", method: useS2 ? "android_s2" : "android_grid",
      ...(useS2 ? { s2Level: comparison.level } : { nominalCellSizeM: 2000 }),
    },
  };
}

export function applyPolicy(prediction, latitude, longitude, access, cityId, legacy,
  { method = "legacy_5km", comparison } = {}) {
  if (access !== "granted" && access !== "approximate") {
    return { action: "停止返回位置", reason: "模拟系统权限拒绝本次调用。", payload: { status: "location_permission_denied" } };
  }
  const ruleRank = lookup(limits, prediction.reference);
  if (prediction.reference === "不涉及") {
    return { action: "停止返回位置", reason: "该组合无需本机位置。", payload: { status: "location_not_applicable" } };
  }
  if (ruleRank === undefined) {
    return { action: "待复核", reason: "演示只对已核对的语义组合执行坐标策略。此输入仍可查看模型预测。", payload: { status: "needs_review" } };
  }
  const modelRank = limits[prediction.label];
  if (modelRank < ruleRank) {
    return { action: "等待精度确认", reason: "模型给出的精度低于该组合的业务要求，演示暂缓返回位置。", payload: { status: "precision_needs_review" } };
  }
  const tier = byRank[Math.min(modelRank, ruleRank)];
  if (tier === "精确") {
    if (access !== "granted") {
      return { action: "暂停精确定位", reason: "业务需要精确位置，当前系统只授予模糊位置权限。",
        payload: { status: "precise_location_permission_required" } };
    }
    return { action: "保留系统坐标", reason: "业务需要精确位置，模拟系统权限也允许。", payload: { type: "device_location", latitude, longitude, crs: "WGS84" } };
  }
  if (tier === "区域级模糊") {
    return regionalResult(latitude, longitude, access, method, comparison);
  }
  const city = lookup(cityFixtures, cityId);
  if (!city) return { action: "等待城市解析", reason: "请为演示选择一条模拟逆地理编码结果。", payload: { status: "city_unresolved" } };
  if (!legacy) {
    return { action: "只返回城市", reason: "业务使用解析出的城市，坐标字段省略。", payload: { type: "city", cityId, city: city.name } };
  }
  return { action: "换成城市代表点", reason: "经纬度兼容模式下，同一城市使用固定目录代表点。", payload: { type: "city_representative", cityId, city: city.name, latitude: city.latitude, longitude: city.longitude, crs: "WGS84" } };
}
