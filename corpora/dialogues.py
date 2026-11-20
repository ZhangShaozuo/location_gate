"""Assemble intent tasks from a complete dialogue before applying a location label."""

from collections import defaultdict
from dataclasses import dataclass, replace
import re

from .adapters import Candidate, FRESH_TASK, action_groups, adapt, domain_kind
from .grounding import (
    CLARIFICATION_QUESTION, DECLARED_DESTINATION, STATED_LOCATION, clarification_place,
    ground_location_evidence, named_place, resolve_task,
)
from .policy import DEVICE, FIXED, HISTORY, ROUTE_INTENTS, SEARCH_INTENTS, UNKNOWN
from .schema import canonical_intent_code, compact, items, ref_kind


DIALOGUE_SOURCES = {"crosswoz", "risawoz", "sgd"}
ACKNOWLEDGEMENT = re.compile(r"(?:好的?|嗯+|了解了?|行|可以|谢谢(?:了|你|您)?|明白了?|再见|ok(?:ay)?|thanks)[，。！？!?. ]*", re.I)
CORRECTION = re.compile(r"改成|改为|换成|说错了|我说的是|我指的是|不是.{0,12}是|instead|actually", re.I)
REQUEST = re.compile(r"找|推荐|查|预[订定]|帮我|需要|我想|find|search|book|check", re.I)
WITHIN_OPTIONS = re.compile(r"(?:这些|上述|上面那些|刚才推荐的)(?:景点|酒店|餐馆|地点)(?:当中|之中|中|里)")
OPTION_DOMAINS = {"nearby_attractions": "place", "nearby_hotels": "hotel", "nearby_restaurants": "restaurant"}
SEGMENT = re.compile(r"[。！？!?;；]|(?:另外|同时|接下来)")
TOPIC = {
    "weather": r"天气|下雨|weather|rain",
    "restaurant": r"餐馆|餐厅|吃饭|美食|用餐|restaurant",
    "hotel": r"酒店|宾馆|住宿|入住|hotel",
    "place": r"地点|景点|公园|便利店|健身房|超市|药店|商店|place|attraction",
    "ride": r"打车|叫车|出租车|上车|ride|cab",
    "route": r"路线|怎么走|多远|多久|directions|route",
    "transit": r"公交|地铁|车站|列车|火车|bus|train",
    "cinema": r"电影|影院|cinema",
}


@dataclass
class DialogueTask:
    candidate: Candidate
    evidence_turns: list[int]
    grounding_text: str


def transcript(source, raw):
    if source == "risawoz":
        return [
            (role, text)
            for turn in raw["dialogue"]
            for role, text in (("user", turn["user_utterance"]), ("assistant", turn.get("system_utterance")))
            if role == "user" or text
        ]
    if source == "sgd":
        return [("user" if turn["speaker"] == "USER" else "assistant", turn["utterance"]) for turn in raw["turns"]]
    return [
        ("user" if turn["role"].casefold() in {"usr", "user"} else "assistant", turn["content"])
        for turn in raw.get("messages", raw.get("message"))
    ]


def user_events(source, raw):
    """Retain the source adapter's turn numbering, including RiSAWOZ pairs."""
    if source == "risawoz":
        previous = ""
        for index, turn in enumerate(raw["dialogue"]):
            yield index, turn["user_utterance"], previous
            previous = turn.get("system_utterance") or ""
        return
    previous = ""
    for index, (role, text) in enumerate(transcript(source, raw)):
        if role == "user":
            yield index, text, previous
            previous = ""
        else:
            previous = text


def reference_turn_positions(source, raw):
    """Translate source user-turn indices into positions in the exported transcript."""
    if source != "risawoz":
        return {}
    positions = {}
    offset = 0
    for index, turn in enumerate(raw["dialogue"]):
        positions[index] = offset
        offset += 1 + bool(turn.get("system_utterance"))
    return positions


def previous_options(source, raw):
    """Index candidate lists from the immediately preceding assistant message."""
    if source == "sgd":
        return {}
    if source == "risawoz":
        turns = ((i + 1, t.get("system_actions") or []) for i, t in enumerate(raw["dialogue"]))
    else:
        turns = (
            (i + 1, t.get("dialog_act", []))
            for i, t in enumerate(raw.get("messages", raw.get("message")))
            if t["role"].casefold() in {"sys", "system", "assistant"}
        )
    result = {}
    for index, acts in turns:
        lists = defaultdict(list)
        for domain, group in action_groups(acts).items():
            for action, key, value in group:
                if action not in {"inform", "recommend"}:
                    continue
                category = domain_kind(domain).split(".")[0] if key == "name" else OPTION_DOMAINS.get(key)
                if category:
                    lists[category].extend(
                        compact(v) for v in items(value)
                        if isinstance(v, str) and v.strip() not in {"", "none", "无", "?", "没有"}
                    )
        result[index] = {category: list(dict.fromkeys(names)) for category, names in lists.items()}
    return result


def task_text(candidate, siblings):
    if len(siblings) == 1:
        return candidate.utterance
    pattern = TOPIC.get(canonical_intent_code(candidate.intent).split(".")[0])
    clauses = [clause for clause in SEGMENT.split(candidate.utterance) if pattern and re.search(pattern, clause, re.I)]
    return clauses[0] if len(clauses) == 1 else ""


def anchor_signature(params):
    return tuple(
        (key, str(params[key])) for key in ("reference_place", "location", "area", "pickup", "origin", "destination", "name")
        if params.get(key) and ref_kind(params[key]) in FIXED
    )


def merge_evidence(previous, current):
    before = previous["parameters"]
    after = {key: value for key, value in current["parameters"].items() if value not in (None, "", UNKNOWN)}
    parameters = {**before, **after}
    if after.get("location_source") == DEVICE:
        if not after.get("reference_place"):
            parameters.pop("reference_place", None)
        if not after.get("location") and not after.get("area"):
            parameters.pop("location", None)
            parameters.pop("area", None)
    if after.get("location_source") in FIXED | {DEVICE} and "reference_status" not in after:
        parameters.pop("reference_status", None)
    return {**current, "parameters": parameters}


def bind_reference(intent, place):
    code = canonical_intent_code(intent)
    params = intent["parameters"].copy()
    params.pop("reference_status", None)
    if code in SEARCH_INTENTS:
        params.update(reference_place=place, location_source=HISTORY)
    elif code in ROUTE_INTENTS:
        params.update(destination=place, destination_source=HISTORY)
        if params.get("origin_source", UNKNOWN) == UNKNOWN and not params.get("origin"):
            params["origin_source"] = DEVICE
    return {**intent, "parameters": params}


def assemble_dialogue(source, raw, window):
    """Collapse slot refinements into tasks while keeping separate user requests."""
    candidates = defaultdict(list)
    for candidate in adapt(source, raw, window, keep_snapshots=True):
        candidates[candidate.turn].append(candidate)
    tasks, active = [], {}
    declared = None
    awaiting = []
    options = previous_options(source, raw)

    for turn, utterance, assistant in user_events(source, raw):
        compact_text = compact(utterance)
        if ACKNOWLEDGEMENT.fullmatch(compact_text):
            continue
        if CLARIFICATION_QUESTION.search(assistant) and len(awaiting) == 1:
            if place := clarification_place(compact_text):
                task = awaiting.pop()
                grounded = bind_reference(task.candidate.intent, place)
                task.candidate = replace(task.candidate, intent=grounded)
                task.evidence_turns.append(turn)
                declared = place
                continue
        if place := named_place(STATED_LOCATION.search(compact_text) or DECLARED_DESTINATION.search(compact_text)):
            declared = place

        for candidate in candidates[turn]:
            text = task_text(candidate, candidates[turn])
            intent = ground_location_evidence(candidate.intent, text)
            if text and declared and intent["parameters"].get("reference_status") == "unresolved":
                intent = bind_reference(intent, declared)
            code = canonical_intent_code(intent)
            from_options = code in SEARCH_INTENTS and WITHIN_OPTIONS.search(text)
            if from_options:
                names = options.get(turn, {}).get(code.split(".")[0])
                params = intent["parameters"].copy()
                if names:
                    params.update(location_source=HISTORY, reference_candidates=names)
                    params.pop("reference_status", None)
                else:
                    params["reference_status"] = "unresolved"
                intent = {**intent, "parameters": params}
            key = (candidate.stream or candidate.original_intent, code)
            task = active.get(key)
            previous_anchors = dict(anchor_signature(task.candidate.intent["parameters"])) if task else {}
            current_anchors = dict(anchor_signature(intent["parameters"]))
            anchor_changed = any(previous_anchors.get(field, value) != value for field, value in current_anchors.items())
            fresh = text and not CORRECTION.search(text) and (
                FRESH_TASK.search(text) and (previous_anchors != current_anchors or code in SEARCH_INTENTS)
                or anchor_changed and REQUEST.search(text)
                or from_options and task and not task.candidate.intent["parameters"].get("reference_candidates")
            )
            if not task or fresh:
                task = DialogueTask(replace(candidate, intent=intent), [turn], text)
                tasks.append(task)
                active[key] = task
            else:
                task.candidate = replace(task.candidate, intent=merge_evidence(task.candidate.intent, intent))
                task.evidence_turns.append(turn)
                if not task.grounding_text and text:
                    task.grounding_text = text
            if task.candidate.intent["parameters"].get("reference_status") == "unresolved":
                if all(task is not item for item in awaiting):
                    awaiting.append(task)
            else:
                awaiting = [item for item in awaiting if item is not task]

    for task in tasks:
        task.candidate = replace(
            task.candidate,
            intent=resolve_task(task.candidate.intent, task.grounding_text),
        )
    return tasks
