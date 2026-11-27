import assert from "node:assert/strict";
import test from "node:test";
import { advanceOffset, compareAndroid, newOffset, s2Grid, traditionalGrid } from "../dist/android.mjs";
import { cases, cityForLocation, locations } from "../dist/fixtures.mjs";
import { applyPolicy, normalize, predict } from "../dist/logic.mjs";

const offset = { latitudeM: 250, longitudeM: -120 };
const stopStatuses = {
  "不涉及": "location_not_applicable",
  "exact-denied": "precise_location_permission_required",
  "unresolved": "city_unresolved",
};

function simulate(example, method, profile = locations[example.location].density, access = example.access ?? "granted") {
  const { latitude, longitude } = locations[example.location];
  const comparison = compareAndroid(latitude, longitude, offset, profile);
  const prediction = predict(normalize(example.intent, example.slots));
  return applyPolicy(prediction, latitude, longitude, access, cityForLocation(example.location), false, { method, comparison });
}

test("fixed-distance angular steps account for latitude and wrap the antimeridian", () => {
  const equator = traditionalGrid({ latitude: 0, longitude: 0.018 });
  const high = traditionalGrid({ latitude: 60, longitude: 0.04 });
  assert.ok(Math.abs(equator.longitude - 0.018018018) < 1e-8);
  assert.ok(Math.abs(high.longitude - 0.036036036) < 1e-8);
  assert.ok(traditionalGrid({ latitude: 0, longitude: 180.01 }).longitude < 0);
});

test("S2 center matches reference for Shenzhen and a latitude/longitude wrap", () => {
  const point = { latitude: 22.531472, longitude: 114.047613 };
  const center = s2Grid(point, 11);
  assert.ok(Math.abs(center.latitude - 22.555104545388456) < 1e-10);
  assert.ok(Math.abs(center.longitude - 114.02501398884053) < 1e-10);
  assert.deepEqual(s2Grid({ latitude: 5.2, longitude: 180 }, 12),
    s2Grid({ latitude: 5.2, longitude: -180 }, 12));
});

test("both Android paths use the same offset and density unavailability falls back", () => {
  const p = locations.shenzhen;
  const comparison = compareAndroid(p.latitude, p.longitude, offset, "dense");
  assert.deepEqual(comparison.traditional, traditionalGrid(comparison.shifted));
  assert.deepEqual(comparison.s2, s2Grid(comparison.shifted, 13));
  assert.deepEqual(compareAndroid(p.latitude, p.longitude, offset, "sparse").s2, s2Grid(comparison.shifted, 10));
  const fallback = compareAndroid(p.latitude, p.longitude, offset, "unavailable");
  assert.equal(fallback.level, null);
  assert.deepEqual(fallback.s2, fallback.traditional);
  assert.deepEqual(newOffset(() => 1), { latitudeM: 500, longitudeM: 500 });
  assert.deepEqual(advanceOffset({ latitudeM: 0, longitudeM: 0 }, () => 1), { latitudeM: 15, longitudeM: 15 });
});

test("all catalog examples honor their reference tier, authorization, and precision", () => {
  assert.equal(new Set(cases.map(example => example.id)).size, cases.length);
  for (const example of cases) {
    const prediction = predict(normalize(example.intent, example.slots));
    assert.equal(prediction.reference, example.expected, example.id);
    if (example.expected !== "不涉及") assert.equal(prediction.label, example.expected, example.id);
    for (const method of ["android_grid", "android_s2", "legacy_5km"]) {
      const { payload } = simulate(example, method);
      const city = cityForLocation(example.location);
      if (example.access === "denied") {
        assert.deepEqual(payload, { status: "location_permission_denied" }, example.id);
      } else if (example.access === "approximate" && example.expected === "精确") {
        assert.deepEqual(payload, { status: stopStatuses["exact-denied"] }, example.id);
      } else if (example.expected === "不涉及") {
        assert.deepEqual(payload, { status: stopStatuses["不涉及"] }, example.id);
      } else if (example.expected === "城市级模糊") {
        if (city) assert.deepEqual(Object.keys(payload), ["type", "cityId", "city"], example.id);
        else assert.deepEqual(payload, { status: stopStatuses.unresolved }, example.id);
      } else if (example.expected === "区域级模糊") {
        assert.equal(payload.type, "grid_center", example.id);
        assert.ok(!Object.hasOwn(payload, "shifted"), example.id);
        if (method === "android_s2") assert.equal(payload.method,
          locations[example.location].density === "unavailable" ? "android_grid" : "android_s2", example.id);
      } else {
        assert.equal(payload.type, "device_location", example.id);
      }
    }
  }
});

test("an approximate system grant uses one Android processing pass", () => {
  const example = cases.find(candidate => candidate.id === "nearby");
  for (const method of ["android_grid", "android_s2"]) {
    assert.deepEqual(simulate(example, method, "dense", "approximate").payload,
      simulate(example, method, "dense", "granted").payload);
  }
});
