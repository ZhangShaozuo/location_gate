"""Convert one published record into one or more atomic intent examples."""

from collections import defaultdict
from dataclasses import dataclass
import re

from .massive_labels import INTENT_LABELS
from .schema import INTENTS, NAMED, ORDER_STATUS, canonical_json, canonical_slot, compact, make_intent


@dataclass(frozen=True)
class Candidate:
    intent: dict
    utterance: str
    context: tuple
    turn: int
    original_intent: str
    stream: str | None = None


MASSIVE_MAP = {
    "weather_query": "weather.query", "transport_taxi": "ride.order",
    "transport_traffic": "traffic.query", "transport_ticket": "transit.ticket",
    "takeaway_order": "delivery.order", "takeaway_query": "delivery.search",
    "recommendation_locations": "place.search", "recommendation_events": "event.search",
    "transport_query": "transit.query", "news_query": "news.query",
    "alarm_set": "alarm.set", "alarm_query": "alarm.query", "alarm_remove": "alarm.remove",
    "calendar_set": "calendar.set", "calendar_query": "calendar.query",
    "calendar_remove": "calendar.remove", "audio_volume_up": "audio.volume.up",
    "audio_volume_down": "audio.volume.down",
}
CMPA_MAP = {
    "查询天气": "weather.query", "查询去某地的路线": "route.query",
    "查天气预警": "weather.alert", "查询天气预警": "weather.alert",
    "查询PM指数": "weather.environment", "查询紫外线": "weather.environment",
    "查询洗车指数": "weather.environment", "查询穿衣指数": "weather.environment",
    "查询运动指数": "weather.environment", "查询钓鱼指数": "weather.environment",
    "导航": "navigation.start", "退出导航": "navigation.stop", "打车": "ride.order",
    "查询当前位置": "location.self", "查询地址": "location.address",
    "订火车票": "transit.rail_ticket", "查询火车票": "transit.rail_ticket",
    "订机票": "transit.flight_ticket", "查询机票": "transit.flight_ticket",
    "查询机场航班流量": "transit.flight_traffic",
    "查询火车行程信息": "transit.trip_status", "查询航班行程信息": "transit.trip_status",
    "搜索公交": "transit.bus_query", "搜公交": "transit.bus_query", "查询公交": "transit.bus_query",
    "查询地铁": "transit.bus_query", "查看乘车码": "transit.ride_code",
    "查找手机": "device.find", "查找设备": "device.find",
    "打开查找我的设备": "device.find_menu",
    "开始运动": "fitness.start", "查询运动数据": "fitness.history",
    "查看运动类型": "fitness.activity_types",
    "寄快递": "package.ship", "收快递": "package.receive",
    "查待签收快递": "package.status", "查已签收快递": "package.status",
    "查找家电维修": "local_service.search", "查找保洁服务": "local_service.search",
    "查找收纳服务": "local_service.search",
    "查旅游指数": "travel.index", "查询旅游指数": "travel.index",
    "查找招聘信息": "jobs.search", "查找地点": "place.search",
    "播新闻": "news.play", "查询新闻": "news.query",
    "点外卖": "delivery.order", "设置闹钟": "alarm.set", "删除闹钟": "alarm.remove",
    "叫外卖": "delivery.order", "订餐厅": "restaurant.reserve", "小艺帮打订餐厅": "restaurant.reserve",
    "查询闹钟": "alarm.query", "创建日程": "calendar.set", "查询日程": "calendar.query",
    "设置日程": "calendar.set", "订酒店": "hotel.reserve", "查询周边": "place.search",
    "修改日程": "calendar.update", "取消日程": "calendar.remove", "删除日程": "calendar.remove",
    "创建提醒": "reminder.create", "创建备忘": "note.create", "记录信息": "information.capture",
    "调高音量": "audio.volume.up", "调低音量": "audio.volume.down",
}
SMP2019_MAP = {
    ("map", "ROUTE"): "route.query", ("map", "POSITION"): "location.address",
    ("weather", "QUERY"): "weather.query",
    ("flight", "QUERY"): "transit.flight_ticket", ("train", "QUERY"): "transit.rail_ticket",
    ("bus", "QUERY"): "transit.coach_query", ("news", "PLAY"): "news.play",
    ("app", "LAUNCH"): "app.launch", ("message", "SEND"): "message.send",
    ("music", "PLAY"): "music.play",
}
SMP2019_SELF = re.compile(r"(?:我|我们)(?:的)?(?:现在(?:在|的)|所在(?:的)?)")
SGD_MAP = {
    "GetWeather": "weather.query", "GetRide": "ride.order",
    "FindRestaurants": "restaurant.search", "ReserveRestaurant": "restaurant.reserve",
    "SearchHotels": "hotel.search", "FindHotels": "hotel.search",
    "ReserveHotel": "hotel.reserve", "BookHotel": "hotel.reserve",
    "FindBus": "transit.bus_query", "FindTrains": "transit.query",
    "GetTrainTimes": "transit.query", "FindFlights": "transit.flight_ticket",
    "SearchRoundtripFlights": "transit.flight_ticket", "SearchOnewayFlight": "transit.flight_ticket",
    "SearchOnewayFlights": "transit.flight_ticket", "BuyBusTicket": "transit.ticket",
    "BuyTrainTicket": "transit.rail_ticket", "FindEvents": "event.search",
    "FindAttractions": "place.search", "AddAlarm": "alarm.set",
    "GetAlarms": "alarm.query", "GetEvents": "calendar.query", "AddEvent": "calendar.set",
}
DOMAINS = {
    "景点": "place.search", "旅游景点": "place.search", "酒店": "hotel.search",
    "餐馆": "restaurant.search", "餐厅": "restaurant.search", "美食": "restaurant.search",
    "出租": "ride.order", "出租车": "ride.order", "打车": "ride.order",
    "地铁": "transit.bus_query", "公交": "transit.bus_query",
    "天气": "weather.query", "旅游": "place.search",
    "火车": "transit.query", "飞机": "transit.flight_ticket",
}
DETAILS = {
    "place.search": "place.details", "hotel.search": "hotel.details",
    "restaurant.search": "restaurant.details",
}
DETAIL_SLOTS = {
    "address", "phone_number", "opening_hours", "rating", "ticket_price", "ticket",
    "recommended_dish", "nearby_attractions", "nearby_restaurants", "nearby_hotels",
    "特点", "是否地铁直达", "房费", "房价", "价格", "price", "简介", "是否有停车场",
}
CROSSWOZ_DETAIL_SLOTS = DETAIL_SLOTS | {"hotel_type", "price_per_person", "游玩时间"}
SUBJECT_SLOTS = {"location", "area", "origin", "pickup", "destination", "name", "reference_place"}
GENERAL_DOMAINS = {"", "none", "general", "通用", "通用领域"}
ACTIVE_ACTS = {"inform", "request", "select", "affirm", "negate", "confirm", "recommend"}
SGD_USER_ACTS = {
    "INFORM", "INFORM_INTENT", "REQUEST", "REQUEST_ALTS", "SELECT", "AFFIRM",
    "AFFIRM_INTENT", "NEGATE", "NEGATE_INTENT",
}

MASSIVE_SLOT = re.compile(r"\[([a-z][a-z_0-9]*)\s*:\s*([^\]]+)\]")
MASSIVE_ORIGIN = re.compile(r"从\s*\[place_name\s*:\s*([^\]]+)\]")
MASSIVE_DEST = re.compile(r"(?:到|去|前往)\s*\[place_name\s*:\s*([^\]]+)\]")
CMPA_OUTPUT = re.compile(r"([^:\n：]+)\s*[:：]\s*\[(.*)\]\s*", re.DOTALL)
CMPA_PAIR = re.compile(r"(?:^|[,，;；])\s*([\w/ -]+?)\s*[:：]\s*")
PUBLIC_TRANSIT = re.compile(r"地铁|公交|高铁|火车|轻轨|列车|航班|车票")
BUS_SUBWAY = re.compile(r"地铁|公交|公共汽车|轻轨")
FLIGHT_TICKET = re.compile(r"机票|航班")
RAIL_TICKET = re.compile(r"火车|高铁|列车")
ROUTE = re.compile(r"怎么走|怎样走|指路|路线|导航|怎么回家")
DISTANCE = re.compile(r"多久|多远|多长时间|多少时间|距离|要多长|几公里|耗时")
DIRECT_NAV = re.compile(r"^(?:开始|现在|请|帮我|给我|步行|骑行|驾车)*导航(?:去|到|至|回)?")
POINTING_CONTEXT = re.compile(r"这里|这儿|那里|那儿|他家|他们家|这个地方|这个景点|这家|这些(?:景点|酒店|餐馆|地点)|上述|前面(?:的|提到的)")
FRESH_TASK = re.compile(r"另外|再.{0,5}(?:帮我|推荐|找|查询)|接下来|还想.{0,6}(?:找|查|去|订)|另一(?:家|个|座)|重新")
NEARBY_SLOTS = {"nearby_attractions", "nearby_restaurants", "nearby_hotels"}
SGD_NAME_BREAK = re.compile(r"(?<!^)(?=[A-Z])")


def utterance_candidate(code, pairs, raw, native, label=None):
    intent = make_intent(code, pairs, text=raw, single_turn=True, label=label)
    return Candidate(intent, raw, (("user", raw),), 0, native)


def adapt_massive(row):
    native, raw, annotated = row["intent"], row["utt"], row["annot_utt"]
    pairs = MASSIVE_SLOT.findall(annotated)
    if len(pairs) != annotated.count("["):
        raise ValueError("MASSIVE 槽位标记无法完整解析")
    code = MASSIVE_MAP.get(native, "massive." + native)
    if (
        native == "social_post" and row.get("locale") == "zh-CN" and str(row.get("id")) == "15387"
        and not any(canonical_slot(key) == "operation" for key, _ in pairs)
    ):
        # Manually reviewed: the source slots omit the post's current-location attachment.
        pairs.append(("operation", "share_current_location"))
    text = compact(raw)
    if native == "transport_query":
        if DIRECT_NAV.search(text):
            code = "navigation.start"
        elif BUS_SUBWAY.search(text):
            code = "transit.bus_query"
        elif PUBLIC_TRANSIT.search(text):
            code = "transit.query"
        elif DISTANCE.search(text):
            code = "route.estimate"
        elif ROUTE.search(text):
            code = "route.query"
    if native == "takeaway_query" and ORDER_STATUS.search(text):
        code = "delivery.status"
    if native == "transport_ticket":
        if FLIGHT_TICKET.search(text):
            code = "transit.flight_ticket"
        elif RAIL_TICKET.search(text):
            code = "transit.rail_ticket"
    if native == "recommendation_locations" and any(
        key == "business_type" and re.search(r"餐馆|餐厅|饭店|餐饮", value)
        for key, value in pairs
    ):
        code = "restaurant.search"
    if native.startswith("transport_"):
        for key, pattern in (("origin", MASSIVE_ORIGIN), ("destination", MASSIVE_DEST)):
            match = pattern.search(annotated)
            if match:
                pairs.append((key, match.group(1).strip()))
    yield utterance_candidate(code, pairs, raw, native, INTENT_LABELS.get(native))


def adapt_cmpa(row):
    raw = row["input"]
    match = CMPA_OUTPUT.fullmatch(row["output"])
    if not match:
        raise ValueError("CMPA-SLU output 不符合 意图: [槽位: 值] 格式")
    native, content = match.groups()
    native = native.strip()
    matches = list(CMPA_PAIR.finditer(content))
    if content.strip() and not matches:
        raise ValueError("CMPA-SLU 槽位无法解析")
    boundaries = [m.start() for m in matches[1:]] + [len(content)]
    pairs = [(a.group(1), content[a.end():end].strip()) for a, end in zip(matches, boundaries)]
    code = CMPA_MAP.get(native, "cmpa." + native)
    yield utterance_candidate(code, pairs, raw, native, native)


def smp2019_place(slots, prefix):
    parts = []
    for kind in ("country", "province", "city", "area", "poi"):
        value = slots.get(f"{prefix}_{kind}")
        if value and value not in parts:
            parts.append(value)
    return "".join(parts)


def adapt_smp2019(row):
    domain, action, raw, slots = row["domain"], row["intent"], row["text"], row["slots"]
    native = f"{domain}.{action.casefold()}"
    code = SMP2019_MAP.get((domain, action), "smp2019." + native)
    pairs = []
    if code in {"route.query", "transit.flight_ticket", "transit.rail_ticket", "transit.coach_query"}:
        pairs = [
            ("origin", smp2019_place(slots, "startLoc") or slots.get("Src")),
            ("destination", smp2019_place(slots, "endLoc") or slots.get("Dest")),
        ]
    if code in {"weather.query", "location.address", "news.play"}:
        location = smp2019_place(slots, "location")
        pairs = [("location", location), ("weather_descriptor", slots.get("subfocus"))]
        if code == "weather.query" and slots.get("subfocus") == "雨":
            code = "weather.rain"
        if code == "location.address" and not location:
            code = "location.self" if SMP2019_SELF.search(compact(raw)) else "smp2019.map.position_unknown"
    yield utterance_candidate(code, pairs, raw, native)


def domain_kind(domain):
    return DOMAINS.get(domain, "dialogue." + domain)


def action_groups(acts):
    groups = defaultdict(list)
    for act in acts:
        if len(act) != 4:
            raise ValueError(f"预期 [动作, 领域, 槽位, 值]，收到 {act!r}")
        action, domain, slot, value = act
        if domain.casefold() not in GENERAL_DOMAINS and action.casefold() in ACTIVE_ACTS:
            groups[domain].append((action.casefold(), canonical_slot(slot), value))
    return groups


def last_named(acts, subjects):
    for domain, group in action_groups(acts).items():
        names = {
            compact(value) for action, key, value in group
            if action in {"inform", "recommend"} and key == "name" and value
            and str(value).casefold() not in {"none", "?", "无"}
        }
        if len(names) == 1:
            subjects[domain_kind(domain)] = next(iter(names))
        elif names:
            subjects.pop(domain_kind(domain), None)


def resolve_dialogue_intent(
    domain, actions, state, subjects, utterance, *, detail_slots=DETAIL_SLOTS, turn_references=None,
):
    code = domain_kind(domain)
    requests = list(dict.fromkeys(key for action, key, _ in actions if action == "request"))
    filled = {key: value for action, key, value in actions if action in {"inform", "select"} and value}
    parameters = {**state, **filled}
    named = parameters.get("name") or subjects.get(code)
    source_domain = next(
        (value for action, key, value in actions
         if action == "select" and key == "source_domain" and value), None
    )
    anchor = None
    named_reference = None
    if isinstance(source_domain, str):
        source_code = domain_kind(source_domain)
        if turn_references:
            named_reference = turn_references.get(source_code)
        anchor = named_reference or subjects.get(source_code) or (named if source_code == code else None)
    if not anchor and named and (
        POINTING_CONTEXT.search(utterance) or NEARBY_SLOTS.intersection(requests)
    ):
        anchor = named
    if (
        code in DETAILS and named and requests and set(requests) <= detail_slots
        and all(key in SUBJECT_SLOTS for key in filled)
    ):
        code = DETAILS[code]
        anchor = named
    if requests:
        parameters["requested_slots"] = requests
    if named_reference and code in DETAILS:
        parameters["location_source"] = NAMED
    label = domain + "查询" if code not in INTENTS else None
    return make_intent(code, parameters.items(), text=utterance, anchor=anchor, label=label)


def bounded_context(history, window):
    return tuple(history[-window:])


def adapt_crosswoz(doc, window, *, keep_snapshots=False):
    turns = doc.get("messages", doc.get("message"))
    if not isinstance(turns, list):
        raise ValueError("CrossWOZ 缺少逐轮 messages 数组")
    history, subjects = [], {}
    states = defaultdict(dict)
    prior = {}
    for index, turn in enumerate(turns):
        role, raw = turn["role"].casefold(), turn["content"]
        actions = turn.get("dialog_act", [])
        if role in {"sys", "system", "assistant"}:
            history.append(("assistant", raw))
            last_named(actions, subjects)
            continue
        if role not in {"usr", "user"}:
            raise ValueError(f"未知 CrossWOZ 角色：{role}")
        history.append(("user", raw))
        groups = action_groups(actions)
        reference_domains = {
            value for domain, acts in groups.items() for action, key, value in acts
            if action == "select" and key == "source_domain" and isinstance(value, str)
            and value in groups and value != domain
        }
        turn_references = {}
        last_named((act for act in actions if act[1] in reference_domains), turn_references)
        for domain, acts in groups.items():
            if domain in reference_domains and all(action == "inform" and key == "name" for action, key, _ in acts):
                continue
            code = domain_kind(domain)
            state = states[code]
            if FRESH_TASK.search(raw) and any(action == "request" and key == "name" for action, key, _ in acts):
                state.clear()
                if not any(action == "select" and key == "source_domain" for action, key, _ in acts):
                    subjects.pop(code, None)
            for action, key, value in acts:
                if action == "inform" and value not in (None, ""):
                    state[key] = value
            detail_slots = CROSSWOZ_DETAIL_SLOTS | {key for _, key, _ in acts if key.startswith("酒店设施-")}
            intent = resolve_dialogue_intent(
                domain, acts, state, subjects, raw, detail_slots=detail_slots, turn_references=turn_references,
            )
            fingerprint = canonical_json(intent)
            if keep_snapshots or fingerprint != prior.get(code):
                prior[code] = fingerprint
                yield Candidate(intent, raw, bounded_context(history, window), index, domain)


def state_parameters(belief, domain):
    pairs = {}
    for joined, value in belief.get("inform slot-values", {}).items():
        prefix, separator, slot = joined.partition("-")
        if separator and domain_kind(prefix) == domain_kind(domain) and value not in (None, ""):
            pairs[canonical_slot(slot)] = value
    return pairs


def adapt_risawoz(doc, window, *, keep_snapshots=False):
    history, subjects, prior = [], {}, {}
    for index, record in enumerate(doc["dialogue"]):
        raw = record["user_utterance"]
        history.append(("user", raw))
        belief = record.get("belief_state") or {}
        groups = action_groups(record.get("user_actions") or [])
        for domain, acts in groups.items():
            current = state_parameters(belief, domain)
            if len(groups) == 1 and not any(action == "request" for action, _, _ in acts):
                acts = acts + [
                    ("request", canonical_slot(slot), "")
                    for slot in (belief.get("turn request") or [])
                ]
            intent = resolve_dialogue_intent(domain, acts, current, subjects, raw)
            key = domain_kind(domain)
            fingerprint = canonical_json(intent)
            if keep_snapshots or fingerprint != prior.get(key):
                prior[key] = fingerprint
                yield Candidate(intent, raw, bounded_context(history, window), index, domain)
        system = record.get("system_utterance")
        if system:
            history.append(("assistant", system))
        last_named(record.get("system_actions") or [], subjects)


def action_names(frame):
    return {x["act"] for x in frame.get("actions", [])}


def adapt_sgd(doc, window, *, keep_snapshots=False):
    history, prior = [], {}
    confirming_services = set()
    for index, turn in enumerate(doc["turns"]):
        role, raw = turn["speaker"], turn["utterance"]
        if role == "SYSTEM":
            history.append(("assistant", raw))
            confirming_services = {
                f["service"] for f in turn["frames"] if "CONFIRM" in action_names(f)
            }
            continue
        if role != "USER":
            raise ValueError(f"未知 SGD 角色：{role}")
        history.append(("user", raw))
        for frame in turn["frames"]:
            state = frame.get("state", {})
            native = state.get("active_intent", "NONE")
            if native == "NONE":
                continue
            acts = action_names(frame)
            if acts and not acts.intersection(SGD_USER_ACTS):
                continue
            service = frame["service"]
            code = SGD_MAP.get(native, "sgd." + native)
            label = SGD_NAME_BREAK.sub(" ", native)
            pairs = list(state.get("slot_values", {}).items())
            requested = state.get("requested_slots", [])
            if requested:
                pairs.append(("requested_slots", requested))
            if service in confirming_services:
                if "NEGATE" in acts:
                    pairs.append(("confirmation", "declined_or_corrected"))
                elif "AFFIRM" in acts:
                    pairs.append(("confirmation", "confirmed"))
                else:
                    pairs.append(("confirmation", "pending_reply"))
            intent = make_intent(code, pairs, text=raw, label=label)
            fingerprint = canonical_json(intent)
            if not keep_snapshots and fingerprint == prior.get(service):
                continue
            prior[service] = fingerprint
            yield Candidate(intent, raw, bounded_context(history, window), index, native, service)
        confirming_services.clear()


def adapt(dataset, row, window, *, keep_snapshots=False):
    if dataset == "massive":
        yield from adapt_massive(row)
    elif dataset == "cmpa":
        yield from adapt_cmpa(row)
    elif dataset == "crosswoz":
        yield from adapt_crosswoz(row, window, keep_snapshots=keep_snapshots)
    elif dataset == "smp2019":
        yield from adapt_smp2019(row)
    elif dataset == "risawoz":
        yield from adapt_risawoz(row, window, keep_snapshots=keep_snapshots)
    elif dataset == "sgd":
        yield from adapt_sgd(row, window, keep_snapshots=keep_snapshots)
