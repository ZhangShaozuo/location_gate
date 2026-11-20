"""Extract position evidence even when an intent cannot be labeled yet."""

import re

from .policy import DEVICE, FIXED, NAMED, NEEDS_REVIEW, ROUTE_INTENTS, SCENE_ENABLE_INTENTS, SEARCH_INTENTS
from .policy import precision_for
from .review import CITY, CITY_CONTEXT, CITY_PREFIX, CN_DIGITS, CN_RADIUS
from .review import ground_single_turn_review, resolve_remaining_single_turn
from .schema import (
    DEVICE_NEARBY, EXACT_DISTANCE, NEARBY, NEAREST, ROUGH_RADIUS, WALKING_TIME,
    canonical_intent_code, compact, radius_meters, ref_kind,
)


STATED_LOCATION = re.compile(
    r"(?:我|我们)(?:现在|目前|正好|正)?在("
    + CITY + r"|黄山|[\u4e00-\u9fff]{2,12}(?:市|县|区|镇|岛|公园|景区|机场|车站))(?=[,，。!?；;]|$)"
)
TARGET = re.compile(
    r"健身房|健身馆|健身中心|便利店|特色小吃|公共厕所|停车场|加油站|充电站|售后服务中心|"
    r"咖啡馆|咖啡店|药店|医院|超市|电影院|图书馆|火车站|公交站|地铁站|快递点|公园"
)
UNBOUND_PLACE = re.compile(r"那边|那里|那儿|那(?:家|个)(?:地方|景点|公园|路口|站点|餐厅|酒店)|所需的位置|(?:去|到)某地")
ROUTE_DEICTIC = re.compile(r"(?:到|去|从|离)(?:那边|那里|那儿|某地|那个地方)|(?:我的|指定的|旅行)目的地|所需的位置|不同的路线")
PLACE_WORD = r"[\u4e00-\u9fffA-Za-z0-9·]{1,18}(?:公园|景区|广场|机场|火车站|车站|博物馆|酒店|银行|大厦|小区|大学)"
EXPLICIT_NEAR = re.compile(r"(?:在|去|到|离|距|以)([\u4e00-\u9fffA-Za-z0-9·]{1,14}(?:殿|寺|公园|景区|广场|站|酒店|路|街))的?(?:附近|周边|旁边|为中心)")
DECLARED_DESTINATION = re.compile(
    r"(?:我|我们)?(?:准备|打算|计划|要|想|会)(?:去|到|前往)(" + PLACE_WORD
    + r")(?=游玩|玩|野餐|散步|逛|[,，。!?]|$)"
)
CLARIFICATION_REPLY = re.compile(
    r"^(?:是|对|是去|我说的是|我指的是|目的地是|去|到|就是|就去|就选)?("
    + PLACE_WORD + r")(?:吧|呀|呢)?[,，。!?]?"
)
CLARIFICATION_QUESTION = re.compile(r"哪个|哪座|哪里|叫什么|具体地址|哪个地方|哪家|请提供.{0,10}(?:地点|目的地|位置)")
PLACE_PREFIX = re.compile(r"^(?:你好|请问|帮我|我要去|我想去|我打算去|我们|在|到|去)+")
DRIVING = re.compile(r"开车回家时|(?:我|正在)?开车时|驾驶(?:回家)?时|驾车(?:回家)?时")
GEOFENCE = re.compile(r"(?:到达|到家|回到家|进入|离开|地理围栏)")
TRANSPORT = re.compile(r"交通|车站|地铁|公交|火车|列车|航班|航空|客车|班车|高铁|车票|bus|train", re.I)
WRONG_TRANSIT_TARGET = re.compile(r"餐馆|餐厅|商店|银行|健身房|加油站|图书馆|麦当劳")
PLACE_MENTIONS = re.compile(
    r"迪士尼乐园|迪士尼|环球影城|天安门|颐和园|故宫|中和殿|黄山|(?:" + CITY
    + r")(?!烤鸭|肉夹馍|菜|酒家)|(?<=[从到去离])(?:我的?家(?:里)?|家里|办公室|公司)|(?<=回)家"
)


def named_place(match):
    return PLACE_PREFIX.sub("", match[1]) if match else None


def clarification_place(text):
    return named_place(CLARIFICATION_REPLY.fullmatch(text))


def ground_location_evidence(intent, utterance):
    """Keep the observed evidence apart from defaults and label resolution."""
    code = canonical_intent_code(intent)
    text = compact(utterance)
    params = intent["parameters"].copy()

    if code in SCENE_ENABLE_INTENTS and DRIVING.search(text) and not GEOFENCE.search(text):
        params["trigger_type"] = "driving"
        if "回家" in text:
            params["destination"] = "家"
    if code in SEARCH_INTENTS:
        ground_search_evidence(params, text)
        if code in {"transit.query", "transit.bus_query"} and WRONG_TRANSIT_TARGET.search(text) and not TRANSPORT.search(text):
            params["reference_status"] = "intent_mismatch"
    if code in ROUTE_INTENTS and ROUTE_DEICTIC.search(text):
        if params.get("destination_source") not in FIXED and ref_kind(params.get("destination")) not in FIXED:
            params["reference_status"] = "unresolved"
    if STATED_LOCATION.search(text) and code.startswith("weather."):
        params["location"] = STATED_LOCATION.search(text)[1]
        params["location_source"] = NAMED

    # A location can be known even when its task role is ambiguous.
    if precision_for({**intent, "parameters": params}).tier == NEEDS_REVIEW:
        places = list(dict.fromkeys(m[0] for m in PLACE_MENTIONS.finditer(text)))
        if places:
            params["place_mentions"] = places

    if params == intent["parameters"]:
        return intent
    return {**intent, "parameters": params}


def ground_search_evidence(params, text):
    nearest = NEAREST.search(text)
    contextual = UNBOUND_PLACE.search(text)
    target_text = text[contextual.end():] if contextual else text
    target = next((
        m[0] for m in TARGET.finditer(target_text)
        if not target_text[m.end():].startswith(("附近", "周边", "旁边", "野餐"))
    ), None)
    if target:
        params["search_target"] = target
    radius = radius_meters(params.get("radius_m"), text)
    if not radius and (match := CN_RADIUS.search(text)):
        radius = CN_DIGITS[match[1]] * (1 if match[2] == "米" else 1000)
    if radius:
        params["radius_m"] = radius
    if nearest:
        params["search_scope"] = "nearest"
    elif WALKING_TIME.search(text):
        params["search_scope"] = "walking_time"
    elif EXACT_DISTANCE.search(text):
        params["search_scope"] = "distance"
    elif radius and ROUGH_RADIUS.search(text):
        params["search_scope"] = "rough_radius"
    elif NEARBY.search(text):
        params.setdefault("search_scope", "nearby")

    supplied = params.get("reference_place")
    stated = STATED_LOCATION.search(text)
    named_region = CITY_CONTEXT.search(text) or CITY_PREFIX.search(text)
    explicit_near = EXPLICIT_NEAR.search(text)
    fixed = params.get("location_source") in FIXED or ref_kind(params.get("location") or params.get("area")) in FIXED
    if explicit_near and not DEVICE_NEARBY.search(text):
        params["reference_place"] = explicit_near[1]
        params["location_source"] = NAMED
    elif stated and not nearest and not DEVICE_NEARBY.search(text) and not contextual:
        params["location"] = stated[1]
        params["location_source"] = NAMED
    elif named_region and not nearest and not DEVICE_NEARBY.search(text) and not contextual and not supplied and not fixed:
        params["location"] = named_region[1]
        params["location_source"] = NAMED
    elif contextual and not supplied and not fixed:
        params["reference_status"] = "unresolved"
        params.setdefault("search_scope", "nearby")
    elif nearest and not fixed and not supplied and not contextual:
        params["location_source"] = DEVICE
    elif radius and not fixed and not supplied and NEARBY.search(text):
        params["location_source"] = DEVICE


def resolve_task(intent, utterance):
    """Run defaults only after explicit slots and reference status are settled."""
    if precision_for(intent).tier != NEEDS_REVIEW or intent["parameters"].get("reference_status"):
        return intent
    first = ground_single_turn_review(intent, utterance)
    return first if first is not intent else resolve_remaining_single_turn(intent, utterance)
