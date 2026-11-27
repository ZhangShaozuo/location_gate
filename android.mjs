const METERS_PER_DEGREE = 111_000;
const GRID_STEP_M = 2_000;
const MAX_LATITUDE = 90 - 1 / METERS_PER_DEGREE;
const RAD = Math.PI / 180;
const CHANGE = 0.03;
const RETAIN = Math.sqrt(1 - CHANGE ** 2);

// These profiles are lab inputs. Android's density service provides the actual levels.
export const densityProfiles = Object.freeze({
  dense: { label: "高密度 · Level 13", level: 13 },
  medium: { label: "中密度 · Level 12", level: 12 },
  sparse: { label: "低密度 · Level 10", level: 10 },
  unavailable: { label: "密度数据不可用", level: null },
});

export const methods = Object.freeze({
  android_grid: "Android 传统网格（约 2 km）",
  android_s2: "Android 人口密度 S2 网格",
  legacy_5km: "实验台原有网格（约 5 km）",
});

const wrappedLongitude = lon => lon >= -180 && lon < 180 ? lon : ((lon + 180) % 360 + 360) % 360 - 180;
const limitedLatitude = lat => Math.min(MAX_LATITUDE, Math.max(-MAX_LATITUDE, lat));
const toLongitudeDegrees = (meters, latitude) => meters / METERS_PER_DEGREE / Math.cos(latitude * RAD);
export const roundedCoordinate = value => Number(value.toFixed(7));

function gaussian() {
  const values = crypto.getRandomValues(new Uint32Array(2));
  const u = (values[0] + 1) / (2 ** 32 + 1);
  const v = values[1] / 2 ** 32;
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

export function newOffset(sample = gaussian) {
  const standardDeviation = GRID_STEP_M / 4;
  return { latitudeM: sample() * standardDeviation, longitudeM: sample() * standardDeviation };
}

export function advanceOffset(offset, sample = gaussian) {
  const next = newOffset(sample);
  return {
    latitudeM: RETAIN * offset.latitudeM + CHANGE * next.latitudeM,
    longitudeM: RETAIN * offset.longitudeM + CHANGE * next.longitudeM,
  };
}

export function addOffset(latitude, longitude, offset) {
  const lat = limitedLatitude(latitude);
  return {
    latitude: lat + offset.latitudeM / METERS_PER_DEGREE,
    longitude: wrappedLongitude(longitude) + wrappedLongitude(toLongitudeDegrees(offset.longitudeM, lat)),
  };
}

export function traditionalGrid(point) {
  const latStep = GRID_STEP_M / METERS_PER_DEGREE;
  const latitude = limitedLatitude(Math.round(point.latitude / latStep) * latStep);
  const lonStep = toLongitudeDegrees(GRID_STEP_M, latitude);
  const longitude = wrappedLongitude(Math.round(point.longitude / lonStep) * lonStep);
  return { latitude, longitude };
}

function faceAndUv(x, y, z) {
  const ax = Math.abs(x), ay = Math.abs(y), az = Math.abs(z);
  if (ax > ay && ax > az) return x > 0 ? [0, y / x, z / x] : [3, z / x, y / x];
  if (ay > az) return y > 0 ? [1, -x / y, z / y] : [4, z / y, -x / y];
  return z > 0 ? [2, -x / z, -y / z] : [5, -y / z, -x / z];
}

function faceUvToXyz(face, u, v) {
  switch (face) {
    case 0: return [1, u, v];
    case 1: return [-u, 1, v];
    case 2: return [-u, -v, 1];
    case 3: return [-1, -v, -u];
    case 4: return [v, -1, -u];
    default: return [v, u, -1];
  }
}

// S2 quadratic projection. Cell centers only require face/i/j, so a Hilbert cell ID is unnecessary.
const uvToSt = u => u >= 0 ? 0.5 * Math.sqrt(1 + 3 * u) : 1 - 0.5 * Math.sqrt(1 - 3 * u);
const stToUv = s => s >= 0.5 ? (4 * s * s - 1) / 3 : (1 - 4 * (1 - s) ** 2) / 3;

export function s2Grid(point, level) {
  if (!Number.isInteger(level) || level < 0 || level > 30) throw new Error("S2 层级须在 0 至 30 之间。");
  const lat = point.latitude * RAD, lon = wrappedLongitude(point.longitude) * RAD;
  const [face, u, v] = faceAndUv(Math.cos(lat) * Math.cos(lon), Math.cos(lat) * Math.sin(lon), Math.sin(lat));
  const width = 2 ** level;
  const center = value => stToUv((Math.max(0, Math.min(width - 1, Math.floor(uvToSt(value) * width))) + 0.5) / width);
  const [x, y, z] = faceUvToXyz(face, center(u), center(v));
  return { latitude: Math.atan2(z, Math.hypot(x, y)) / RAD, longitude: Math.atan2(y, x) / RAD };
}

export function compareAndroid(latitude, longitude, offset, profile) {
  if (!Object.hasOwn(densityProfiles, profile)) throw new Error("请选择有效的人口密度模拟档位。");
  const shifted = addOffset(latitude, longitude, offset);
  const traditional = traditionalGrid(shifted);
  const level = densityProfiles[profile].level;
  return { shifted, traditional, s2: level === null ? traditional : s2Grid(shifted, level), level };
}

export function distanceMeters(a, b) {
  const dLat = (b.latitude - a.latitude) * RAD;
  const dLon = (b.longitude - a.longitude) * RAD;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.latitude * RAD) * Math.cos(b.latitude * RAD) * Math.sin(dLon / 2) ** 2;
  return 2 * 6_371_008.8 * Math.asin(Math.sqrt(Math.min(1, Math.max(0, h))));
}
