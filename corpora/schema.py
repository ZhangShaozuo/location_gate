"""Common intent taxonomy, location roles, and weak-label policy."""

import json
import re
import unicodedata

from .policy import (
    CLASSES, DEVICE, HISTORY, NAMED, NEEDS_REVIEW, NOT_APPLICABLE,
    POSITION_SOURCES, PRECISION_CLASSES, REPORTED_TIERS, SAVED, UNKNOWN,
    FIXED, GEOFENCE_TRIGGERS, GEO_CONTENT_INTENTS, RULES, SCENE_ENABLE_INTENTS, SEARCH_INTENTS,
    SELF_GRANULARITY, SOCIAL_POST_INTENTS,
    PolicyLabel, precision_for,
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
    "news.query": "查询新闻",
    "news.play": "播报新闻",
    "transit.query": "查询公共交通",
    "transit.ticket": "查询或办理交通票务",
    "transit.coach_query": "查询城际客车",
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
    "app.launch": "打开应用",
    "message.send": "发送消息",
    "music.play": "播放音乐",
    "social.post": "发布社交内容",
    "scene.enable": "启动智能情景",
}

INTENT_ALIASES = {
    "cmpa.打开应用": "app.launch", "cmpa.发送短信": "message.send",
    "cmpa.通过微信发送消息": "message.send",
    "cmpa.播放音乐": "music.play", "massive.play_music": "music.play",
    "sgd.PlayMusic": "music.play", "sgd.PlaySong": "music.play",
    **dict.fromkeys(SOCIAL_POST_INTENTS, "social.post"),
    **dict.fromkeys(SCENE_ENABLE_INTENTS, "scene.enable"),
}

SMP2019_INTENT_NAMES = {
    "app.download": "下载应用",
    "app.query": "查询应用",
    "cinemas.date_query": "查询影片上映日期",
    "cinemas.query": "查询影院或影片",
    "contacts.create": "新建联系人",
    "contacts.query": "查询联系人",
    "cookbook.query": "查询食谱",
    "email.create": "撰写邮件",
    "email.forward": "转发邮件",
    "email.launch": "打开邮件应用",
    "email.replay_all": "回复全部收件人",
    "email.reply": "回复邮件",
    "email.send": "发送邮件",
    "epg.look_back": "回看电视节目",
    "epg.query": "查询电视节目单",
    "health.query": "查询健康信息",
    "joke.query": "讲笑话",
    "lottery.number_query": "查询彩票号码",
    "lottery.query": "查询彩票信息",
    "map.position_unknown": "查询位置（对象未明确）",
    "match.query": "查询体育赛事",
    "message.sendcontacts": "发送联系人信息",
    "message.view": "查看消息",
    "music.search": "搜索音乐",
    "novel.query": "查询小说",
    "poetry.default": "诗词请求（动作未明确）",
    "poetry.query": "查询诗词",
    "radio.launch": "打开广播",
    "riddle.query": "猜谜语",
    "stock.closeprice_query": "查询股票收盘价",
    "stock.query": "查询股票",
    "stock.riserate_query": "查询股票涨幅",
    "story.query": "讲故事",
    "telephone.dial": "拨打电话",
    "telephone.query": "查询电话号码",
    "translation.translation": "翻译",
    "tvchannel.play": "播放电视频道",
    "video.query": "查询视频",
    "website.open": "打开网站",
}

GEO_SLOT_FIELDS = {
    "location_source": ("loc", "src", ("location", "area")),
    "origin_source": ("from", "from_src", ("origin",)),
    "destination_source": ("to", "to_src", ("destination",)),
    "pickup_source": ("pickup", "pickup_src", ("pickup",)),
    "address_source": ("loc", "src", ("address", "delivery_address")),
}
PLACE_INTENTS = {
    "location.address", "place.search", "place.details", "hotel.search", "hotel.details",
    "hotel.reserve", "restaurant.search", "restaurant.details", "restaurant.reserve",
}

SLOT_ALIASES = {
    "搜索范围": "search_scope", "搜索半径": "radius_m", "所需粒度": "requested_granularity",
    "位置来源": "location_source", "上车点来源": "pickup_source", "地址来源": "address_source",
    "city": "location", "location": "location", "place_name": "location",
    "城市": "location", "地点": "location", "城市名称": "location",
    "区域": "area", "地区": "area", "行政区": "area", "所在区域": "area",
    "出发地": "origin", "起点": "origin", "出发城市": "origin",
    "origin": "origin", "from": "origin", "from_city": "origin", "departure_city": "origin",
    "origin_airport": "origin", "始发站": "origin",
    "起始地址": "origin", "上车点": "pickup", "上车地点": "pickup",
    "pickup_location": "pickup", "pickup_address": "pickup",
    "目的地": "destination", "终点": "destination", "到达城市": "destination",
    "destination_city": "destination", "to_city": "destination", "终点站": "destination",
    "配送地址": "delivery_address", "收货地址": "delivery_address",
    "上门地址": "address", "寄件地址": "address", "收件地址": "address",
    "时间": "time", "出发时间": "time", "始发时间": "time", "日期": "date", "时段": "time_of_day",
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
    "查找方式": "operation", "操作": "operation",
    "触发方式": "trigger_type",
}
DEVICE_FIND_OPERATIONS = {
    "响铃": "ring", "播放铃声": "ring", "让设备响铃": "ring",
    "定位设备": "query_target_location", "查询设备位置": "query_target_location",
    "查询目标设备位置": "query_target_location",
    "查看目标设备的地图位置": "query_target_location",
    "导航去找设备": "navigate_to_target", "导航到目标设备": "navigate_to_target",
    "从当前位置导航到目标设备": "navigate_to_target",
}
SOCIAL_POST_OPERATIONS = {
    "附带当前位置": "share_current_location",
    "显示当前位置": "share_current_location",
    "分享当前位置": "share_current_location",
}
SCENE_TRIGGERS = {
    "地理围栏": "geofence", "场景围栏": "geofence",
    "到达地点": "enter_location", "离开地点": "leave_location",
    "手动": "manual", "定时": "schedule", "按时间": "time",
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
NEARBY = re.compile(r"附近|周边|周围|就近|\bnearby\b|\baround me\b|\bnear me\b", re.I)
DEVICE_NEARBY = re.compile(
    r"(?<!告诉)(?<!给)(?<!帮)(?<!为)我(?:们)?(?:的)?(?:附近|周边|周围)|"
    r"(?:离|距)我(?!的?(?:家|公司|单位|学校|住处|办公室))|以我为中心|"
    r"\bnear me\b|\baround me\b|\bclosest to me\b", re.I,
)
LOCAL_REGION = re.compile(r"我(?:的)?这(?:里|儿|边)|我(?:们)?(?:当前|现在)?所在(?:的)?(?:国家|城市|市|地区|区)|我们这座城市")
NEAREST = re.compile(
    r"离[^，。！？]{0,15}最近|距离[^，。！？]{0,15}最近|\b(?:nearest|closest)\b|"
    r"(?:最近的|最近一家)(?=[^，。！？]{0,12}(?:店|医院|景点|车站|站点|路口|公园|酒店|宾馆|餐馆|餐厅|银行|商场|超市|厕所|停车场|咖啡馆))",
    re.I,
)
WALKING_TIME = re.compile(r"(?:步行|走路)\s*(?:\d+|[一二三四五六七八九十两]+)\s*分钟(?:内|以内|之内)|\bwithin a \d+[- ]minute walk\b", re.I)
EXACT_DISTANCE = re.compile(r"准确距离|精确距离|(?:离我|距我)[^，。！？]{0,12}(?:多远|多少米)|\bexact distance\b", re.I)
RADIUS = re.compile(
    r"(?:(?P<prefix><=?|≤|小于|不到|不超过|半径|within\s+)?\s*)"
    r"(?P<number>\d+(?:\.\d+)?)\s*(?P<unit>公里|千米|km\b|米(?!饭|线)|m\b)"
    r"\s*(?P<suffix>以内|之内|范围内|内|范围|左右)?", re.I,
)
ROUGH_RADIUS = re.compile(r"(?:大约|大概|约)\s*\d|(?:米|公里|千米|km\b|m\b)\s*左右", re.I)
NEAREST_ANCHOR = re.compile(r"(?:离|距(?:离)?)([^，。！？]{1,18}?)最近")
LANDMARK = r"(?:公园|博物馆|图书馆|车站|酒店|宾馆|公司|商场|小区|医院|大学|机场|餐厅|广场|饭店|学校|大厦|园区|校区|店|站|家|办公室)"
ANCHOR_TEXT = re.compile(
    r"(?:在|以|离|距|到|找)\s*[^，。！？、]{0,18}" + LANDMARK +
    r"\s*(?:的)?(?:附近|旁边|周边|周围|为中心|最近)|"
    r"[\u4e00-\u9fff]{0,12}" + LANDMARK +
    r"\s*(?:的)?(?:附近|旁边|周边|周围)"
)
DEVICE_SCOPE_LEVELS = (
    ("country", re.compile(r"我(?:们)?(?:当前|现在)?所在(?:的)?国家|我所在国")),
    ("city", re.compile(r"我(?:们)?(?:当前|现在)?所在(?:的)?(?:城市|市)|我们这座城市")),
    ("district", re.compile(r"我(?:们)?(?:当前|现在)?所在(?:的)?(?:行政区|区|片区)")),
)
NO_DEVICE_LOCATION = re.compile(r"(?:不用|不需要|不要|别用|不允许)(?:使用|读取|调用)?(?:本机|手机|我的|当前)?(?:定位|当前位置)")
DELIVER_CURRENT = re.compile(r"(?:送到|配送到)(?:我这(?:里|儿|边)|我的?当前位置|手机当前位置)|使用(?:我的?|本机|手机)?当前位置(?:收货|配送)")
DELIVER_SAVED = re.compile(r"(?:送到|配送到|用)(?:我(?:保存|常用|默认)的)?(?:收货地址|常用地址|默认地址)|(?:送到|配送到)(?:我家|家里|公司|办公室)")
TRACKING_OFF = re.compile(r"室内|跑步机|不要记录轨迹|不记录轨迹|不使用GPS|模拟导航|导航预览", re.I)
TRACKING_ROUTE = re.compile(r"户外|室外|记录(?:运动|骑行|跑步)?轨迹|跑步路线|骑行路线|GPS", re.I)
ATTACH_LOCATION = re.compile(r"(?:附上|附带|加上|标注|记录|保存|使用)(?:我的?|本机|手机)?当前位置")
ORDER_STATUS = re.compile(r"订单.{0,5}(?:状态|进度|怎么样|什么时候到|好了吗)|外卖现在什么状况")
PRECISE_SELF = re.compile(r"具体位置|精确位[置址]|详细地址|经纬度|坐标|门牌号")
COARSE_SELF = re.compile(r"大概|粗略|模糊|大致")
SELF_LEVELS = (
    ("country", re.compile(r"哪个国家|什么国家|哪一个国家")),
    ("city", re.compile(r"哪个城市|哪座城市|什么城市|哪个市")),
    ("district", re.compile(r"哪个区|什么区|哪个行政区|哪(?:个|片)区域|哪个片区")),
    ("precise", PRECISE_SELF),
)
LOCATION_TRIGGER = re.compile(
    r"(?:到达|离开|进入)\s*[^，。！？,!?]{1,14}(?:时|后|以后|了就|了以后)"
    r"[^，。！？,!?]{0,8}(?:提醒|闹钟|通知)|(?:提醒|闹钟|通知)[^，。！？,!?]{0,8}"
    r"(?:到达|离开|进入)[^，。！？,!?]{1,16}|"
    r"(?:到|回)(?:家|公司|学校)(?:就|时|后|以后|了就|了以后)?(?:提醒|闹钟|通知)"
    r"|\b(?:when i (?:arrive|leave|get home))\b",
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
        elif DEVICE_NEARBY.search(atom):
            candidates.add(DEVICE)
        elif atom in {"附近", "本地", "当地", "nearby", "local"} or NEARBY.search(atom):
            candidates.add(UNKNOWN)
        elif PRONOUN.fullmatch(atom) or SYMBOLIC_REFERENCE.fullmatch(atom):
            candidates.add(HISTORY if anchor else UNKNOWN)
        elif SAVED_PLACE.fullmatch(atom):
            candidates.add(SAVED)
        else:
            candidates.add(NAMED)
    return candidates.pop() if len(candidates) == 1 else UNKNOWN


def radius_meters(value, text):
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        return int(value) or None
    for match in RADIUS.finditer(text):
        if match["prefix"] or match["suffix"]:
            multiplier = 1000 if match["unit"].casefold() in {"公里", "千米", "km"} else 1
            radius = round(float(match["number"]) * multiplier)
            if radius > 0:
                return radius
    return None


def apply_search_scope(params, text, single_turn):
    scope = params.get("search_scope")
    if isinstance(scope, str):
        scope = {"附近": "nearby", "最近": "nearest", "最近的": "nearest",
                 "精确距离": "distance", "步行时间": "walking_time"}.get(scope, scope)
    if scope not in ("nearby", "nearest", "distance", "walking_time", "rough_radius"):
        scope = next((key for key, pattern in (
            ("nearest", NEAREST), ("distance", EXACT_DISTANCE), ("walking_time", WALKING_TIME), ("nearby", NEARBY),
        ) if pattern.search(text)), None)
    radius = radius_meters(params.get("radius_m"), text)
    source = params.get("location_source")
    explicit_device = bool(DEVICE_NEARBY.search(text) or CURRENT.search(text) or LOCAL_REGION.search(text))
    other_anchor = NEAREST_ANCHOR.search(text)
    if explicit_device and source != "none":
        source = DEVICE
    elif source == UNKNOWN and (
        ANCHOR_TEXT.search(text) or other_anchor and ref_kind(other_anchor[1]) in FIXED
    ):
        source = NAMED
    if source == UNKNOWN and (explicit_device or single_turn and (scope or radius)):
        source = DEVICE
    params["location_source"] = source
    params.pop("search_scope", None)
    params.pop("radius_m", None)
    if source == DEVICE:
        if radius and scope in (None, "nearby") and ROUGH_RADIUS.search(text):
            scope = "rough_radius"
        if scope:
            params["search_scope"] = scope
        if radius:
            params["radius_m"] = radius
        level = next((level for level, cue in DEVICE_SCOPE_LEVELS if cue.search(text)), None)
        if level:
            params.setdefault("requested_granularity", level)


def make_intent(code, pairs, *, text="", single_turn=False, anchor=None, label=None):
    params = normalize_slots(pairs)
    text = compact(text)
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
    if code == "delivery.order":
        params.pop("delivery_source", None)
    if code == "location.address" or (
        code in PLACE_INTENTS and not (DEVICE_NEARBY.search(text) or CURRENT.search(text) or LOCAL_REGION.search(text))
    ):
        location = location or params.get("name")
    role_values = {
        "origin_source": params.get("origin"),
        "destination_source": params.get("destination"),
        "pickup_source": params.get("pickup"),
        "address_source": params.get("address") or params.get("delivery_address"),
        "location_source": location,
    }
    rule = RULES.get(code)
    if rule:
        for field in rule.fields:
            if field not in params:
                value = role_values[field]
                params[field] = ref_kind(value, anchor=anchor)
                if field == "location_source" and anchor and params[field] == UNKNOWN:
                    params[field] = HISTORY
        if single_turn:
            cues = {
                "origin_source": ORIGIN_HERE.search(text),
                "destination_source": DESTINATION_HERE.search(text),
                "pickup_source": PICKUP_HERE.search(text) or ORIGIN_HERE.search(text),
            }
            for field, matched in cues.items():
                if field in rule.fields and matched and params[field] == UNKNOWN:
                    params[field] = DEVICE
            if "location_source" in rule.fields and params["location_source"] == UNKNOWN:
                if LOCAL_REGION.search(text) or DEVICE_NEARBY.search(text) or CURRENT.search(text):
                    params["location_source"] = DEVICE
        if code in SEARCH_INTENTS:
            apply_search_scope(params, text, single_turn)
        if single_turn and code == "delivery.order" and params["address_source"] == UNKNOWN:
            if DELIVER_SAVED.search(text):
                params["address_source"] = SAVED
            elif DELIVER_CURRENT.search(text):
                params["address_source"] = DEVICE
        if NO_DEVICE_LOCATION.search(text):
            for field in rule.fields:
                if params[field] in (DEVICE, UNKNOWN):
                    params[field] = "none"
            if code in ("navigation.start", "fitness.start"):
                params["tracking_mode"] = "no_route"
    if code == "location.self":
        params.setdefault("location_source", DEVICE)
        if single_turn and "requested_granularity" not in params:
            params["requested_granularity"] = next(
                (level for level, cue in SELF_LEVELS if cue.search(text)),
                "coarse_unspecified" if COARSE_SELF.search(text) else UNKNOWN,
            )
    if code == "device.find":
        operation = params.get("operation")
        if isinstance(operation, str):
            params["operation"] = DEVICE_FIND_OPERATIONS.get(operation, operation)
    if code in SOCIAL_POST_INTENTS:
        operation = params.get("operation")
        if isinstance(operation, str):
            params["operation"] = SOCIAL_POST_OPERATIONS.get(operation, operation)
    if code in GEO_CONTENT_INTENTS:
        operation = params.get("operation")
        if isinstance(operation, str):
            params["operation"] = SOCIAL_POST_OPERATIONS.get(operation, operation)
        if params.get("location_source") != "none" and (
            ATTACH_LOCATION.search(text) or params.get("operation") == "share_current_location"
        ):
            params["operation"] = "share_current_location"
            params["location_source"] = DEVICE
    if code in ("navigation.start", "fitness.start"):
        if TRACKING_OFF.search(text):
            params["tracking_mode"] = "no_route"
        elif code == "fitness.start" and TRACKING_ROUTE.search(text):
            params.setdefault("tracking_mode", "route")
    if code in SCENE_ENABLE_INTENTS:
        trigger_type = params.get("trigger_type")
        if isinstance(trigger_type, str):
            params["trigger_type"] = SCENE_TRIGGERS.get(trigger_type, trigger_type)
    if code in {"alarm.set", "calendar.set", "calendar.update", "reminder.create"} and LOCATION_TRIGGER.search(text):
        params.setdefault("trigger_type", "geofence")

    return {"intent_id": code, "label": INTENTS.get(code, label or code), "parameters": params}


def canonical_json(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_intent_code(intent):
    code = intent["intent_id"]
    return INTENT_ALIASES.get(code, code)


def chinese_intent_name(intent):
    code = canonical_intent_code(intent)
    if code in INTENTS:
        return INTENTS[code]
    prefix, _, native = code.partition(".")
    if prefix == "smp2019" and native in SMP2019_INTENT_NAMES:
        return SMP2019_INTENT_NAMES[native]
    name = intent["label"]
    if re.search(r"[\u3400-\u9fff]", name):
        return name
    return f"待归一意图（{code}）"


def model_slots(intent):
    """Project normalized intent parameters onto the shared location slot vocabulary."""
    code = intent["intent_id"]
    params = intent["parameters"]
    rule = RULES.get(code)
    slots = {}
    if code in PLACE_INTENTS:
        if params.get("name"):
            slots["loc"] = params["name"]
        if params.get("reference_place") and params["reference_place"] != params.get("name"):
            slots["near"] = params["reference_place"]
    for field in rule.fields if rule else ():
        slot, source_slot, keys = GEO_SLOT_FIELDS[field]
        for key in keys:
            if params.get(key):
                slots[slot] = params[key]
                break
        source = params.get(field)
        has_place = slot in slots or slot == "loc" and "near" in slots
        if source in (NAMED, HISTORY) and not has_place:
            slots[source_slot] = "fixed"
        elif isinstance(source, str) and source in POSITION_SOURCES - {UNKNOWN, NAMED}:
            slots[source_slot] = source
    if code == "ride.order" and params.get("destination"):
        slots["to"] = params["destination"]
    if code == "location.self" or code in SEARCH_INTENTS and params.get("location_source") == DEVICE:
        level = params.get("requested_granularity")
        if isinstance(level, str) and level in SELF_GRANULARITY:
            slots["level"] = level
    if code in SEARCH_INTENTS and params.get("location_source") == DEVICE:
        for field, slot in (("search_scope", "scope"), ("radius_m", "radius_m")):
            if field in params:
                slots[slot] = params[field]
    if code == "device.find" or code in SOCIAL_POST_INTENTS | GEO_CONTENT_INTENTS:
        operation = params.get("operation")
        allowed = (
            ("query_target_location", "ring", "navigate_to_target")
            if code == "device.find" else ("share_current_location",)
        )
        if operation in allowed:
            slots["op"] = operation
    if code in SCENE_ENABLE_INTENTS | GEO_CONTENT_INTENTS | {"alarm.set"}:
        trigger = params.get("trigger_type")
        if trigger in (*GEOFENCE_TRIGGERS, "manual", "schedule", "time"):
            slots["trigger"] = trigger
    if code in ("fitness.start", "navigation.start") and params.get("tracking_mode") in ("route", "no_route"):
        slots["track"] = params["tracking_mode"]
    return slots
