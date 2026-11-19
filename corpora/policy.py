"""Minimum precision for an intent when a location call is attempted."""

from dataclasses import dataclass
import json
from pathlib import Path
import re


PRECISION_CLASSES = ("精确", "区域级", "城市级", "国家级")
NOT_APPLICABLE = "不涉及"
NEEDS_REVIEW = "待复核"
CLASSES = PRECISION_CLASSES + (NOT_APPLICABLE,)
REPORTED_TIERS = CLASSES + (NEEDS_REVIEW,)
UNKNOWN = "unknown"
DEVICE = "device_current"
HISTORY = "previous_entity"
NAMED = "named_place"
SAVED = "saved_place"
FIXED = {HISTORY, NAMED, SAVED}

LOCATION_CONTROL = {"cmpa.打开GPS", "cmpa.关闭GPS", "cmpa.打开GPS设置面板"}
NON_LOCATION = {
    "navigation.stop", "delivery.status", "place.details",
    "hotel.details", "restaurant.details", "transit.trip_status", "package.status",
    "device.find_menu", "fitness.activity_types", "calendar.query",
}
NON_LOCATION_PREFIXES = (
    "alarm.", "audio.", "massive.alarm_", "massive.audio_",
    "massive.calendar_", "massive.cooking_", "massive.datetime_", "massive.email_", "massive.general_",
    "massive.iot_", "massive.lists_", "massive.music_", "massive.play_",
)
NON_LOCATION_MASSIVE = {
    "qa_currency", "qa_definition", "qa_maths", "qa_stock", "recommendation_movies",
}
CMPA_NON_LOCATION = re.compile(
    r"设置(?:手机|导航键|显示|屏幕|应用|日期时间|输|桌面|日程|定时开关机)|"
    r"(?:关闭|打开)(?:闹钟|手机|WIFI|蓝牙|NFC|静音|振动|勿扰|飞行|热点|手电筒|省电|卡[一二]数据)|"
    r"(?:调[大小]|把)手机(?:音量|字体)|(?:调亮|调暗|关闭)屏幕|"
    r"(?:开始|继续|停止)播放|播放(?:音乐|视频|下一首|上一首)|查询手机(?:型号|软件版本|内存|名称)|"
    r"换算(?:面积|长度|重量|时间)单位|讲(?:笑话|故事)|倒计时|四则运算|设置主题|"
    r"(?:微信|支付宝)(?:转账|付款|收款|视频电话|语音电话)|"
    r"(?:充值话费|带金额充话费|查询话费余额|查询数据流量|查询现在几点了|设置锁屏背景)"
)
SGD_NON_LOCATION = {
    "PlayMedia", "PlayMovie", "PlaySong", "FindMusic", "SearchMusic", "LookupSong",
    "PlayMusic", "FindMovies", "GetAccountBalance", "TransferMoney", "CheckBalance",
}
with Path(__file__).with_name("non_location_intents.json").open(encoding="utf-8") as source:
    REVIEWED_NON_LOCATION = {
        f"{namespace}.{name}" for namespace, names in json.load(source).items() for name in names
    }


POLICY_VERSION = "precision-weak-v5-reviewed-intents"
NO_POSITION = "none"
TARGET_DEVICE = "target_device"
STORED_TRACK = "stored_history"
POSITION_SOURCES = FIXED | {DEVICE, TARGET_DEVICE, STORED_TRACK, NO_POSITION, UNKNOWN}
SELF_GRANULARITY = {
    "precise": "精确", "district": "区域级", "city": "城市级", "country": "国家级",
    "coarse_unspecified": "城市级",
}
SOCIAL_POST_INTENTS = {"massive.social_post", "social.post"}
SCENE_ENABLE_INTENTS = {"cmpa.使能智能情景", "scene.enable"}
GEOFENCE_TRIGGERS = ("geofence", "enter_location", "leave_location")


@dataclass(frozen=True)
class Rule:
    tier: str
    fields: tuple
    notice: str | None = None
    mode: str | None = None


# A field names the location role of the requested action, not a free-text prompt.
ORIGINS = ("origin_source", "destination_source")
WHERE = ("location_source",)
RULES = {
    "route.query": Rule("精确", ORIGINS),
    "route.estimate": Rule("精确", ORIGINS),
    "navigation.start": Rule("精确", ORIGINS, mode="continuous"),
    "weather.query": Rule("城市级", WHERE),
    "weather.rain": Rule("城市级", WHERE),
    "weather.alert": Rule("城市级", WHERE),
    "weather.environment": Rule("城市级", WHERE),
    "place.search": Rule("精确", WHERE, notice="notify"),
    "location.address": Rule("精确", WHERE, notice="notify"),
    "ride.order": Rule("精确", ("pickup_source",)),
    "transit.flight_ticket": Rule("城市级", ORIGINS),
    "transit.rail_ticket": Rule("城市级", ORIGINS),
    "transit.ticket": Rule("城市级", ORIGINS),
    "transit.flight_traffic": Rule("城市级", WHERE),
    "transit.bus_query": Rule("精确", ("location_source", *ORIGINS)),
    "transit.ride_code": Rule("城市级", WHERE),
    "fitness.start": Rule("精确", WHERE, notice="notify", mode="continuous"),
    "fitness.history": Rule("区域级", WHERE, mode="route_overview"),
    "package.ship": Rule("精确", ("address_source",)),
    "package.receive": Rule("精确", ("address_source",)),
    "local_service.search": Rule("城市级", WHERE),
    "travel.index": Rule("城市级", WHERE),
    "jobs.search": Rule("城市级", WHERE),
    "delivery.order": Rule("精确", ("delivery_source",)),
    "restaurant.reserve": Rule("城市级", WHERE),
    "calendar.set": Rule("城市级", WHERE),
    "calendar.update": Rule("城市级", WHERE),
    "calendar.remove": Rule("城市级", WHERE),
    "reminder.create": Rule("城市级", WHERE),
    "note.create": Rule("城市级", WHERE),
    "information.capture": Rule("城市级", WHERE),
    # Existing public-corpus intents adjacent to the live business table.
    "transit.query": Rule("区域级", ORIGINS),
    "traffic.query": Rule("区域级", WHERE),
    "hotel.search": Rule("区域级", WHERE),
    "hotel.reserve": Rule("区域级", WHERE),
    "restaurant.search": Rule("城市级", WHERE),
    "delivery.search": Rule("区域级", WHERE),
    "event.search": Rule("区域级", WHERE),
    "news.query": Rule("城市级", WHERE),
    "news.play": Rule("城市级", WHERE),
}


@dataclass(frozen=True)
class PolicyLabel:
    tier: str
    rule: str
    review: bool = False
    notice: str | None = None
    mode: str | None = None

    def record(self):
        if self.tier == NEEDS_REVIEW:
            return {"precision": None, "coarse_level": None}
        if self.tier in (NOT_APPLICABLE, "精确"):
            return {"precision": self.tier, "coarse_level": None}
        return {"precision": "模糊", "coarse_level": self.tier}

    def requirements(self):
        return {key: value for key, value in (("notice", self.notice), ("mode", self.mode)) if value}


def review(rule):
    return PolicyLabel(NEEDS_REVIEW, rule, True)


def precision_for(intent):
    """Do not infer whether the agent should call location from filled address slots."""
    code = intent["intent_id"]
    params = intent["parameters"]

    if code == "device.find":
        operation = params.get("operation")
        if operation == "query_target_location":
            return PolicyLabel("精确", "device_find_query_target_location", True)
        if operation == "ring":
            return PolicyLabel(NOT_APPLICABLE, "device_find_ring_only")
        return review("device_find_operation_unknown")

    if code == "location.self":
        requested = params.get("requested_granularity")
        tier = SELF_GRANULARITY.get(requested, "精确") if isinstance(requested, str) else "精确"
        return PolicyLabel(tier, "self_location", tier == "精确", notice="prompt")

    if code == "fitness.start" and params.get("tracking_mode") == "no_route":
        return PolicyLabel(NOT_APPLICABLE, "exercise_without_route")

    if code in SOCIAL_POST_INTENTS:
        if params.get("operation") == "share_current_location":
            return PolicyLabel("城市级", "social_post_current_location")
        return PolicyLabel(NOT_APPLICABLE, "social_post_without_current_location")

    if code in SCENE_ENABLE_INTENTS:
        trigger = params.get("trigger_type")
        if trigger in GEOFENCE_TRIGGERS:
            return PolicyLabel("精确", "scene_geofence_trigger", True)
        if trigger in ("manual", "schedule", "time"):
            return PolicyLabel(NOT_APPLICABLE, "scene_non_location_trigger")
        return review("scene_trigger_unknown")

    rule = RULES.get(code)
    if rule:
        return PolicyLabel(rule.tier, code, rule.tier == "精确", rule.notice, rule.mode)

    if code == "alarm.set" and params.get("trigger_type") in GEOFENCE_TRIGGERS:
        return review("geofence_alarm_policy_unspecified")

    namespace, _, native = code.partition(".")
    unrelated = (
        code in LOCATION_CONTROL or code in NON_LOCATION or code in REVIEWED_NON_LOCATION
        or code.startswith(NON_LOCATION_PREFIXES)
        or (namespace == "massive" and native in NON_LOCATION_MASSIVE)
        or (namespace == "cmpa" and CMPA_NON_LOCATION.fullmatch(native))
        or (namespace == "sgd" and native in SGD_NON_LOCATION)
    )
    if unrelated:
        return PolicyLabel(NOT_APPLICABLE, "known_non_location_intent")
    return review("unmapped_location_relevance")
