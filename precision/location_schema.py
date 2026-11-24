"""Resolve reviewed paraphrases of intent/slot labels to the training schema."""

import json
from functools import lru_cache
from pathlib import Path
import re
import sys
import unicodedata
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from corpora.policy import RADIUS_PRECISE_M
from corpora.schema import INTENT_CODES_BY_NAME, policy_from_slots, ref_kind

EXACT, AREA, CITY = LABELS = ("精确", "区域级模糊", "城市级模糊")
NA = "不涉及"
CURRENT = "device_current"
SOURCES = {
    CURRENT: ("当前位置", "本机实时位置"),
    "named_place": ("指定地点", "用户已给地点"),
    "saved_place": ("已保存地点", "收藏地址"),
    "previous_entity": ("前文地点", "对话已确认地点"),
    "target_device": ("目标设备", "另一设备的位置"),
    "stored_history": ("历史轨迹", "已存轨迹"),
    "none": ("无位置", "不使用位置"),
    "unknown": ("未知来源", "未确认来源"),
}
KEYS = {
    "src": ("位置来源", "参照位置来源"),
    "from_src": ("起点来源", "出发地点来源"),
    "to_src": ("终点来源", "目的地点来源"),
    "pickup_src": ("上车点来源", "接驾点来源"),
    "fence_src": ("围栏来源", "围栏地点来源"),
    "level": ("定位粒度", "位置精度级别"),
    "scope": ("搜索约束", "空间筛选范围"),
    "radius_m": ("半径", "搜索半径"),
    "radius_band": ("半径分档", "距离区间"),
    "op": ("操作", "业务动作"),
    "track": ("轨迹模式", "路线记录方式"),
    "trigger": ("触发方式", "启动条件"),
    "anchor": ("指代状态", "参照确认状态"),
    "loc": ("地点", "指定地点"),
    "near": ("附近参照", "周边地标"),
    "from": ("起点", "出发地点"),
    "to": ("终点", "目的地点"),
    "pickup": ("上车点", "接驾位置"),
    "target": ("搜索目标", "候选类型"),
    "places": ("提到的地点", "地名列表"),
    "candidates": ("候选地点", "地点选项"),
}
VALUES = {
    "level": {
        "precise": ("精确", "准确坐标"), "district": ("区级", "所在行政区"),
        "city": ("城市级", "所在城市"), "country": ("国家级", "所在国家"),
        "coarse_unspecified": ("大概位置", "粗略位置"),
    },
    "scope": {
        "nearby": ("附近", "大致周边"), "nearest": ("最近", "距离最短"),
        "distance": ("准确距离", "实际路程距离"), "walking_time": ("步行耗时", "步行时长"),
        "rough_radius": ("约略半径", "可放宽的半径"),
    },
    "radius_band": {
        "up_to_policy_limit": ("阈值以内", "不超过阈值"),
        "above_policy_limit": ("超过阈值", "阈值以外"),
    },
    "track": {"route": ("记录路线", "启用轨迹"), "no_route": ("不记录路线", "关闭轨迹")},
    "trigger": {
        "enter_location": ("到达地点", "进入围栏"), "leave_location": ("离开地点", "移出围栏"),
        "geofence": ("地理围栏", "基于围栏"), "driving": ("驾驶状态", "进入驾车状态"),
        "manual": ("手动触发", "手动开启"), "time": ("时间触发", "定时触发"),
        "schedule": ("按日程", "日程触发"), "wifi": ("无线网连接", "连接Wi-Fi"),
        "bluetooth": ("蓝牙连接", "连接蓝牙"), "activity": ("活动状态", "检测到活动"),
    },
    "anchor": {"unresolved": ("未确认", "参照不明"), "intent_mismatch": ("意图不符", "意图冲突")},
    "op": {
        "discover": ("浏览候选", "查找选项"), "rank_by_distance": ("按距离排序", "按远近排序"),
        "filter_by_radius": ("按半径筛选", "距离阈值过滤"),
        "filter_by_travel_time": ("按步行耗时过滤", "按步行时长筛选"),
        "deliver_order": ("送餐下单", "安排配送"),
        "book_ticket": ("订票", "购买车票"), "search_options": ("查票", "搜索票务选项"),
        "request_pickup": ("请求上门", "呼叫接驾取件"), "schedule_pickup": ("预约上门", "预约交接"),
        "share_current_location": ("附上当前位置", "带上本机位置信息"),
        "navigate_to_target": ("导航到目标设备", "从本机导航至设备"),
        "query_target_location": ("查询目标位置", "查看另一设备位置"),
        "ring": ("响铃", "让设备响铃"),
    },
}
for field in ("src", "from_src", "to_src", "pickup_src", "fence_src"):
    VALUES[field] = SOURCES
LOCATION_FIELDS = {"src": ("loc", "near"), "from_src": ("from",), "to_src": ("to",), "pickup_src": ("pickup",)}
IGNORED = {"target", "places", "candidates", "loc", "near", "from", "to", "pickup"}
SEMANTIC_OPS = {"share_current_location", "navigate_to_target", "query_target_location", "ring"}
RADIUS_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(km|m|公里|千米|米)?", re.I)


def token(value):
    return re.sub(r"[\s_\-:：、，。！？!?]+", "", unicodedata.normalize("NFKC", str(value))).casefold()


def index(choices):
    result = {}
    for canonical, variants in choices.items():
        for name in (canonical, *variants):
            alias = token(name)
            if alias in result and result[alias] != canonical:
                raise ValueError(f"有歧义的别名：{name}")
            result[alias] = canonical
    return result


@lru_cache(maxsize=1)
def intent_aliases():
    data = {}
    for line in Path(__file__).with_name("intent_aliases.tsv").read_text(encoding="utf-8").splitlines():
        canonical, *variants = line.split("\t")
        if len(variants) != 3 or canonical not in INTENT_CODES_BY_NAME:
            raise ValueError(f"无效意图别名：{line}")
        data[canonical] = tuple(variants)
    return data


@lru_cache(maxsize=1)
def intent_index():
    return index(intent_aliases())


KEY_INDEX = index(KEYS)
VALUE_INDEX = {field: index(options) for field, options in VALUES.items()}
OP_PATTERN = re.compile(r"[a-z][a-z0-9_]*")


def radius_meters(value):
    match = RADIUS_PATTERN.fullmatch(unicodedata.normalize("NFKC", str(value)).strip())
    if not match:
        raise ValueError(f"无法识别半径：{value}")
    number, unit = match.groups()
    meters = Decimal(number) * (1000 if unit and unit.casefold() in {"km", "公里", "千米"} else 1)
    if not 0 < meters <= 10000000 or meters != meters.to_integral_value():
        raise ValueError(f"半径须为正整数米：{value}")
    return int(meters)


def normalize(row):
    intent = intent_index().get(token(row["intent"]))
    if intent is None:
        raise ValueError(f"未知意图：{row['intent']}")
    slots = row["slots"]
    if not isinstance(slots, dict):
        raise ValueError("slots 必须为 JSON 对象")
    parsed = {}

    def set_value(key, value):
        if key in parsed and parsed[key] != value:
            raise ValueError(f"槽位冲突：{key}")
        parsed[key] = value

    for name, value in slots.items():
        field = KEY_INDEX.get(token(name))
        if field is None:
            raise ValueError(f"未知槽位：{name}")
        if field == "radius_m":
            field_value = "up_to_policy_limit" if radius_meters(value) <= RADIUS_PRECISE_M else "above_policy_limit"
            set_value("radius_band", field_value)
        elif field in VALUE_INDEX:
            canonical = VALUE_INDEX[field].get(token(value))
            if canonical is None:
                if field != "op" or not isinstance(value, str) or not OP_PATTERN.fullmatch(value):
                    raise ValueError(f"{field} 不支持这个取值：{value}")
                canonical = value
            set_value(field, canonical)
        else:
            set_value(field, value)

    for source, fields in LOCATION_FIELDS.items():
        evidence = next((parsed[f] for f in fields if parsed.get(f)), None)
        if source not in parsed and evidence:
            kind = ref_kind(evidence)
            if kind != "unknown":
                parsed[source] = kind
    if "src" not in parsed and parsed.get("candidates"):
        parsed["src"] = "previous_entity"
    return {"intent": intent, "slots": {k: v for k, v in parsed.items() if k not in IGNORED}}


def semantic_slots(row):
    slots = {key: value for key, value in row["slots"].items() if key != "fence_src"}
    if slots.get("op") not in SEMANTIC_OPS:
        slots.pop("op", None)
    return slots


def combination(row):
    return json.dumps([row["intent"], row["slots"]], ensure_ascii=False, sort_keys=True)


def semantic_key(row):
    return combination({"intent": row["intent"], "slots": semantic_slots(row)})


def rule_label(row):
    slots = dict(row["slots"])
    band = slots.pop("radius_band", None)
    if band:
        slots["radius_m"] = RADIUS_PRECISE_M + (band == "above_policy_limit")
    tier = policy_from_slots(INTENT_CODES_BY_NAME[row["intent"]], slots).tier
    return {"区域级": AREA, "城市级": CITY}.get(tier, tier)
