"""Finite scenario inventory. Expected labels are specified independently of rule replay."""

EXACT, AREA, CITY, NA = "精确", "区域级模糊", "城市级模糊", "不涉及"
CURRENT = "device_current"

SEARCH = (
    "place.search", "restaurant.search", "hotel.search", "hotel.reserve", "delivery.search",
    "event.search", "local_service.search", "jobs.search", "transit.bus_query", "transit.query",
    "traffic.query", "cinema.query",
)
AIR_AND_RAIL = ("transit.flight_ticket", "transit.rail_ticket", "transit.ticket", "transit.coach_query")
ACTIONS = (
    ("导航", "路线规划", ("route.query", "route.estimate"), None),
    ("导航", "持续实时引导", ("navigation.start",), None),
    ("天气", "查天气和天气预警", ("weather.query", "weather.alert"), None),
    ("通用", "查询本机当前位置", ("location.self",), None),
    ("地图", "查找地点", ("place.search",), None),
    ("用车", "呼叫车辆", ("ride.order",), None),
    ("交通票务", "查询和预订机票及查机场流量", ("transit.flight_ticket", "transit.flight_traffic"), None),
    ("交通票务", "查询和预订火车票", ("transit.rail_ticket",), None),
    ("公交地铁", "查公交和地铁", ("transit.bus_query", "transit.query"), None),
    ("公交地铁", "查看乘车码", ("transit.ride_code",), "按本机城市选码与现网精确合标口径待确认"),
    ("安全", "查找设备", ("device.find", "device.find_menu"), None),
    ("运动", "开始运动", ("fitness.start",), None),
    ("运动", "查询运动数据和查看运动类型", ("fitness.history", "fitness.activity_types"), "已存记录用对照，按本机城市筛记录待确认"),
    ("快递", "寄快递", ("package.ship",), None),
    ("快递", "收快递及查询签收状态", ("package.receive", "package.status"), None),
    ("本地生活", "查家电维修、保洁和收纳", ("local_service.search",), None),
    ("旅游", "查询旅游指数", ("travel.index",), None),
    ("招聘", "查找招聘信息", ("jobs.search",), None),
    ("外卖", "下单外卖", ("delivery.order",), None),
    ("餐饮", "预订餐厅", ("restaurant.reserve",), None),
    ("日历与提醒", "修改、取消和删除日程", ("calendar.update", "calendar.remove"), "按本机城市筛选后删除待确认"),
    ("日历与提醒", "创建提醒", ("reminder.create",), "地理围栏触发的授权口径待确认"),
    ("备忘", "创建备忘", ("note.create",), None),
    ("通用", "记录信息", ("information.capture",), None),
)


def cases():
    for code in SEARCH:
        for scope, title in (("nearest", "只取最近候选"), ("distance", "输出实测距离"), ("walking_time", "按步行耗时筛选")):
            if scope == "walking_time" and code in {"jobs.search", "traffic.query"}:
                continue
            yield code, {"src": CURRENT, "scope": scope}, EXACT, title, False
            for band, dist in (("up_to_policy_limit", "硬性小半径"), ("above_policy_limit", "硬性较大半径")):
                yield code, {"src": CURRENT, "scope": scope, "radius_band": band}, EXACT, f"{dist}内{title}", False
        for slots, label, note in (
            ({"level": "city"}, CITY, "城市范围内查找"),
            ({"level": "city", "scope": "nearby"}, CITY, "周边检索明确以全市为限"),
            ({"level": "district"}, AREA, "行政区范围内查找"),
            ({"level": "district", "scope": "nearby"}, AREA, "先限所在区，再查大致周边"),
            ({"scope": "nearby"}, AREA, "附近粗筛"),
            ({"radius_band": "up_to_policy_limit"}, EXACT, "小半径是硬性筛选条件"),
            ({"radius_band": "above_policy_limit"}, "待复核", "较大硬半径的精度口径待确认"),
            ({"scope": "nearest", "level": "city"}, "待复核", "按实际距离找最近与只提供市级位置冲突"),
        ):
            yield code, {"src": CURRENT, **slots}, label, note, label == "待复核"
        for band in ("up_to_policy_limit", "above_policy_limit"):
            yield code, {"src": CURRENT, "scope": "rough_radius", "radius_band": band}, AREA, "给定大致范围且允许放宽半径", False
            yield code, {"src": CURRENT, "scope": "rough_radius", "radius_band": band, "level": "district"}, AREA, "限制在所在区内，按可放宽半径粗筛", False

    for code in ("route.query", "route.estimate", *AIR_AND_RAIL):
        tier = CITY if code in AIR_AND_RAIL else EXACT
        for live, other in (("from_src", "to_src"), ("to_src", "from_src")):
            for source in ("named_place", "saved_place", "previous_entity"):
                yield code, {live: CURRENT, other: source}, tier, "一端使用本机位置，另一端有独立来源", False
        for a in ("named_place", "saved_place", "previous_entity"):
            for b in ("named_place", "saved_place", "previous_entity"):
                yield code, {"from_src": a, "to_src": b}, NA, "起终点均有独立位置来源", False

    for code in ("route.query", "route.estimate"):
        yield code, {"from_src": CURRENT, "to_src": "target_device"}, EXACT, "从本机到已查得位置的目标设备", False
    for saved in ("named_place", "saved_place", "previous_entity"):
        for code, field in (("delivery.order", "src"), ("ride.order", "pickup_src"),
                            ("package.ship", "src"), ("package.receive", "src")):
            yield code, {field: saved}, NA, "接送或交接点已明确", False
        yield "ride.order", {"pickup_src": CURRENT, "to_src": saved}, EXACT, "本机定位用于乘车起点，终点有独立来源", False
    for code in ("transit.bus_query", "transit.query"):
        for source in ("named_place", "saved_place", "previous_entity"):
            yield code, {"src": CURRENT, "from_src": source, "level": "city"}, CITY, "从已知枢纽找通往本机城市的线路概览", False
            yield code, {"src": CURRENT, "from_src": source, "level": "district"}, AREA, "从已知枢纽找通往本机所在区的线路概览", False
    yield "traffic.query", {"from_src": CURRENT, "to_src": "previous_entity"}, EXACT, "按本机起点查询到已确认地点的沿途路况", False
    for slots in ({"trigger": "enter_location", "to_src": "saved_place"},
                  {"trigger": "leave_location", "to_src": "saved_place"},
                  {"trigger": "enter_location", "to_src": "previous_entity"},
                  {"trigger": "leave_location", "to_src": "previous_entity"}):
        yield "scene.enable", slots, EXACT, "进入或离开已确认地点触发，需检测本机位置", False

    yield from (
        ("device.find", {"op": "query_target_location"}, NA, "只查目标设备上报的位置", False),
        ("fitness.history", {"src": "stored_history"}, NA, "读取已存运动记录", False),
        ("fitness.activity_types", {}, NA, "查询可用运动类型", False),
        ("package.status", {}, NA, "根据运单查待签收或已签收状态", False),
        ("calendar.remove", {}, NA, "删除已经选中的日程", False),
        ("transit.ride_code", {"src": CURRENT}, "待复核", "按所在城市选码与现网默认精确口径待确认", True),
        ("fitness.history", {"src": CURRENT, "op": "filter_by_current_city"}, CITY, "用本机城市筛已存运动记录，现有规则会忽略该操作", True),
        ("calendar.remove", {"src": CURRENT, "op": "filter_by_current_city"}, CITY, "按本机城市筛选待删除日程，现有规则会忽略该操作", True),
        ("reminder.create", {"trigger": "enter_location"}, "待复核", "地理围栏提醒的现网授权口径待确认", True),
        ("reminder.create", {"trigger": "leave_location"}, "待复核", "离开围栏触发提醒的现网授权口径待确认", True),
    )
