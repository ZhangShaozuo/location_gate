import io
import json
from pathlib import Path
import sqlite3
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from corpora.adapters import adapt_crosswoz, adapt_risawoz, adapt_sgd, adapt_cmpa, adapt_massive
from corpora.schema import NEEDS_REVIEW, NOT_APPLICABLE, PRECISION_CLASSES, make_intent, precision_for
from corpora.sources import download, sgd_records
from prepare import deduplicate, init_database, make_row, quotas, sample, write_device_find_contrasts


class DialogueTests(unittest.TestCase):
    def test_crosswoz_reference_and_future_task(self):
        dialogue = {
            "goal": [[3, "出租", "出发地", "未来任务", False]],
            "messages": [
                {"role": "usr", "content": "推荐餐馆", "dialog_act": [["Request", "餐馆", "名称", ""]]},
                {"role": "sys", "content": "推荐同行餐馆",
                 "dialog_act": [["Inform", "餐馆", "名称", "同行餐馆"]]},
                {"role": "usr", "content": "他家周边有什么景点？",
                 "dialog_act": [["Request", "餐馆", "周边景点", ""]]},
                {"role": "sys", "content": "有春风公园",
                 "dialog_act": [["Inform", "景点", "名称", "春风公园"]]},
            ],
        }
        first, second = adapt_crosswoz(dialogue, 6)
        self.assertEqual(first.intent["intent_id"], "restaurant.search")
        self.assertNotIn("未来任务", json.dumps(first.intent, ensure_ascii=False))
        self.assertEqual(second.intent["intent_id"], "restaurant.details")
        self.assertEqual(second.intent["parameters"]["reference_place"], "同行餐馆")
        self.assertEqual(precision_for(second.intent).tier, NOT_APPLICABLE)
        self.assertNotIn(("assistant", "有春风公园"), second.context)

    def test_risawoz_keeps_current_domains_separate(self):
        dialogue = {"dialogue": [{
            "user_utterance": "这里的营业时间？另外看看苏州明天的天气",
            "system_utterance": "后续答案",
            "user_actions": [
                ["Request", "旅游景点", "开放时间", ""],
                ["Inform", "天气", "日期", "明天"],
            ],
            "belief_state": {
                "inform slot-values": {
                    "旅游景点-名称": "金鸡湖 景区", "天气-城市": "苏州",
                    "酒店-名称": "另一任务",
                },
                "turn request": ["开放时间"],
            },
        }]}
        a, b = adapt_risawoz(dialogue, 5)
        self.assertEqual(a.intent["intent_id"], "place.details")
        self.assertEqual(a.intent["parameters"]["reference_place"], "金鸡湖景区")
        self.assertEqual(a.intent["parameters"]["requested_slots"], ["opening_hours"])
        self.assertEqual(b.intent["intent_id"], "weather.query")
        self.assertEqual(b.intent["parameters"]["location"], "苏州")
        self.assertNotIn("requested_slots", b.intent["parameters"])
        self.assertEqual(len(a.context), 1)

    def test_sgd_preserves_separate_frames_and_confirmation(self):
        ride = {"service": "RideSharing_1", "state": {
            "active_intent": "GetRide",
            "slot_values": {"destination": ["Airport"], "pickup_location": ["current location"]},
        }, "actions": [{"act": "AFFIRM"}]}
        weather = {"service": "Weather_1", "state": {
            "active_intent": "GetWeather", "slot_values": {"city": ["San Jose"]},
        }}
        turns = [
            {"speaker": "SYSTEM", "utterance": "Confirm the ride?", "frames": [
                {"service": "RideSharing_1", "actions": [{"act": "CONFIRM"}]},
            ]},
            {"speaker": "USER", "utterance": "Yes. And check the weather.", "frames": [ride, weather]},
        ]
        a, b = adapt_sgd({"turns": turns}, 8)
        self.assertEqual(a.intent["parameters"]["confirmation"], "confirmed")
        self.assertEqual(precision_for(a.intent).tier, "精确")
        self.assertEqual(precision_for(b.intent).tier, "城市级")
        self.assertEqual(a.turn, b.turn)
        ride["actions"] = [{"act": "NEGATE"}]
        self.assertEqual(precision_for(next(adapt_sgd({"turns": turns}, 8)).intent).tier, "精确")

    def test_cmpa_keeps_destination_distinct_from_pickup(self):
        row = {"input": "帮我现在叫辆出租车去机场", "output": "打车: [目的地: 机场]"}
        a = next(adapt_cmpa(row))
        self.assertEqual(a.intent["parameters"]["pickup_source"], "unknown")
        self.assertEqual(a.intent["parameters"]["destination"], "机场")
        self.assertEqual(precision_for(a.intent).tier, "精确")

    def test_cmpa_keeps_colons_within_time_value(self):
        row = {"input": "明天早上七点开会", "output": "设置闹钟: [时间: 07:00, 事件: 开会]"}
        self.assertEqual(next(adapt_cmpa(row)).intent["parameters"]["time"], "07:00")

    def test_alarm_without_location_and_location_trigger(self):
        ordinary = make_intent("alarm.set", [("time", "七点")], text="七点设置闹钟", single_turn=True)
        triggered = make_intent("alarm.set", [], text="到家以后提醒我", single_turn=True)
        after_email = make_intent("alarm.set", [], text="收到邮件后十五分钟定个闹钟", single_turn=True)
        self.assertEqual(precision_for(ordinary).record(), {"precision": NOT_APPLICABLE, "coarse_level": None})
        self.assertEqual(precision_for(triggered).tier, NEEDS_REVIEW)
        self.assertEqual(precision_for(after_email).tier, NOT_APPLICABLE)

    def test_country_is_reserved_for_device_country_request(self):
        country = make_intent("location.self", [], text="我在哪个国家", single_turn=True)
        self.assertEqual(precision_for(country).record(), {"precision": "模糊", "coarse_level": "国家级"})
        unknown = make_intent("cmpa.其他意图", [], text="把我现在的位置发出去", single_turn=True)
        self.assertEqual(precision_for(unknown).record(), {"precision": None, "coarse_level": None})


class PipelineTests(unittest.TestCase):
    def test_scope_filter_applies_to_all_splits(self):
        with sqlite3.connect(":memory:") as db:
            init_database(db)
            for index, split in enumerate(("train", "dev", "test")):
                for tier in ("精确", NOT_APPLICABLE, NEEDS_REVIEW):
                    key = f"{split}:{tier}"
                    db.execute("INSERT INTO candidates VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (
                        key, "cmpa", split, index, tier, index, key, key, "intent", "意图", 0, "{}",
                    ))
            deduplicate(db)
            options = SimpleNamespace(
                include_not_applicable=False, max_train=None, max_train_per_class=None,
                train_sampling="natural",
            )
            sample(db, options)
            self.assertEqual(set(db.execute("SELECT id FROM selected")), {
                (f"{split}:精确",) for split in ("train", "dev", "test")
            })
            db.execute("DELETE FROM selected")
            options.include_not_applicable = True
            sample(db, options)
            self.assertEqual(set(db.execute("SELECT id FROM selected")), {
                (f"{split}:{tier}",) for split in ("train", "dev", "test")
                for tier in ("精确", NOT_APPLICABLE)
            })

    def test_dedupe_prefers_test_over_train(self):
        with sqlite3.connect(":memory:") as db:
            init_database(db)
            for index, split in enumerate(("train", "dev", "test")):
                db.execute("INSERT INTO candidates VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (
                    split, "cmpa", split, index, "区域级", index,
                    "same_digest", "a", "location.self", "查询当前位置", 0, "{}",
                ))
            deduplicate(db)
            self.assertEqual(db.execute("SELECT split FROM eligible").fetchall(), [("test",)])

    def test_balanced_no_duplication(self):
        caps = dict(zip(PRECISION_CLASSES, (2, 100, 100, 100)))
        result = quotas(caps, 32, "balanced", PRECISION_CLASSES)
        self.assertEqual(list(result.values()), [2, 10, 10, 10])
        result = quotas(caps, 5, "natural", PRECISION_CLASSES)
        self.assertEqual(sum(result.values()), 5)
        self.assertGreater(result["精确"], 0)

    def test_sgd_tar_members_stream_without_extracting(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with tarfile.open(root / "sgd.tar.gz", "w:gz") as archive:
                for split in ("train", "dev", "test"):
                    payload = json.dumps([{"dialogue_id": split}]).encode()
                    item = tarfile.TarInfo(f"sgd-revision/{split}/dialogues_001.json")
                    item.size = len(payload)
                    archive.addfile(item, io.BytesIO(payload))
            self.assertEqual(
                list(sgd_records(root)),
                [(split, {"dialogue_id": split}) for split in ("train", "dev", "test")],
            )

    def test_failed_download_does_not_publish_partial_file(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "archive.zip"
            response = io.BytesIO(b"short")
            response.headers = {"Content-Length": "20"}
            with patch("corpora.sources.urlopen", return_value=response):
                with self.assertRaises(OSError):
                    download("https://example.test/file", target, None, 1, 0)
            self.assertEqual(list(target.parent.iterdir()), [])


class LivePolicyTests(unittest.TestCase):
    def check(self, code, fields, tier, requirements=None):
        decision = precision_for({"intent_id": code, "parameters": fields})
        self.assertEqual(decision.tier, tier, code)
        self.assertEqual(decision.requirements(), requirements or {}, code)

    def test_live_rows_have_the_expected_precision_and_scope(self):
        current = {"location_source": "device_current"}
        origin = {"origin_source": "device_current"}
        cases = [
            ("route.query", origin, "精确"),
            ("route.estimate", origin, "精确"),
            ("navigation.start", origin, "精确", {"mode": "continuous"}),
            ("weather.query", current, "城市级"),
            ("weather.alert", current, "城市级"),
            ("location.self", {}, "精确", {"notice": "prompt"}),
            ("place.search", current, "精确", {"notice": "notify"}),
            ("ride.order", {"pickup_source": "device_current"}, "精确"),
            ("transit.flight_ticket", origin, "城市级"),
            ("transit.rail_ticket", origin, "城市级"),
            ("transit.flight_traffic", current, "城市级"),
            ("transit.bus_query", current, "精确"),
            ("transit.ride_code", current, "城市级"),
            ("device.find", {"operation": "query_target_location"}, "精确"),
            ("fitness.start", current, "精确", {"notice": "notify", "mode": "continuous"}),
            ("fitness.history", {"location_source": "stored_history"}, "区域级", {"mode": "route_overview"}),
            ("package.ship", {"address_source": "device_current"}, "精确"),
            ("package.receive", {"address_source": "device_current"}, "精确"),
            ("local_service.search", current, "城市级"),
            ("travel.index", current, "城市级"),
            ("jobs.search", current, "城市级"),
            ("delivery.order", {"delivery_source": "device_current"}, "精确"),
            ("restaurant.reserve", current, "城市级"),
            ("calendar.update", current, "城市级"),
            ("calendar.remove", current, "城市级"),
            ("reminder.create", current, "城市级"),
            ("note.create", current, "城市级"),
            ("information.capture", current, "城市级"),
        ]
        for case in cases:
            with self.subTest(intent=case[0]):
                self.check(*case)

    def test_call_precision_is_independent_of_supplied_addresses(self):
        fixed = {"origin_source": "named_place", "destination_source": "named_place"}
        for params in (fixed, {}, {"origin_source": "named_place"}):
            self.check("route.query", params, "精确")
            self.check("transit.rail_ticket", params, "城市级")
            self.check("transit.bus_query", params, "精确")
        self.check("ride.order", {"destination_source": "device_current"}, "精确")
        self.check("delivery.order", {"delivery_source": "saved_place"}, "精确")
        self.check("weather.query", {"location_source": "named_place"}, "城市级")
        self.check("weather.query", {}, "城市级")
        self.check("location.self", {"requested_granularity": "coarse_unspecified"}, "城市级", {"notice": "prompt"})
        self.check("device.find", {"location_source": "device_current"}, NEEDS_REVIEW)
        self.check("device.find", {"operation": "ring", "location_source": "target_device"}, NOT_APPLICABLE)
        self.check("device.find_menu", {}, NOT_APPLICABLE)
        self.check("package.status", {}, NOT_APPLICABLE)
        self.check("fitness.activity_types", {}, NOT_APPLICABLE)
        self.check("fitness.start", {"tracking_mode": "no_route"}, NOT_APPLICABLE)
        self.check("reminder.create", {"trigger_type": "geofence"}, "城市级")
        self.check("calendar.update", {"time": "17:00"}, "城市级")

    def test_reference_stays_outside_the_intent_and_the_label(self):
        raw = {"input": "告诉我当前位置", "output": "查询当前位置: [内容: 整句文本]"}
        candidate = next(adapt_cmpa(raw))
        row, tier = make_row(candidate, "cmpa", "train", "example", 0, True)
        self.assertEqual(tier, "精确")
        self.assertEqual(row["annotation"]["location_requirements"], {"notice": "prompt"})
        self.assertEqual(row["reference"]["utterance"], raw["input"])
        self.assertNotIn("reference", row["model_input"])
        params = row["model_input"]["intent_with_parameters"]["parameters"]
        self.assertNotIn("内容", params)
        self.assertNotIn("device_location_cue", params)

    def test_named_poi_proximity_is_not_inferred_as_device_input(self):
        unbound = make_intent("place.search", [], text="图书馆附近的咖啡店", single_turn=True)
        bound = make_intent("place.search", [], text="我附近的咖啡店", single_turn=True)
        self.assertEqual(unbound["parameters"]["location_source"], "unknown")
        self.assertEqual(precision_for(unbound).tier, "精确")
        self.assertEqual(precision_for(bound).tier, "精确")

    def test_source_intent_wins_over_a_conflicting_reference_text(self):
        row = {
            "utt": "这道菜多少钱", "intent": "takeaway_order", "annot_utt": "这道菜多少钱",
        }
        intent = next(adapt_massive(row)).intent
        self.assertEqual(intent["intent_id"], "delivery.order")
        self.assertEqual(precision_for(intent).tier, "精确")
        how_to = next(adapt_cmpa({"input": "如何查看我的当前位置", "output": "查询当前位置: []"}))
        self.assertEqual(precision_for(how_to.intent).tier, "精确")

    def test_named_rail_stations_are_normalized_to_their_roles(self):
        item = next(adapt_cmpa({
            "input": "西安到郑州的动车票还有吗",
            "output": "订火车票: [始发站: 西安, 终点站: 郑州]",
        }))
        params = item.intent["parameters"]
        self.assertEqual((params["origin"], params["destination"]), ("西安", "郑州"))
        self.assertEqual(precision_for(item.intent).tier, "城市级")

    def test_device_contrasts_match_except_for_operation(self):
        with tempfile.TemporaryDirectory() as folder:
            metadata = write_device_find_contrasts(Path(folder), True)
            self.assertEqual(metadata["classes"], {"精确": 3, "不涉及": 3})
            with (Path(folder) / metadata["path"]).open(encoding="utf-8") as stream:
                rows = list(map(json.loads, stream))
        for locate, ring in zip(rows[::2], rows[1::2], strict=True):
            self.assertEqual(locate["group_id"], ring["group_id"])
            self.assertEqual(locate["split"], "train")
            self.assertEqual(ring["split"], "train")
            self.assertTrue(locate["reference"]["synthetic"])
            a = locate["model_input"]["intent_with_parameters"]
            b = ring["model_input"]["intent_with_parameters"]
            self.assertEqual(a["intent_id"], "device.find")
            self.assertEqual(a["parameters"].pop("operation"), "query_target_location")
            self.assertEqual(b["parameters"].pop("operation"), "ring")
            self.assertEqual(a, b)
            self.assertEqual((locate["label"]["precision"], ring["label"]["precision"]), ("精确", "不涉及"))


if __name__ == "__main__":
    unittest.main()
