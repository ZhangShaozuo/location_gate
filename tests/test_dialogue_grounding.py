import unittest

from corpora.adapters import adapt_cmpa
from corpora.dialogues import assemble_dialogue
from corpora.grounding import ground_location_evidence, resolve_task
from prepare import make_row


def user(text, *actions):
    return {"role": "usr", "content": text, "dialog_act": actions}


def assistant(text, *actions):
    return {"role": "sys", "content": text, "dialog_act": actions}


class WholeDialogueTests(unittest.TestCase):
    def single(self, text, native):
        candidate, = adapt_cmpa({"input": text, "output": native + ": []"})
        grounded = resolve_task(ground_location_evidence(candidate.intent, text), text)
        return make_row(candidate, "cmpa", "train", 0, 0, True, intent=grounded)[0]

    def test_user_examples_keep_position_slots(self):
        for text, code, label, slots in (
            ("能否帮我找到最近的健身房？", "查询周边", "精确",
             {"scope": "nearest", "src": "device_current", "target": "健身房"}),
            ("能否在我开车回家时启动智能情景模式？", "使能智能情景", "不涉及",
             {"trigger": "driving", "to": "家"}),
            ("我在黄山，哪里可以找到特色小吃？", "查询周边", "不涉及",
             {"loc": "黄山", "target": "特色小吃"}),
            ("周末打算去公园野餐，帮我查一下那边有没有便利店。", "查询周边", "待复核",
             {"anchor": "unresolved", "scope": "nearby", "target": "便利店"}),
        ):
            with self.subTest(text=text):
                row = self.single(text, code)
                self.assertEqual(row["label"], label)
                self.assertEqual(row["slots"], slots)

    def test_unknown_label_does_not_discard_radius(self):
        row = self.single("帮我查找附近两公里半径范围内的便利店。", "查询周边")
        self.assertEqual(row["label"], "待复核")
        self.assertEqual(row["slots"]["radius_m"], 2000)
        self.assertEqual(row["slots"]["target"], "便利店")

    def test_places_are_kept_when_route_roles_are_incomplete(self):
        row = self.single("迪士尼乐园路线图", "查询去某地的路线")
        self.assertEqual(row["label"], "待复核")
        self.assertEqual(row["slots"], {"places": ["迪士尼乐园"]})

    def test_later_clarification_resolves_previous_task_even_without_actions(self):
        messages = [
            user("周末打算去公园野餐，帮我查一下那边有没有便利店。", ("Request", "景点", "名称", "")),
            assistant("请问是哪个公园？"),
            user("世纪公园。"),
            assistant("明白了。"),
            user("再查一下北京的天气。", ("Inform", "天气", "城市", "北京")),
        ]
        tasks = assemble_dialogue("crosswoz", {"messages": messages}, 1)
        self.assertEqual(len(tasks), 2)
        first, second = tasks
        self.assertEqual(first.evidence_turns, [0, 2])
        self.assertEqual(second.evidence_turns, [4])
        a, b = [make_row(t.candidate, "crosswoz", "train", 0, i, True)[0] for i, t in enumerate(tasks)]
        self.assertEqual(a["label"], "不涉及")
        self.assertEqual(a["slots"], {"near": "世纪公园", "src": "previous_entity", "scope": "nearby", "target": "便利店"})
        self.assertEqual(b["slots"], {"loc": "北京"})

    def test_later_requested_locations_are_separate_and_corrections_merge(self):
        messages = [
            user("帮我查北京的酒店。", ("Inform", "酒店", "城市", "北京"), ("Request", "酒店", "名称", "")),
            assistant("我先查北京。"),
            user("另外查一下上海的酒店。", ("Inform", "酒店", "城市", "上海"), ("Request", "酒店", "名称", "")),
            assistant("需要上海对吗？"),
            user("第二个改成广州。", ("Inform", "酒店", "城市", "广州")),
        ]
        first, second = assemble_dialogue("crosswoz", {"messages": messages}, 2)
        self.assertEqual(first.evidence_turns, [0])
        self.assertEqual(second.evidence_turns, [2, 4])
        self.assertEqual(first.candidate.intent["parameters"]["location"], "北京")
        self.assertEqual(second.candidate.intent["parameters"]["location"], "广州")

    def test_assistant_options_do_not_become_an_arbitrary_anchor(self):
        messages = [
            user("推荐景点。", ("Request", "景点", "名称", "")),
            assistant("世纪公园和人民公园都可以。",
                      ("Recommend", "景点", "名称", "世纪公园"), ("Recommend", "景点", "名称", "人民公园")),
            user("另外，查一下那边有没有便利店。", ("Request", "景点", "名称", "")),
        ]
        last = assemble_dialogue("crosswoz", {"messages": messages}, 6)[-1]
        row = make_row(last.candidate, "crosswoz", "train", 0, 0, True)[0]
        self.assertEqual(row["label"], "待复核")
        self.assertNotIn("near", row["slots"])

    def test_filtering_an_established_list_is_a_new_location_independent_task(self):
        messages = [
            user("帮我找一家酒店。", ("Request", "酒店", "名称", "")),
            assistant("推荐甲酒店和乙酒店。", ("Recommend", "酒店", "名称", "甲酒店"),
                      ("Recommend", "酒店", "名称", "乙酒店")),
            user("这些酒店中哪个评分更高？", ("Request", "酒店", "评分", "")),
        ]
        first, second = assemble_dialogue("crosswoz", {"messages": messages}, 1)
        a, b = [make_row(x.candidate, "crosswoz", "train", 0, i, True)[0] for i, x in enumerate((first, second))]
        self.assertEqual(a["label"], "城市级模糊")
        self.assertEqual(b["label"], "不涉及")
        self.assertEqual(b["slots"], {"candidates": ["甲酒店", "乙酒店"], "src": "previous_entity"})
