"""Device location decisions from normalized intent fields."""

from dataclasses import dataclass
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
    "navigation.stop", "delivery.status", "location.address", "place.details",
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


POLICY_VERSION = "precision-weak-v3-production-intents"
NO_POSITION = "none"
TARGET_DEVICE = "target_device"
STORED_TRACK = "stored_history"
POSITION_SOURCES = FIXED | {DEVICE, TARGET_DEVICE, STORED_TRACK, NO_POSITION, UNKNOWN}
RESOLVED_WITHOUT_DEVICE = FIXED | {NO_POSITION}
SELF_GRANULARITY = {"precise": "精确", "district": "区域级", "city": "城市级", "country": "国家级"}


@dataclass(frozen=True)
class Rule:
    tier: str
    fields: tuple
    sources: frozenset = frozenset({DEVICE})
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
    "ride.order": Rule("精确", ("pickup_source",)),
    "transit.flight_ticket": Rule("城市级", ORIGINS),
    "transit.rail_ticket": Rule("城市级", ORIGINS),
    "transit.ticket": Rule("城市级", ORIGINS),
    "transit.flight_traffic": Rule("城市级", WHERE),
    "transit.bus_query": Rule("精确", ("location_source", *ORIGINS)),
    "transit.ride_code": Rule("城市级", WHERE),
    "device.find": Rule("精确", WHERE, frozenset({TARGET_DEVICE})),
    "fitness.start": Rule("精确", WHERE, notice="notify", mode="continuous"),
    "fitness.history": Rule("区域级", WHERE, frozenset({STORED_TRACK}), mode="route_overview"),
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
}
TIMED_ACTIONS = {"calendar.set", "calendar.update", "calendar.remove", "reminder.create"}
POSITION_FIELDS = frozenset(field for rule in RULES.values() for field in rule.fields)


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


def param_source(params, field):
    value = params.get(field)
    return value if isinstance(value, str) and value in POSITION_SOURCES else UNKNOWN


def review(rule):
    return PolicyLabel(NEEDS_REVIEW, rule, True)


def precision_for(intent):
    code = intent["intent_id"]
    params = intent["parameters"]
    if params.get("intent_state") == "unresolved" or params.get("confirmation") in (
        "pending_reply", "declined_or_corrected"
    ):
        return review("action_unresolved")
    if params.get("trigger_type") in ("geofence", "enter_location", "leave_location"):
        return review("geofence_outside_city_level_policy")

    if code == "location.self":
        source = param_source(params, "location_source")
        granularity = params.get("requested_granularity", UNKNOWN)
        if source not in (UNKNOWN, DEVICE) or (
            granularity != UNKNOWN and (not isinstance(granularity, str) or granularity not in SELF_GRANULARITY)
        ):
            return review("invalid_self_location_parameters")
        tier = SELF_GRANULARITY.get(granularity, "精确")
        return PolicyLabel(tier, "self_location", tier == "精确", notice="prompt")

    rule = RULES.get(code)
    if rule:
        references = tuple(param_source(params, key) for key in rule.fields)
        if code == "fitness.start" and params.get("tracking_mode") == "no_route":
            return PolicyLabel(NOT_APPLICABLE, "exercise_without_route")
        if any(source in rule.sources for source in references):
            return PolicyLabel(rule.tier, code, rule.tier == "精确", rule.notice, rule.mode)
        if all(source in RESOLVED_WITHOUT_DEVICE for source in references) or (
            code == "transit.bus_query" and (
                all(source in RESOLVED_WITHOUT_DEVICE for source in references[1:])
                or (references[0] in RESOLVED_WITHOUT_DEVICE and all(source == UNKNOWN for source in references[1:]))
            )
        ):
            return PolicyLabel(NOT_APPLICABLE, "location_already_specified_or_unused")
        if not any(source != UNKNOWN for source in references) and (
            code in TIMED_ACTIONS and (params.get("time") or params.get("date"))
        ):
            return PolicyLabel(NOT_APPLICABLE, "time_based_schedule")
        return review("location_role_unspecified_or_out_of_scope")

    namespace, _, native = code.partition(".")
    unrelated = (
        code in LOCATION_CONTROL or code in NON_LOCATION or code.startswith(NON_LOCATION_PREFIXES)
        or (namespace == "massive" and native in NON_LOCATION_MASSIVE)
        or (namespace == "cmpa" and CMPA_NON_LOCATION.fullmatch(native))
        or (namespace == "sgd" and native in SGD_NON_LOCATION)
    )
    if unrelated:
        if any(param_source(params, field) in (DEVICE, TARGET_DEVICE, STORED_TRACK) for field in POSITION_FIELDS):
            return review("unexpected_location_role")
        return PolicyLabel(NOT_APPLICABLE, "known_non_location_intent")
    return review("unmapped_location_relevance")
