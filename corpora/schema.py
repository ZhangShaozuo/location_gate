"""Common intent taxonomy, location roles, and weak-label policy."""

import json
import re
import unicodedata

from .policy import (
    CLASSES, DEVICE, HISTORY, NAMED, NEEDS_REVIEW, NOT_APPLICABLE,
    POSITION_SOURCES, PRECISION_CLASSES, REPORTED_TIERS, SAVED, UNKNOWN,
    RULES, PolicyLabel, precision_for,
)


INTENTS = {
    "weather.query": "查询天气",
    "weather.rain": "查询降雨",
    "weather.alert": "查询天气预警",
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
    "transit.flight_ticket": "查询或预订机票",
    "transit.rail_ticket": "查询或预订火车票",
    "transit.flight_traffic": "查询机场航班流量",
    "transit.trip_status": "查询已订行程",
    "transit.bus_query": "查询公交地铁",
    "transit.ride_code": "查看乘车码",
    "device.find": "查找设备",
    "device.find_menu": "打开查找设备界面",
    "fitness.start": "开始运动",
    "fitness.history": "查询运动轨迹",
    "fitness.activity_types": "查看运动类型",
    "package.ship": "寄快递",
    "package.receive": "收快递",
    "package.status": "查询快递状态",
    "local_service.search": "查找本地服务",
    "travel.index": "查询旅游指数",
    "jobs.search": "查找招聘信息",
    "traffic.query": "查询路况",
    "alarm.set": "设置闹钟",
    "alarm.query": "查询闹钟",
    "alarm.remove": "删除闹钟",
    "calendar.query": "查询日程",
    "calendar.set": "创建日程",
    "calendar.update": "修改日程",
    "calendar.remove": "删除日程",
    "reminder.create": "创建提醒",
    "note.create": "创建备忘",
    "information.capture": "记录信息",
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
    "上门地址": "address", "寄件地址": "address", "收件地址": "address",
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
REFERENCE_ONLY_SLOTS = {
    "utterance", "raw_text", "user_request", "query", "text", "content", "message",
    "事项", "内容", "文本内容", "短信内容", "device_location_cue", "resolution_status",
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
        if key in REFERENCE_ONLY_SLOTS:
            continue
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
DEVICE_NEARBY = re.compile(r"(?:我(?:的)?|这(?:里|儿|边))(?:附近|周边)|离我|\bnear me\b|\bclosest to me\b", re.I)
LOCAL_WEATHER = re.compile(r"我(?:的)?这(?:里|儿|边)|我(?:的)?所在地区|我们这座城市|本地|当地")
ORDER_STATUS = re.compile(r"订单.{0,5}(?:状态|进度|怎么样|什么时候到|好了吗)|外卖现在什么状况")
PRECISE_SELF = re.compile(r"具体位置|精确位[置址]|详细地址|经纬度|坐标|门牌号")
COARSE_SELF = re.compile(r"大概|粗略|模糊|大致")
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
def ref_kind(value, *, anchor=None):
    values = [compact(atom) for atom in items(value) if atom]
    if not values:
        return UNKNOWN
    candidates = set()
    for atom in values:
        if atom in POSITION_SOURCES:
            candidates.add(atom)
        elif CURRENT.fullmatch(atom):
            candidates.add(DEVICE)
        elif atom in {"附近", "本地", "当地", "nearby", "local"}:
            candidates.add(UNKNOWN)
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
    if code == "ride.order":
        if "pickup" not in params and "origin" in params:
            params["pickup"] = params.pop("origin")
    role_values = {
        "origin_source": params.get("origin"),
        "destination_source": params.get("destination"),
        "pickup_source": params.get("pickup"),
        "delivery_source": params.get("delivery_address"),
        "address_source": params.get("address") or params.get("delivery_address"),
        "location_source": location,
    }
    rule = RULES.get(code)
    if rule:
        for field in rule.fields:
            if field not in params:
                value = role_values[field]
                params[field] = ref_kind(value, anchor=anchor)
                if field == "location_source" and anchor and not value:
                    params[field] = HISTORY
        if single_turn:
            cues = {
                "origin_source": ORIGIN_HERE.search(text),
                "destination_source": DESTINATION_HERE.search(text),
                "pickup_source": PICKUP_HERE.search(text) or ORIGIN_HERE.search(text),
                "delivery_source": DELIVER_HERE.search(text),
            }
            for field, matched in cues.items():
                if field in rule.fields and matched and params[field] == UNKNOWN:
                    params[field] = DEVICE
            if "location_source" in rule.fields and params["location_source"] == UNKNOWN:
                local_weather = code.startswith("weather.") and LOCAL_WEATHER.search(text)
                local_search = (
                    (code.endswith(".search") or code in ("transit.bus_query", "traffic.query"))
                    and DEVICE_NEARBY.search(text)
                )
                if local_weather or local_search or CURRENT.search(text):
                    params["location_source"] = DEVICE
    if code == "location.self":
        params.setdefault("location_source", DEVICE)
        if single_turn and "requested_granularity" not in params:
            params["requested_granularity"] = next(
                (level for level, cue in SELF_LEVELS if cue.search(text)),
                "coarse_unspecified" if COARSE_SELF.search(text) else UNKNOWN,
            )
    if code in {"alarm.set", "calendar.set", "calendar.update", "reminder.create"} and LOCATION_TRIGGER.search(text):
        params.setdefault("trigger_type", "geofence")
    if single_turn and (rule or code == "location.self") and UNCERTAIN_ACTION.search(text):
        params["intent_state"] = "unresolved"

    return {"intent_id": code, "label": INTENTS.get(code, label or code), "parameters": params}


def canonical_json(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
