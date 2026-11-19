"""Common intent taxonomy, location roles, and weak-label policy."""

from dataclasses import dataclass
import json
import re
import unicodedata


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

INTENTS = {
    "weather.query": "查询天气",
    "weather.rain": "查询降雨",
    "weather.environment": "查询环境或生活指数",
    "navigation.start": "开始导航",
    "navigation.stop": "结束导航",
    "route.query": "查询路线",
    "route.estimate": "查询路线距离或耗时",
    "ride.order": "叫车",
    "delivery.order": "下单外卖",
    "delivery.search": "查找外卖",
    "delivery.status": "查询外卖订单状态",
    "location.self": "查询当前位置",
    "location.address": "查询地点地址",
    "place.search": "查找或推荐地点",
    "place.details": "查询地点详情",
    "hotel.search": "查找或推荐酒店",
    "hotel.details": "查询酒店详情",
    "hotel.reserve": "预订酒店",
    "restaurant.search": "查找或推荐餐馆",
    "restaurant.details": "查询餐馆详情",
    "restaurant.reserve": "预订餐馆",
    "event.search": "查找或推荐活动",
    "transit.query": "查询公共交通",
    "transit.ticket": "查询或办理交通票务",
    "traffic.query": "查询路况",
    "alarm.set": "设置闹钟",
    "alarm.query": "查询闹钟",
    "alarm.remove": "删除闹钟",
    "calendar.query": "查询日程",
    "calendar.set": "创建日程",
    "calendar.remove": "删除日程",
    "audio.volume.up": "调高音量",
    "audio.volume.down": "调低音量",
}

SLOT_ALIASES = {
    "city": "location", "location": "location", "place_name": "location",
    "城市": "location", "地点": "location", "城市名称": "location",
    "区域": "area", "地区": "area", "行政区": "area", "所在区域": "area",
    "出发地": "origin", "起点": "origin", "出发城市": "origin",
    "origin": "origin", "from": "origin", "from_city": "origin", "departure_city": "origin",
    "origin_airport": "origin",
    "起始地址": "origin", "上车点": "pickup", "上车地点": "pickup",
    "pickup_location": "pickup", "pickup_address": "pickup",
    "目的地": "destination", "终点": "destination", "到达城市": "destination",
    "destination_city": "destination", "to_city": "destination",
    "配送地址": "delivery_address", "收货地址": "delivery_address",
    "时间": "time", "出发时间": "time", "日期": "date", "时段": "time_of_day",
    "timeofday": "time_of_day", "天气现象": "weather_descriptor",
    "店名": "name", "名称": "name", "business_name": "name", "restaurant_name": "name",
    "hotel_name": "name", "景点名称": "name", "酒店名称": "name", "餐厅名称": "name",
    "地址": "address", "电话号码": "phone_number", "电话": "phone_number",
    "开门时间": "opening_hours", "开放时间": "opening_hours", "营业时间": "opening_hours",
    "评分": "rating", "门票价格": "ticket_price", "门票": "ticket",
    "酒店类型": "hotel_type", "景点类型": "attraction_type", "餐馆类型": "restaurant_type",
    "价格": "price", "人均消费": "price_per_person", "消费": "price_range",
    "推荐菜": "recommended_dish", "美食类型": "cuisine", "类别": "category",
    "出行方式": "transport_type", "交通方式": "transport_type", "乘车人": "rider",
    "商品名称": "item_name", "食物": "food_type",
    "源领域": "source_domain", "周边景点": "nearby_attractions",
    "周边餐馆": "nearby_restaurants", "周边酒店": "nearby_hotels",
}


def compact(text):
    text = unicodedata.normalize("NFKC", str(text)).strip()
    return re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", text)


def items(value):
    return value if isinstance(value, (list, tuple)) else [value]


def canonical_slot(name):
    key = compact(name)
    return SLOT_ALIASES.get(key, SLOT_ALIASES.get(key.lower(), key))


def normalize_slots(pairs):
    grouped = {}
    for key, value in pairs:
        key = canonical_slot(key)
        for atom in items(value):
            if atom is None or isinstance(atom, (dict, list, tuple)):
                continue
            normalized = compact(atom)
            if normalized.casefold() not in {"", "none", "?", "null", "未提及", "未指定"}:
                found = grouped.setdefault(key, [])
                if normalized not in found:
                    found.append(normalized)
    return {key: vals[0] if len(vals) == 1 else vals for key, vals in grouped.items()}


CURRENT = re.compile(
    r"(?:设备|手机|我(?:的)?)?(?:(?:当前|现在|此刻|目前)(?:所在)?的?位置|"
    r"所在(?:的)?(?:位置|地方|地区))|我的位置|我现在的位置|current (?:device )?location|my location",
    re.I,
)
PRONOUN = re.compile(r"(?:这儿|这里|这边|此处|那里|那边|那儿|他们家|他家|here|there|it)", re.I)
SYMBOLIC_REFERENCE = re.compile(r"(?:出现在)?(?:id\s*=|目标\s*|地点\s*)\d+.*", re.I)
SAVED_PLACE = re.compile(r"(?:我(?:的)?家(?:里)?|家里|家|公司|办公室|home|my home|my office)", re.I)
RAIN = re.compile(r"降雨|下雨|降水|暴雨|小雨|阵雨|雷雨|雨夹雪|带伞|雨量|precipitation|rain", re.I)
HERE = r"(?:这儿|这里|这边|此处|我这(?:儿|里|边)|我(?:的)?当前(?:的)?位置|当前位置|我的所在的地方|我所在的地方)"
ORIGIN_HERE = re.compile(r"(?:从|以)" + HERE)
DESTINATION_HERE = re.compile(r"(?:到|去|至)\s*(?:我这(?:儿|里|边)|设备当前位置|手机当前位置|我(?:的)?当前位置)")
PICKUP_HERE = re.compile(r"(?:到|在|去)" + HERE + r"(?:来)?接(?:上)?我|" + HERE + r"出发")
DELIVER_HERE = re.compile(r"(?:送|配送)到" + HERE)
NEARBY = re.compile(r"附近|周边|最近的|离我近|nearby|near me|closest to me", re.I)
LOCAL_WEATHER = re.compile(r"我(?:的)?这(?:里|儿|边)|我(?:的)?所在地区|我们这座城市|本地|当地")
ORDER_STATUS = re.compile(r"订单.{0,5}(?:状态|进度|怎么样|什么时候到|好了吗)|外卖现在什么状况")
PRECISE_SELF = re.compile(r"具体位置|精确位[置址]|详细地址|经纬度|坐标|门牌号")
SELF_LEVELS = (
    ("country", re.compile(r"哪个国家|什么国家|哪一个国家")),
    ("city", re.compile(r"哪个城市|哪座城市|什么城市|哪个市")),
    ("district", re.compile(r"哪个区|什么区|哪个行政区|哪(?:个|片)区域|哪个片区")),
    ("precise", PRECISE_SELF),
)
UNCERTAIN_ACTION = re.compile(
    r"不(?:用|要|想|能)(?:给我|帮我|再)?(?:导航|叫车|打车|定位|送|配送)|"
    r"假如|如果|取消(?:导航|打车|叫车)|如何查看我的当前位置|怎么查看我的当前位置"
)
LOCATION_TRIGGER = re.compile(
    r"(?:到达|离开|进入|到|回)\s*[^，。！？,!?]{1,14}(?:时|后|以后|了就|了以后)"
    r"[^，。！？,!?]{0,8}(?:提醒|闹钟|通知)|(?:提醒|闹钟|通知)[^，。！？,!?]{0,8}"
    r"(?:到达|离开|进入)[^，。！？,!?]{1,16}|"
    r"(?:到|回)(?:家|公司|学校)(?:就)?(?:提醒|通知)|\b(?:when i (?:arrive|leave|get home))\b",
    re.I,
)
LOCATION_CONTROL = {"cmpa.打开GPS", "cmpa.关闭GPS", "cmpa.打开GPS设置面板"}
NON_LOCATION = {
    "navigation.stop", "delivery.status", "location.address", "place.details",
    "hotel.details", "restaurant.details", "restaurant.reserve",
}
NON_LOCATION_PREFIXES = (
    "alarm.", "calendar.", "audio.", "massive.alarm_", "massive.audio_",
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


def ref_kind(value, *, anchor=None):
    values = [compact(atom) for atom in items(value) if atom]
    if not values:
        return UNKNOWN
    candidates = set()
    for atom in values:
        if CURRENT.fullmatch(atom):
            candidates.add(DEVICE)
        elif PRONOUN.fullmatch(atom) or SYMBOLIC_REFERENCE.fullmatch(atom):
            candidates.add(HISTORY if anchor else UNKNOWN)
        elif SAVED_PLACE.fullmatch(atom):
            candidates.add(SAVED)
        else:
            candidates.add(NAMED)
    return candidates.pop() if len(candidates) == 1 else UNKNOWN


def make_intent(code, pairs, *, text="", single_turn=False, anchor=None, label=None):
    params = normalize_slots(pairs)
    if "requested_slots" in params:
        params["requested_slots"] = items(params["requested_slots"])
    location = params.get("location") or params.get("area")
    if anchor:
        params["reference_place"] = compact(anchor)

    if code.startswith("weather."):
        if code == "weather.query" and (
            RAIN.search(" ".join(items(params.get("weather_descriptor", ""))))
            or (single_turn and RAIN.search(text))
        ):
            code = "weather.rain"
        params["location_source"] = ref_kind(location, anchor=anchor)
        if not location and single_turn and (LOCAL_WEATHER.search(text) or CURRENT.search(text)):
            params["location_source"] = DEVICE

    if code in {"navigation.start", "route.query", "route.estimate", "transit.query", "transit.ticket"}:
        params["origin_source"] = ref_kind(params.get("origin"), anchor=anchor)
        if single_turn and "origin" not in params and ORIGIN_HERE.search(text):
            params["origin_source"] = DEVICE
        if ref_kind(params.get("destination"), anchor=anchor) == DEVICE or (
            single_turn and DESTINATION_HERE.search(text)
        ):
            params["destination_source"] = DEVICE

    if code == "ride.order":
        if "pickup" not in params and "origin" in params:
            params["pickup"] = params.pop("origin")
        params["pickup_source"] = ref_kind(params.get("pickup"), anchor=anchor)
        if single_turn and "pickup" not in params and (PICKUP_HERE.search(text) or ORIGIN_HERE.search(text)):
            params["pickup_source"] = DEVICE

    if code == "delivery.order":
        params["delivery_source"] = ref_kind(params.get("delivery_address"), anchor=anchor)
        if single_turn and "delivery_address" not in params and DELIVER_HERE.search(text):
            params["delivery_source"] = DEVICE

    if code == "location.self":
        params["location_source"] = DEVICE
        params["requested_granularity"] = next(
            (level for level, rule in SELF_LEVELS if rule.search(text)), UNKNOWN
        ) if single_turn else UNKNOWN

    if code.endswith(".search") or code in {"traffic.query", "hotel.reserve"}:
        params["location_source"] = ref_kind(location, anchor=anchor)
        if anchor:
            params["location_source"] = HISTORY
        elif single_turn and not location and (NEARBY.search(text) or CURRENT.search(text)):
            params["location_source"] = DEVICE
        if single_turn and NEARBY.search(text):
            params["search_scope"] = "nearby"

    if single_turn and UNCERTAIN_ACTION.search(text):
        params["resolution_status"] = "uncertain"

    if LOCATION_TRIGGER.search(text) or CURRENT.search(text) or re.search(r"离我(?!们)", text):
        params["device_location_cue"] = True

    return {"intent_id": code, "label": INTENTS.get(code, label or code), "parameters": params}


@dataclass(frozen=True)
class PolicyLabel:
    tier: str
    rule: str
    review: bool = False

    def record(self):
        if self.tier in {NOT_APPLICABLE, NEEDS_REVIEW}:
            return {
                "precision": NOT_APPLICABLE if self.tier == NOT_APPLICABLE else None,
                "coarse_level": None,
            }
        return {
            "precision": "精确" if self.tier == "精确" else "模糊",
            "coarse_level": None if self.tier == "精确" else self.tier,
        }


def precision_for(intent):
    code = intent["intent_id"]
    params = intent["parameters"]
    if code in LOCATION_CONTROL:
        return PolicyLabel(NOT_APPLICABLE, "toggle_location_setting")
    namespace, _, native = code.partition(".")
    unrelated = (
        code in NON_LOCATION or code.startswith(NON_LOCATION_PREFIXES)
        or (namespace == "massive" and native in NON_LOCATION_MASSIVE)
        or (namespace == "cmpa" and CMPA_NON_LOCATION.fullmatch(native))
        or (namespace == "sgd" and native in SGD_NON_LOCATION)
    )
    if unrelated:
        if params.get("device_location_cue"):
            return PolicyLabel(NEEDS_REVIEW, "non_location_intent_with_device_cue", True)
        return PolicyLabel(NOT_APPLICABLE, "known_non_location_intent")
    if params.get("resolution_status") == "uncertain":
        return PolicyLabel(NEEDS_REVIEW, "uncertain_action", True)
    if code.startswith("weather."):
        loc = params["location_source"]
        if loc in FIXED:
            return PolicyLabel(NOT_APPLICABLE, "weather_fixed_place")
        return PolicyLabel("城市级", "weather_device_or_unspecified", loc == UNKNOWN)
    if code == "location.self":
        tier = params["requested_granularity"]
        if tier == "precise":
            return PolicyLabel("精确", "explicit_precise_self_location", True)
        if tier == UNKNOWN:
            return PolicyLabel("区域级", "self_location_granularity_unspecified", True)
        return PolicyLabel({"country": "国家级", "city": "城市级", "district": "区域级"}[tier], "explicit_coarse_self_location")
    role = {
        "navigation.start": "origin_source", "route.query": "origin_source",
        "ride.order": "pickup_source", "delivery.order": "delivery_source",
    }.get(code)
    if role:
        if code in {"navigation.start", "route.query"} and params.get("destination_source") == DEVICE:
            return PolicyLabel("精确", "explicit_device_destination", True)
        if params[role] == DEVICE:
            if params.get("confirmation") in {"pending_reply", "declined_or_corrected"}:
                return PolicyLabel("区域级", "pending_transaction_confirmation", True)
            return PolicyLabel("精确", f"explicit_device_{role}", True)
        if params[role] in FIXED:
            return PolicyLabel(NOT_APPLICABLE, f"fixed_{role}")
        return PolicyLabel("区域级", f"unspecified_{role}", True)
    if code in {"route.estimate", "transit.query"}:
        if params["origin_source"] in FIXED and params.get("destination_source") != DEVICE:
            return PolicyLabel(NOT_APPLICABLE, "fixed_route_origin")
        return PolicyLabel("区域级", "rough_route_or_transit", params["origin_source"] == UNKNOWN)
    if code == "transit.ticket":
        if params["origin_source"] in FIXED and params.get("destination_source") != DEVICE:
            return PolicyLabel(NOT_APPLICABLE, "fixed_ticket_origin")
        return PolicyLabel("城市级", "intercity_ticket", True)
    if "location_source" in params and (code.endswith(".search") or code in {"traffic.query", "hotel.reserve"}):
        if params["location_source"] in FIXED:
            return PolicyLabel(NOT_APPLICABLE, "search_fixed_place")
        if params["location_source"] == DEVICE:
            return PolicyLabel("区域级", "search_around_device")
        return PolicyLabel("区域级", "search_reference_unspecified", True)
    return PolicyLabel(NEEDS_REVIEW, "unmapped_location_relevance", True)


def canonical_json(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
