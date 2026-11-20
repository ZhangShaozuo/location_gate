import io
import json
from pathlib import Path
import sqlite3
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from corpora.adapters import adapt_crosswoz, adapt_risawoz, adapt_sgd, adapt_cmpa, adapt_massive, adapt_smp2019
from corpora.schema import NEEDS_REVIEW, NOT_APPLICABLE, PRECISION_CLASSES, make_intent, precision_for
from corpora.sources import download, sgd_records
from prepare import (
    deduplicate, init_database, make_row, quotas, sample,
    write_device_find_contrasts, write_self_location_contrasts,
)


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

    def test_crosswoz_uses_same_turn_place_as_reference(self):
        actions = [
            ["Inform", "景点", "名称", "念坛公园"],
            ["Select", "餐馆", "源领域", "景点"],
            ["Request", "餐馆", "名称", ""],
        ]
        turn = {"role": "usr", "content": "念坛公园附近有什么餐馆？", "dialog_act": actions}
        older = {"role": "sys", "content": "可以去人民大会堂",
                 "dialog_act": [["Inform", "景点", "名称", "人民大会堂"]]}
        restaurant, = adapt_crosswoz({"messages": [older, turn]}, 6)
        self.assertEqual(restaurant.intent["intent_id"], "restaurant.search")
        self.assertEqual(restaurant.intent["parameters"]["reference_place"], "念坛公园")
        self.assertEqual(restaurant.intent["parameters"]["location_source"], "named_place")

        turn["dialog_act"] = [*actions, ["Request", "景点", "电话", ""]]
        attraction, restaurant = adapt_crosswoz({"messages": [older, turn]}, 6)
        self.assertEqual(attraction.intent["intent_id"], "place.details")
        self.assertEqual(restaurant.intent["intent_id"], "restaurant.search")

    def test_crosswoz_named_hotel_attributes_are_details(self):
        turns = [
            {"role": "sys", "content": "推荐同行酒店",
             "dialog_act": [["Inform", "酒店", "名称", "同行酒店"]]},
            {"role": "usr", "content": "这家酒店是什么类型，提供吹风机吗？",
             "dialog_act": [["Request", "酒店", "酒店类型", ""],
                            ["Request", "酒店", "酒店设施-吹风机", ""]]},
        ]
        hotel, = adapt_crosswoz({"messages": turns}, 6)
        self.assertEqual(hotel.intent["intent_id"], "hotel.details")
        self.assertEqual(precision_for(hotel.intent).tier, NOT_APPLICABLE)

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
        self.assertEqual(precision_for(b.intent).tier, NOT_APPLICABLE)
        self.assertEqual(a.turn, b.turn)
        ride["actions"] = [{"act": "NEGATE"}]
        self.assertEqual(precision_for(next(adapt_sgd({"turns": turns}, 8)).intent).tier, "精确")

    def test_cmpa_keeps_destination_distinct_from_pickup(self):
        row = {"input": "帮我现在叫辆出租车去机场", "output": "打车: [目的地: 机场]"}
        a = next(adapt_cmpa(row))
        self.assertEqual(a.intent["parameters"]["pickup_source"], "unknown")
        self.assertEqual(a.intent["parameters"]["destination"], "机场")
        self.assertEqual(precision_for(a.intent).tier, NEEDS_REVIEW)

    def test_cmpa_keeps_colons_within_time_value(self):
        row = {"input": "明天早上七点开会", "output": "设置闹钟: [时间: 07:00, 事件: 开会]"}
        self.assertEqual(next(adapt_cmpa(row)).intent["parameters"]["time"], "07:00")

    def test_alarm_without_location_and_location_trigger(self):
        ordinary = make_intent("alarm.set", [("time", "七点")], text="七点设置闹钟", single_turn=True)
        triggered = make_intent("alarm.set", [], text="到家以后提醒我", single_turn=True)
        after_email = make_intent("alarm.set", [], text="收到邮件后十五分钟定个闹钟", single_turn=True)
        self.assertEqual(precision_for(ordinary).record(), {"precision": NOT_APPLICABLE, "coarse_level": None})
        self.assertEqual(precision_for(triggered).tier, "精确")
        self.assertEqual(precision_for(after_email).tier, NOT_APPLICABLE)

    def test_country_is_reserved_for_device_country_request(self):
        country = make_intent("location.self", [], text="我在哪个国家", single_turn=True)
        self.assertEqual(precision_for(country).record(), {"precision": "模糊", "coarse_level": "国家级"})
        unknown = make_intent("cmpa.未收录意图", [], text="把我现在的位置发出去", single_turn=True)
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
                include_not_applicable=False, max_train=None, max_train_per_class=None, max_train_per_source=None,
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

    def test_training_source_cap_keeps_held_out_records(self):
        with sqlite3.connect(":memory:") as db:
            init_database(db)
            db_rows = []
            for dataset in ("massive", "crosswoz"):
                for split, size in (("train", 9), ("dev", 4)):
                    for i in range(size):
                        key = f"{dataset}:{split}:{i}"
                        tier = "精确" if i % 2 else "城市级"
                        db_rows.append((key, dataset, split, 0, tier, i, key, key, "intent", "意图", 0, "{}"))
            db.executemany("INSERT INTO candidates VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", db_rows)
            deduplicate(db)
            sample(db, SimpleNamespace(include_not_applicable=False, max_train=None, max_train_per_class=None,
                                       max_train_per_source=3, train_sampling="balanced"))
            self.assertEqual(list(db.execute("""
                SELECT dataset, split, COUNT(*) FROM eligible JOIN selected USING(id)
                GROUP BY dataset, split ORDER BY dataset, split
            """)), [(ds, sp, n) for ds in ("crosswoz", "massive") for sp, n in (("dev", 4), ("train", 3))])

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
            ("place.search", current, "区域级"),
            ("place.search", {**current, "search_scope": "nearest"}, "精确", {"notice": "notify"}),
            ("ride.order", {"pickup_source": "device_current"}, "精确"),
            ("transit.flight_ticket", origin, "城市级"),
            ("transit.rail_ticket", origin, "城市级"),
            ("transit.flight_traffic", current, "城市级"),
            ("transit.bus_query", current, "区域级"),
            ("transit.ride_code", current, "城市级"),
            ("device.find", {"operation": "query_target_location"}, NOT_APPLICABLE),
            ("device.find", {"operation": "navigate_to_target"}, "精确", {"mode": "continuous"}),
            ("fitness.start", current, "精确", {"notice": "notify", "mode": "continuous"}),
            ("fitness.history", {"location_source": "stored_history"}, NOT_APPLICABLE),
            ("package.ship", {"address_source": "device_current"}, "精确"),
            ("package.receive", {"address_source": "device_current"}, "精确"),
            ("local_service.search", current, "城市级"),
            ("travel.index", current, "城市级"),
            ("jobs.search", current, "城市级"),
            ("delivery.order", {"address_source": "device_current"}, "精确"),
            ("delivery.order", {}, "精确"),
            ("restaurant.reserve", current, "城市级"),
            ("calendar.update", current, NOT_APPLICABLE),
            ("calendar.remove", current, NOT_APPLICABLE),
            ("reminder.create", current, NOT_APPLICABLE),
            ("note.create", {**current, "operation": "share_current_location"}, "城市级"),
            ("information.capture", current, NOT_APPLICABLE),
        ]
        for case in cases:
            with self.subTest(intent=case[0]):
                self.check(*case)

    def test_fixed_addresses_cover_roles_independently(self):
        fixed = {"origin_source": "named_place", "destination_source": "named_place"}
        for code in ("route.query", "transit.rail_ticket", "transit.bus_query"):
            self.check(code, fixed, NOT_APPLICABLE)
        self.check("route.query", {"origin_source": "named_place"}, NEEDS_REVIEW)
        self.check("transit.rail_ticket", {"destination_source": "named_place"}, "城市级")
        self.check("ride.order", {"destination_source": "device_current"}, NEEDS_REVIEW)
        self.check("delivery.order", {"address_source": "saved_place"}, NOT_APPLICABLE)
        self.check("weather.query", {"location_source": "named_place"}, NOT_APPLICABLE)
        self.check("weather.query", {}, "城市级")
        self.check("location.self", {"requested_granularity": "coarse_unspecified"}, "城市级", {"notice": "prompt"})
        self.check("device.find", {"location_source": "device_current"}, NEEDS_REVIEW)
        self.check("device.find", {"operation": "unknown"}, NEEDS_REVIEW)
        self.check("device.find", {"operation": "ring", "location_source": "target_device"}, NOT_APPLICABLE)
        self.check("device.find_menu", {}, NOT_APPLICABLE)
        self.check("package.status", {}, NOT_APPLICABLE)
        self.check("fitness.activity_types", {}, NOT_APPLICABLE)
        self.check("fitness.start", {"tracking_mode": "no_route"}, NOT_APPLICABLE)
        self.check("reminder.create", {"trigger_type": "geofence"}, "精确")
        self.check("calendar.update", {"time": "17:00"}, NOT_APPLICABLE)

    def test_reviewed_fact_social_and_app_intents_do_not_use_location(self):
        codes = (
            "cmpa.其他意图", "cmpa.搜索查询互联网", "massive.qa_factoid",
            "massive.social_query", "cmpa.发送短信", "cmpa.通过微信发送消息",
            "cmpa.小程序/公众号", "cmpa.支付宝功能", "cmpa.在指定应用中按关键字搜索",
            "cmpa.买东西", "cmpa.查询应用里的图片",
        )
        for code in codes:
            with self.subTest(intent=code):
                self.check(code, {}, NOT_APPLICABLE)

    def test_social_post_current_location_requires_an_explicit_operation(self):
        intent = make_intent("massive.social_post", [("操作", "显示当前位置")])
        self.assertEqual(intent["parameters"], {"operation": "share_current_location"})
        self.assertEqual(precision_for(intent).record(), {"precision": "模糊", "coarse_level": "城市级"})
        self.check("social.post", intent["parameters"], "城市级")
        self.check("massive.social_post", {"location": "巴黎"}, NOT_APPLICABLE)
        reference_only = make_intent("massive.social_post", [], text="发帖并显示当前位置", single_turn=True)
        self.assertEqual(precision_for(reference_only).tier, NOT_APPLICABLE)
        row = {
            "id": "15387", "locale": "zh-CN", "intent": "social_post",
            "utt": "把我的现在的位置发微博",
            "annot_utt": "把我的现在的位置 [media_type : 发微博]",
        }
        reviewed = next(adapt_massive(row)).intent
        self.assertEqual(reviewed["parameters"]["operation"], "share_current_location")
        self.assertEqual(precision_for(reviewed).tier, "城市级")
        unreviewed = next(adapt_massive({**row, "id": "another"})).intent
        self.assertEqual(precision_for(unreviewed).tier, NOT_APPLICABLE)

    def test_scene_trigger_uses_only_structured_parameters(self):
        for value in ("地理围栏", "到达地点", "离开地点"):
            with self.subTest(trigger=value):
                row = {"input": "启动智能情景", "output": f"使能智能情景: [触发方式: {value}]"}
                intent = next(adapt_cmpa(row)).intent
                self.assertEqual(precision_for(intent).tier, "精确")
        for value in ("manual", "schedule", "time"):
            self.check("scene.enable", {"trigger_type": value}, NOT_APPLICABLE)
        self.check("cmpa.使能智能情景", {}, NEEDS_REVIEW)
        self.check("scene.enable", {"trigger_type": "other"}, NEEDS_REVIEW)

    def test_reference_stays_outside_the_intent_and_the_label(self):
        raw = {"input": "告诉我当前位置", "output": "查询当前位置: [内容: 整句文本]"}
        candidate = next(adapt_cmpa(raw))
        row, tier = make_row(candidate, "cmpa", "train", "example", 0, True)
        self.assertEqual(tier, "精确")
        self.assertEqual(row["meta"]["notice"], "prompt")
        self.assertEqual(row["ref"]["text"], raw["input"])
        self.assertEqual(row["slots"], {})
        export, _ = make_row(candidate, "cmpa", "train", "example", 0, False)
        self.assertNotIn("ref", export)

    def test_smp2019_maps_slot_roles_without_mistaking_named_places_for_self_location(self):
        cases = (
            ("map", "ROUTE", "从济源市到河南省电信分公司怎么走",
             {"startLoc_city": "济源市", "endLoc_poi": "电信分公司", "endLoc_province": "河南省"},
             "查询路线", {"from": "济源市", "to": "河南省电信分公司"}, NOT_APPLICABLE),
            ("map", "POSITION", "河北在哪里", {"location_province": "河北"},
             "查询地点地址", {"loc": "河北"}, NOT_APPLICABLE),
            ("map", "POSITION", "我现在在哪个国家", {}, "查询当前位置", {"level": "country"}, "国家级模糊"),
            ("weather", "QUERY", "今天有雨吗", {"subfocus": "雨", "datetime_date": "今天"},
             "查询降雨", {}, "城市级模糊"),
            ("bus", "QUERY", "从无锡到阜阳的车", {"Src": "无锡", "Dest": "阜阳"},
             "查询城际客车", {"from": "无锡", "to": "阜阳"}, NOT_APPLICABLE),
        )
        for domain, action, raw, slots, name, expected_slots, label in cases:
            with self.subTest(name=name):
                candidate = next(adapt_smp2019({"text": raw, "domain": domain, "intent": action, "slots": slots}))
                row, _ = make_row(candidate, "smp2019", "train", "example", 0, False)
                self.assertEqual(row["intent"], name)
                self.assertEqual(row["slots"], expected_slots)
                self.assertEqual(row["label"], label)

    def test_chinese_names_match_for_shared_intents(self):
        cmpa = next(adapt_cmpa({"input": "帮我查天气", "output": "查询天气: []"}))
        massive = next(adapt_massive({
            "utt": "今天天气如何", "intent": "weather_query", "annot_utt": "今天天气如何",
        }))
        for source, candidate in (("cmpa", cmpa), ("massive", massive)):
            row, _ = make_row(candidate, source, "train", "example", 0, False)
            self.assertEqual(row["intent"], "查询天气")

    def test_named_poi_proximity_is_not_inferred_as_device_input(self):
        unbound = make_intent("place.search", [], text="图书馆附近的咖啡店", single_turn=True)
        bound = make_intent("place.search", [], text="我附近的咖啡店", single_turn=True)
        self.assertEqual(unbound["parameters"]["location_source"], "named_place")
        self.assertEqual(precision_for(unbound).tier, NOT_APPLICABLE)
        self.assertEqual(precision_for(bound).tier, "区域级")

    def test_source_intent_wins_over_a_conflicting_reference_text(self):
        row = {
            "utt": "这道菜多少钱", "intent": "takeaway_order", "annot_utt": "这道菜多少钱",
        }
        intent = next(adapt_massive(row)).intent
        self.assertEqual(intent["intent_id"], "delivery.order")
        self.assertEqual(precision_for(intent).tier, "精确")
        how_to = next(adapt_cmpa({"input": "如何查看我的当前位置", "output": "查询当前位置: []"}))
        self.assertEqual(precision_for(how_to.intent).tier, "精确")

    def test_delivery_order_omits_delivery_source_from_model_input(self):
        raw = "帮我点份披萨"
        for slots in ("食物: 披萨", "食物: 披萨, delivery_source: device_current"):
            with self.subTest(slots=slots):
                candidate = next(adapt_cmpa({"input": raw, "output": f"点外卖: [{slots}]"}))
                row, tier = make_row(candidate, "cmpa", "train", "example", 0, True)
                self.assertEqual(row["slots"], {})
                self.assertEqual(row["ref"]["text"], raw)
                self.assertEqual(tier, "精确")
        current = next(adapt_cmpa({"input": "点份披萨送到我当前位置", "output": "点外卖: []"}))
        row, tier = make_row(current, "cmpa", "train", "example", 0, False)
        self.assertEqual(row["slots"], {"src": "device_current"})
        self.assertEqual(tier, "精确")

    def test_named_rail_stations_are_normalized_to_their_roles(self):
        item = next(adapt_cmpa({
            "input": "西安到郑州的动车票还有吗",
            "output": "订火车票: [始发站: 西安, 终点站: 郑州]",
        }))
        params = item.intent["parameters"]
        self.assertEqual((params["origin"], params["destination"]), ("西安", "郑州"))
        self.assertEqual(precision_for(item.intent).tier, NOT_APPLICABLE)

    def test_device_relative_searches_keep_only_the_accuracy_evidence(self):
        cases = (
            ("附近的药店", "区域级", {"src": "device_current", "scope": "nearby"}),
            ("离我最近的图书馆", "精确", {"src": "device_current", "scope": "nearest"}),
            ("找<500米的药店", "精确", {"src": "device_current", "radius_m": 500}),
            ("找步行5分钟内的药店", "精确", {"src": "device_current", "scope": "walking_time"}),
            ("找我所在城市的景点", "城市级", {"src": "device_current", "level": "city"}),
            ("找我所在国家的旅游景点", "国家级", {"src": "device_current", "level": "country"}),
            ("查图书馆附近500米以内的咖啡馆", NOT_APPLICABLE, {"src": "fixed"}),
            ("找离我家最近的餐厅", NOT_APPLICABLE, {"src": "fixed"}),
            ("找2公里以内的餐厅", NEEDS_REVIEW, {"src": "device_current", "radius_m": 2000}),
            ("找2公里左右的餐厅", "区域级", {"src": "device_current", "scope": "rough_radius", "radius_m": 2000}),
        )
        for text, expected_tier, slots in cases:
            with self.subTest(text=text):
                candidate = next(adapt_cmpa({"input": text, "output": "查找地点: []"}))
                row, tier = make_row(candidate, "cmpa", "train", "example", 0, False)
                self.assertEqual(row["slots"], slots)
                self.assertEqual(tier, expected_tier)

    def test_crosswoz_followup_over_a_set_of_named_places_needs_no_device_location(self):
        messages = [
            {"role": "usr", "content": "查航空航天博物馆周围的景点", "dialog_act": [
                ["Inform", "景点", "名称", "航空航天博物馆"], ["Request", "景点", "周边景点", ""],
            ]},
            {"role": "sys", "content": "周边有北京大学", "dialog_act": [
                ["Inform", "景点", "周边景点", "北京大学"],
            ]},
            {"role": "usr", "content": "这些景点中有能玩2个小时的并且票价在100-150元之间的吗？", "dialog_act": [
                ["Inform", "景点", "游玩时间", "2小时"], ["Inform", "景点", "门票", "100-150元"],
                ["Select", "景点", "源领域", "景点"],
            ]},
        ]
        candidate = list(adapt_crosswoz({"messages": messages}, 6))[-1]
        row, tier = make_row(candidate, "crosswoz", "dev", "10860", 0, True)
        self.assertEqual(row["intent"], "查找或推荐地点")
        self.assertEqual(row["slots"], {"loc": "航空航天博物馆"})
        self.assertEqual(tier, NOT_APPLICABLE)

    def test_multi_turn_search_does_not_read_generic_nearby_or_local_taste_as_device(self):
        anchored = make_intent("place.search", [], text="告诉我周边餐馆和酒店的信息", anchor="博物馆")
        unbound = make_intent("restaurant.search", [], text="找家符合当地口味的餐馆")
        self.assertEqual(precision_for(anchored).tier, NOT_APPLICABLE)
        self.assertEqual(precision_for(unbound).tier, NEEDS_REVIEW)

    def test_device_contrasts_match_except_for_operation(self):
        with tempfile.TemporaryDirectory() as folder:
            metadata = write_device_find_contrasts(Path(folder), True)
            self.assertEqual(metadata["classes"], {"精确": 3, "不涉及": 6})
            self.assertEqual(metadata["total"], 9)
            with (Path(folder) / metadata["path"]).open(encoding="utf-8") as stream:
                rows = list(map(json.loads, stream))
        operations = {
            "query_target_location": NOT_APPLICABLE,
            "ring": NOT_APPLICABLE,
            "navigate_to_target": "精确",
        }
        for kind, offset in zip(("phone", "watch", "tablet"), range(0, 9, 3), strict=True):
            group = rows[offset:offset + 3]
            seen_operations = set()
            for row in group:
                self.assertTrue(row["id"].startswith(f"synthetic:train:{kind}:"))
                self.assertEqual(row["intent"], "查找设备")
                operation = row["slots"]["op"]
                self.assertEqual(row["slots"], {"op": operation})
                self.assertEqual(row["label"], operations[operation])
                seen_operations.add(operation)
            self.assertEqual(seen_operations, operations.keys())

    def test_self_location_contrasts_cover_all_four_labels(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "augmentation").mkdir()
            metadata = write_self_location_contrasts(root, False)
            rows = [json.loads(line) for line in (root / metadata["path"]).read_text().splitlines()]
        self.assertEqual({r["intent"] for r in rows}, {"查询当前位置"})
        self.assertEqual({r["slots"]["level"]: r["label"] for r in rows}, {
            "precise": "精确", "district": "区域级模糊", "city": "城市级模糊", "country": "国家级模糊",
        })

    def test_device_operation_is_normalized_from_structured_slots(self):
        for value, operation, label in (
            ("查看目标设备的地图位置", "query_target_location", NOT_APPLICABLE),
            ("播放铃声", "ring", NOT_APPLICABLE),
            ("从当前位置导航到目标设备", "navigate_to_target", "精确"),
        ):
            with self.subTest(operation=operation):
                candidate = next(adapt_cmpa({"input": "帮我找手机", "output": f"查找手机: [操作: {value}]"}))
                self.assertEqual(candidate.intent["parameters"]["operation"], operation)
                self.assertEqual(precision_for(candidate.intent).tier, label)


if __name__ == "__main__":
    unittest.main()
