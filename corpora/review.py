"""Ground confirmed single-turn review cases before projecting model slots."""

import re

from .policy import DEVICE, FIXED, NAMED, NEEDS_REVIEW, NO_POSITION, SAVED, UNKNOWN, precision_for
from .schema import (
    DEVICE_SCOPE_LEVELS, NEARBY, NO_DEVICE_LOCATION, compact, canonical_intent_code,
    ref_kind,
)


UNRESOLVED = re.compile(
    r"那里|那儿|他家|他们|它们|这家|那家|这(?:条|辆|趟|个)路线|"
    r"这餐厅|(?:这个|那个)(?:地方|景点|酒店|餐馆|餐厅|影院|订单|活动)|"
    r"这些|上述|刚才|那个路口|所需的位置|旅行目的地|(?:到|去)某地"
)
CITY = (
    r"北京|上海|广州|深圳|天津|重庆|成都|杭州|苏州|武汉|南京|西安|长沙|郑州|"
    r"济南|青岛|厦门|香港|澳门|台北|三亚|昆明|合肥|哈尔滨|沈阳|"
    r"纽约|洛杉矶|芝加哥|旧金山|奥兰多|曼谷|悉尼|伦敦|巴黎|东京"
)
CITY_CONTEXT = re.compile(r"(?:在|到|去|前往|来)\s*(" + CITY + r")(?:市)?(?!烤鸭|菜)")
CITY_PREFIX = re.compile(r"^(?:请|帮我|查一下|查询|搜索|看看|预订|找)*(" + CITY + r")(?:市)?(?=最新|的|上映|排片|列车|火车|酒店|景点|影院|附近|周边|路况)")
LANDMARK_SUFFIX = (
    r"植物园|动物园|游乐园|博物馆|图书馆|美术馆|电影院|电影城|影城|火车站|地铁站|机场|"
    r"公园|广场|钟楼|欢乐谷|天安门|颐和园|故宫|宾馆|酒店|餐厅|饭店|大厦|大学|医院|小区|路口"
)
ANCHOR = re.compile(
    r"(?:(?:在|以|离|距|到|去)\s*)?([\u4e00-\u9fff]{1,12}(?:" + LANDMARK_SUFFIX + r")|"
    r"天安门|颐和园|故宫|欢乐谷|(?:家里?|公司|办公室))"
    r"(?:的)?(?:附近|旁边|周边|周围|为中心|最近)"
)
NAMED_CINEMA = re.compile(
    r"^(?:哦哦[，,]|(?:我)?想|我想知道|我要|想知道|查找|查一查|查一下|查询|搜索|帮我|请)*"
    r"([\u4e00-\u9fff]{1,12}(?:电影院|电影城|影城|影院))"
    r"(?=正在|即将|热映|的热映|的排片|最[新热]|有播放|[。.!！?？]?$)"
)
NEAREST = re.compile(r"离我最近|距我最近|最近(?:的|一[家个])(?=[^，。!?]{0,12}(?:酒吧|店|站|馆|院|酒店|公园|取餐地点|电影院|餐馆|餐厅|麦当劳|肯德基|必胜客|出租车))")
LOCAL = re.compile(r"本地|当地|我(?:们)?这(?:里|边|儿)|这(?:里|边)|我(?:的)?地区|这(?:个)?地区|本区域")
LOCAL_CITY = re.compile(r"(?:本|当地|所在|这座)城市|城里|市区|全市")
CN_RADIUS = re.compile(r"(?:半径|[<≤]|不到|小于|不超过)?([一二两三四五六七八九十])\s*(公里|千米|米)(?:半径)?(?:范围内|以内|之内|内|左右)")
CN_DIGITS = dict(zip("一二两三四五六七八九十", (1, 2, 2, 3, 4, 5, 6, 7, 8, 9, 10)))
ROUTE_PAIR = re.compile(r"从([^，。!?]{1,24}?)\s*(?:到|去|前往)\s*([^，。!?]{1,24}?)(?=怎么|怎样|如何|坐|乘|打车|走|出发|的路线|的火车|的列车|[，。!?]|$)")
ROUTE_DEST = re.compile(r"(?:到|去|前往)\s*([^，。!?]{1,22}?)(?=怎么|怎样|多远|要多久|还要多久|要多长时间|多久|的(?:开车|步行|驾车)?路线|[，。!?]|$)")
HERE = re.compile(r"当前位置|现在的位置|从这(?:里|儿)|以这(?:里|儿)|离这(?:里|儿)")
GENERIC_TRANSIT_PLACE = {"车站", "火车站", "地铁站", "公交站", "站点", "地点", "指定地点", "下一站"}
TRANSIT_TICKET = re.compile(r"车票|订票|跨城.{0,5}车次")
FUTURE_ANCHOR = re.compile(r"它的周边|(?:再|顺便).{0,6}(?:景点|酒店|餐厅|餐馆|它的)?(?:周边|附近)|(?:景点|酒店|餐馆)的周边")
HOTEL_NAME = re.compile(r"(?:今晚|今天晚上|明晚)([\u4e00-\u9fff]{2,12}(?:酒店|宾馆))(?=[，。,!?.]|$)")
SAVED_ADDRESS = re.compile(r"我(?:的)?(?:家|房子|住处|办公室|公司)|家里|办公室|公司|家")
EXPLICIT_RIDE = re.compile(
    r"(?:叫|订|预约|订购|呼叫|请求|预订|安排|帮我找|给我|需要|搭乘|坐|打)[^，。!?]{0,18}"
    r"(?:出租[车汽]|优步|滴滴|来福车|计程车|一辆车|一辆|辆车|辆汽车|车来接)|"
    r"(?:出租车|优步|滴滴|计程车)[^，。!?]{0,14}(?:来接|接我|去|送我)|打辆?[的车]|打个车|"
    r"预约最近的优步|开车送我|有人送我|坐车去"
)


def position_value(value):
    if not value:
        return UNKNOWN
    if isinstance(value, str) and SAVED_ADDRESS.fullmatch(value):
        return SAVED
    return ref_kind(value)


def set_place(params, name, field="location_source", value="location"):
    if name and params.get(field, UNKNOWN) == UNKNOWN:
        source = position_value(name)
        if source != UNKNOWN:
            params.setdefault(value, name)
            params[field] = source


def fixed_place(params, text):
    if params.get("location_source") in FIXED:
        return True
    supplied = params.get("location") or params.get("area") or params.get("name")
    values = supplied if isinstance(supplied, list) else [supplied]
    if any(position_value(value) in FIXED or (
        isinstance(value, str) and ANCHOR.search(value)
    ) for value in values):
        if params.get("name") and not (params.get("location") or params.get("area")):
            params["location"] = params["name"]
        params["location_source"] = NAMED
        return True
    anchor = ANCHOR.search(text) or CITY_CONTEXT.search(text) or CITY_PREFIX.search(text)
    if anchor:
        name = re.sub(r"^(?:请|帮我|我想|在|去|到|找|查|想在)+", "", anchor[1])
        if name and not re.match(r"附近|周边|最近|本地|当地", name) and name not in {
            "酒店", "餐厅", "公园", "电影院", "电影城", "火车站",
        }:
            params.setdefault("location", name)
            params["location_source"] = NAMED
            return True
    return False


def set_device_scope(params, *, scope=None, level=None):
    params["location_source"] = DEVICE
    if scope:
        params["search_scope"] = scope
    if level:
        params["requested_granularity"] = level


def effective_scope(params, text):
    """Complete explicit single-turn local scope and radius cues."""
    radius = CN_RADIUS.search(text)
    if radius and "radius_m" not in params:
        params["radius_m"] = CN_DIGITS[radius[1]] * (1 if radius[2] == "米" else 1000)
        if "左右" in radius[0]:
            params["search_scope"] = "rough_radius"
    for level, cue in DEVICE_SCOPE_LEVELS:
        if cue.search(text):
            set_device_scope(params, level=level)
            return True
    if NEAREST.search(text):
        set_device_scope(params, scope="nearest")
    elif params.get("search_scope") or params.get("radius_m"):
        set_device_scope(params)
    elif LOCAL_CITY.search(text):
        set_device_scope(params, level="city")
    elif NEARBY.search(text) or LOCAL.search(text):
        set_device_scope(params, scope="nearby")
    else:
        return False
    return True


def ground_search(code, params, text):
    if fixed_place(params, text):
        return
    if code == "hotel.reserve" and (names := HOTEL_NAME.findall(text)):
        set_place(params, names[-1])
        return
    if FUTURE_ANCHOR.search(text) and not (HERE.search(text) or re.search(r"我(?:的)?附近|这附近", text)):
        return
    if effective_scope(params, text):
        return
    if code == "restaurant.search" and re.search(r"餐馆|餐厅|饭店|吃饭|用餐|推荐|找一家", text):
        if not re.search(r"导航|营业时间|评分(?:是|多少)|怎么走", text) or re.search(r"推荐|找", text):
            set_device_scope(params, scope="nearby")
    elif code in {"hotel.search", "hotel.reserve"} and (
        re.search(r"酒店|宾馆|住宿|入住|房间|[订定]房", text)
        and re.search(r"找|查|推荐|[订定]|住|有没有|有无|能否|请", text)
    ):
        set_device_scope(params, level="city")


def ground_delivery(params, text):
    if re.search(
        r"我的订单|我(?:刚)?点的餐|(?:我的|已经|刚)订(?:单|的)|送我的订单|在送我的|"
        r"(?:我的|我点的).{1,12}(?:还(?:有|要)多久|几点到|什么时候(?:到|好|送))|"
        r"(?:披萨|比萨|外卖|订单).{0,5}(?:马上|快|已经)(?:就)?(?:到|送到)",
        text,
    ):
        params["location_source"] = NO_POSITION
    elif fixed_place(params, text) or effective_scope(params, text):
        return
    elif re.search(r"评分.{0,6}(?:外卖|外送)|(?:列出|推荐|附近).{0,16}(?:外卖|外送)|在哪里.{0,8}(?:外卖|外送)", text):
        set_device_scope(params, scope="nearby")
    elif re.search(r"(?:外送|外卖)(?:的费用|菜单|选项)|(?:餐厅|餐馆).{0,6}(?:外送|外卖)吗", text):
        params["location_source"] = NO_POSITION


def ground_ride(params, text):
    route = ROUTE_PAIR.search(text)
    if route:
        set_place(params, route[1], "pickup_source", "pickup")
        set_place(params, route[2], "destination_source", "destination")
    elif pickup := re.search(r"(?:到|去|(?<!现)在)([^，。!?]{1,18}?)(?:来)?接(?:上)?我", text):
        set_place(params, pickup[1], "pickup_source", "pickup")
    if params.get("pickup_source") in FIXED:
        return
    if re.search(r"(?:在哪|哪里|最近).{0,12}(?:哪一辆|公司|号码)|电话号码|如何叫|怎么叫|打开.{0,4}$", text):
        return
    if (HERE.search(text) and re.search(r"出租车|优步|滴滴|打车|叫车", text)) or EXPLICIT_RIDE.search(text):
        params["pickup_source"] = DEVICE


def ground_route(params, text):
    pair = ROUTE_PAIR.search(text)
    if pair:
        set_place(params, pair[1], "origin_source", "origin")
        set_place(params, pair[2], "destination_source", "destination")
    if match := re.search(r"^([^，。!?]{1,18})离(我的(?:房子|家|公司|办公室)|这里|这儿)(?:有)?多远", text):
        set_place(params, match[1], "destination_source", "destination")
        set_place(params, match[2], "origin_source", "origin")
    if params.get("destination_source", UNKNOWN) == UNKNOWN:
        destination = ROUTE_DEST.search(text) or re.search(
            r"([^，。!?]{1,15}(?:酒吧|星巴克|麦当劳|必胜客|银行|休息站))(?=吗?$|怎么走|有多远|多远)", text
        )
        if destination:
            name = re.sub(r"^(?:最近的|我能知道|请告诉我|去|到)+", "", destination[1])
            set_place(params, name, "destination_source", "destination")
    if HERE.search(text) and params.get("origin_source", UNKNOWN) == UNKNOWN:
        params["origin_source"] = DEVICE
    if params.get("origin_source", UNKNOWN) == UNKNOWN and params.get("destination_source") in FIXED:
        if not re.search(r"从|以.{0,15}为起点", text):
            params["origin_source"] = DEVICE


def ground_transit(params, text):
    if not re.search(r"车站|站点|站口|火车|地铁|公交|列车|航班|航空|客车|班车|高铁|车票", text):
        return
    if re.search(r"(?:怎么|如何|怎样|到哪儿).{0,10}(?:买|订|预订).{0,8}(?:火车)?票", text):
        params["location_source"] = NO_POSITION
        return
    if pair := ROUTE_PAIR.search(text):
        set_place(params, pair[1], "origin_source", "origin")
        set_place(params, pair[2], "destination_source", "destination")
        if params.get("origin_source") in FIXED and params.get("destination_source") in FIXED:
            return
    if re.search(r"(?:从|离开|由)(?:这里|这儿|本地|我(?:的)?当前位置)", text):
        params["origin_source"] = DEVICE
        location = params.get("location")
        if isinstance(location, str) and re.search(r"(?:到|去|开往)" + re.escape(location), text):
            set_place(params, location, "destination_source", "destination")
            if params.get("destination") == location:
                params.pop("location")
        set_device_scope(params, level="city")
        return
    for key in ("location", "area", "name"):
        if isinstance(params.get(key), str) and params[key] in GENERIC_TRANSIT_PLACE:
            params.pop(key)
    if re.search(r"^(?:请|帮我|查询|查一下|看看)*(?:[^\s，。!?]{1,12})?(?:火车|列车)时刻表[。!?]?$", text):
        if station := re.search(r"([\u4e00-\u9fff]{1,12}站)(?:的)?(?:火车|列车)", text):
            set_place(params, station[1])
        elif not fixed_place(params, text):
            params["location_source"] = NO_POSITION
    elif re.search(r"车站|站点|站口|火车|地铁|公交|列车|航班", text):
        if fixed_place(params, text):
            return
        if TRANSIT_TICKET.search(text):
            params["origin_source"] = DEVICE
            set_device_scope(params, level="city")
        else:
            effective_scope(params, text)


def ground_activity(params, text):
    if fixed_place(params, text) or effective_scope(params, text):
        return
    if re.search(r"我的活动|(?:今晚的|今天的|明天的).{1,10}(?:美食节|音乐节|演唱会)在哪里", text):
        params["location_source"] = NO_POSITION


def ground_traffic(params, text):
    if re.search(r"从(?:这里|当前位置|我现在的位置)", text) and re.search(r"路况|堵车|交通", text):
        ground_route(params, text)
        return
    if match := re.match(r"([\u4e00-\u9fff]{2,16})(?:现在|今天|目前)的?交通状况", text):
        if match[1] not in {"请问", "告诉我", "给我", "看看", "查询"}:
            set_place(params, match[1])
            return
    if fixed_place(params, text) or effective_scope(params, text):
        return
    if re.search(r"路况|交通(?:情况|状况|拥堵|最新消息)|车流|堵车|拥堵", text) and not re.search(
        r"去公司|上班|通勤|下班|回家|哪条|路上|什么是交通|我会|车流长度", text
    ):
        set_device_scope(params, level="city")


def ground_cinema(params, text):
    if fixed_place(params, text):
        return
    if cinema := NAMED_CINEMA.search(text):
        name = cinema[1]
        if not re.match(r"附近|周边|最近|本地|当地|现[在有]|哪[家个]|离我", name):
            set_place(params, name)
            return
    if re.search(r"电影院|影院|影城|电影城", text):
        if not effective_scope(params, text) and re.search(r"放映|电影|热映|上映", text):
            set_device_scope(params, level="city")
    elif re.search(r"排片|附近.{0,6}电影|我(?:们)?(?:这边|这座城市|所在城市)", text):
        set_device_scope(params, level="city")
    elif re.search(r"电影|影片|新片|大片", text):
        params["location_source"] = NO_POSITION


def ground_scene(params, text):
    if params.get("trigger_type") or re.search(r"开车回家", text):
        return
    if re.search(r"(?:到达|进入|离开)[^，。!?]{1,18}(?:时|后|以后|就)|(?:到家|到公司|到学校)(?:时|后|以后|就)|地理围栏", text):
        params["trigger_type"] = "geofence"
    elif re.search(r"连接蓝牙", text):
        params["trigger_type"] = "bluetooth"
    elif re.search(r"连接\s*wi-?fi", text, re.I):
        params["trigger_type"] = "wifi"
    elif re.search(r"定时|(?:早上|晚上|下午|上午)\s*\d+点|\d+点(?:钟|到)", text):
        params["trigger_type"] = "time"
    elif re.search(r"智能情景", text) and not re.search(r"(?:时|之后|之前|以后|的话|条件|自动)", text):
        params["trigger_type"] = "manual"


def ground_device(params, text):
    if params.get("operation"):
        return
    if re.search(r"导航", text):
        params["operation"] = "navigate_to_target"
    elif re.search(r"响铃|播放铃声", text):
        params["operation"] = "ring"
    elif re.search(r"找|丢|消失|不见|在哪", text) and re.search(r"手机|设备|手表|平板", text):
        params["operation"] = "query_target_location"


GROUNDERS = {
    "delivery.search": ground_delivery, "ride.order": ground_ride,
    "route.query": ground_route, "route.estimate": ground_route, "transit.query": ground_transit,
    "event.search": ground_activity, "traffic.query": ground_traffic, "cinema.query": ground_cinema,
    "scene.enable": ground_scene, "device.find": ground_device,
}
SEARCH_REVIEW_CODES = {"restaurant.search", "hotel.search", "hotel.reserve", "place.search"}
REVIEW_ALIASES = {"smp2019.cinemas.query": "cinema.query", "smp2019.cinemas.date_query": "cinema.release_date"}


def ground_single_turn_review(intent, utterance):
    """Return a grounded candidate when a confirmed review rule can resolve it."""
    original = canonical_intent_code(intent)
    code = REVIEW_ALIASES.get(original, original)
    params = intent["parameters"].copy()
    text = compact(utterance)
    if not text or UNRESOLVED.search(text) or NO_DEVICE_LOCATION.search(text):
        return intent
    if code in SEARCH_REVIEW_CODES:
        ground_search(code, params, text)
    elif code in GROUNDERS:
        GROUNDERS[code](params, text)
    elif code != "cinema.release_date":
        return intent
    resolved = {**intent, "intent_id": code, "parameters": params}
    return intent if precision_for(resolved).tier == NEEDS_REVIEW else resolved
