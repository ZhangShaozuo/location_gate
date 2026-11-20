import json
import sqlite3
import unittest

from corpora.adapters import utterance_candidate
from corpora.policy import NEEDS_REVIEW, NOT_APPLICABLE
from corpora.review import ground_single_turn_review
from corpora.schema import reviewed_label
from prepare import LABEL_NAMES, make_row, model_record, validate_model_inputs


class SingleTurnReviewTests(unittest.TestCase):
    def row(self, code, text, pairs=()):
        candidate = utterance_candidate(code, pairs, text, code)
        intent = ground_single_turn_review(candidate.intent, text)
        return make_row(candidate, "sample", "train", 0, 0, True, intent=intent)[0]

    def test_confirmed_searches_keep_the_sources_that_change_the_label(self):
        cases = (
            ("restaurant.search", "帮我推荐一个评分5分的餐馆", (), "区域级",
             {"src": "device_current", "scope": "nearby"}),
            ("restaurant.search", "在颐和园附近找家餐厅", (), NOT_APPLICABLE, {"loc": "颐和园"}),
            ("hotel.search", "帮我找一家舒适型的酒店", (), "城市级",
             {"src": "device_current", "level": "city"}),
            ("hotel.reserve", "帮我预订附近的酒店", (("location", "附近"),), "区域级",
             {"loc": "附近", "src": "device_current", "scope": "nearby"}),
            ("hotel.reserve", "我需要入住北京天安门附近的酒店", (("location", ["北京", "天安门附近"]),),
             NOT_APPLICABLE, {"loc": ["北京", "天安门附近"], "src": "fixed"}),
            ("place.search", "我想找最近的酒吧", (), "精确",
             {"src": "device_current", "scope": "nearest"}),
            ("smp2019.cinemas.query", "附近电影院。", (), "区域级",
             {"src": "device_current", "scope": "nearby"}),
            ("smp2019.cinemas.query", "我要查找雷迪波尔电影院最新上映的大片", (), NOT_APPLICABLE,
             {"loc": "雷迪波尔电影院"}),
            ("smp2019.cinemas.query", "最近有什么新上映的电影啊？", (), NOT_APPLICABLE, {"src": "none"}),
            ("smp2019.cinemas.date_query", "咱们结婚吧什么时候播出", (), NOT_APPLICABLE, {}),
            ("delivery.search", "我的比萨还有多久到这里", (), NOT_APPLICABLE, {"src": "none"}),
        )
        for code, text, pairs, tier, slots in cases:
            with self.subTest(text=text):
                row = self.row(code, text, pairs)
                self.assertEqual(row["slots"], slots)
                self.assertEqual(row["label"], LABEL_NAMES[tier])
                self.assertEqual(reviewed_label(row["intent"], row["slots"]), tier)
                self.assertEqual(model_record(row), {"intent": row["intent"], "slots": slots, "label": row["label"]})

    def test_route_and_ride_positions_preserve_their_role(self):
        cases = (
            ("route.query", "去美术馆怎么走", (), "精确",
             {"to": "美术馆", "from_src": "device_current"}),
            ("route.query", "从曼哈顿的麦当劳到我家怎么走", (), NOT_APPLICABLE,
             {"from": "曼哈顿的麦当劳", "to": "我家", "to_src": "saved_place"}),
            ("ride.order", "叫出租车去机场", (("destination", "机场"),), "精确",
             {"to": "机场", "pickup_src": "device_current"}),
            ("ride.order", "现在叫辆滴滴来接我", (), "精确", {"pickup_src": "device_current"}),
            ("ride.order", "叫辆出租车从什刹海到裕德孚老北京涮羊肉", (), NOT_APPLICABLE,
             {"pickup": "什刹海", "to": "裕德孚老北京涮羊肉"}),
            ("transit.query", "最近的火车站在哪", (), "精确", {"src": "device_current", "scope": "nearest"}),
            ("transit.query", "最近的火车站在哪", (("location", "火车站"),), "精确",
             {"src": "device_current", "scope": "nearest"}),
            ("transit.query", "下一班离开这里去北京的火车什么时候开", (("location", "北京"),), "城市级",
             {"from_src": "device_current", "to": "北京", "src": "device_current", "level": "city"}),
            ("transit.query", "火车时刻表", (), NOT_APPLICABLE, {"src": "none"}),
        )
        for code, text, pairs, tier, slots in cases:
            with self.subTest(text=text):
                row = self.row(code, text, pairs)
                self.assertEqual(row["slots"], slots)
                self.assertEqual(reviewed_label(row["intent"], slots), tier)
                self.assertEqual(row["label"], LABEL_NAMES[tier])

    def test_scene_and_device_require_different_slot_evidence(self):
        for code, text, tier, slots in (
            ("cmpa.使能智能情景", "请在我连接蓝牙耳机时启动智能情景", NOT_APPLICABLE, {"trigger": "bluetooth"}),
            ("scene.enable", "到家时启动智能情景", "精确", {"trigger": "geofence"}),
            ("device.find", "我的手机不见了，帮我找找看。", NOT_APPLICABLE, {"op": "query_target_location"}),
            ("device.find", "导航到我的手机", "精确", {"op": "navigate_to_target"}),
        ):
            with self.subTest(text=text):
                row = self.row(code, text)
                self.assertEqual(row["slots"], slots)
                self.assertEqual(reviewed_label(row["intent"], slots), tier)
                self.assertEqual(row["label"], LABEL_NAMES[tier])

    def test_unresolved_cases_are_not_assigned_a_tier(self):
        for code, text in (
            ("delivery.search", "他们送外送吗"),
            ("route.query", "请规划路线"),
            ("route.estimate", "到那里要多长时间"),
            ("scene.enable", "我开车回家时启动智能情景"),
            ("place.search", "请给我两公里半径范围内的所有商店名字"),
            ("transit.query", "最近的墨西哥餐厅在哪里"),
            ("delivery.search", "我能点外卖吗"),
        ):
            with self.subTest(text=text):
                self.assertEqual(self.row(code, text)["label"], NEEDS_REVIEW)

    def test_conflicting_labels_for_identical_model_input_fail_export(self):
        with sqlite3.connect(":memory:") as conn:
            conn.executescript("CREATE TABLE candidates(id, row_json); CREATE TABLE eligible(id, split, tier);")
            for i, label in enumerate(("精确", "区域级模糊")):
                conn.execute("INSERT INTO eligible VALUES (?, ?, ?)", (i, "train", label))
                conn.execute("INSERT INTO candidates VALUES (?, ?)", (
                    i, json.dumps({"intent": "测试意图", "slots": {}, "label": label}),
                ))
            with self.assertRaisesRegex(ValueError, "同一模型输入的标签冲突"):
                validate_model_inputs(conn)
