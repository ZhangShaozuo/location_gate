#!/usr/bin/env python3
"""Expand normalized location scenarios and assemble the three-class training file."""

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "data-balance-v12"))
from build import DISPLAY, LABELS, NA, REVIEW, canonical, key, read_jsonl, write_jsonl

EXACT, AREA, CITY = LABELS
OUTSIDE = "超出范围"
CURRENT = "device_current"
SOURCE_NAMES = {
    "named_place": "用户指定地点", "saved_place": "已保存地点", "previous_entity": "已确认的前文地点",
}
FIXED_SOURCES = tuple(SOURCE_NAMES)

# The public policy receives the original slots. Training retains normalized evidence.
SEARCH_RULES = (
    ({"level": "city"}, CITY, "只按当前城市选择"),
    ({"level": "district"}, AREA, "只按当前行政区选择"),
    ({"scope": "nearby"}, AREA, "查本机周边，不按距离排序"),
    ({"scope": "rough_radius", "radius_m": 250}, AREA, "小范围近似粗筛，可放宽半径"),
    ({"scope": "rough_radius", "radius_m": 1800}, AREA, "较大范围近似粗筛，可放宽半径"),
    ({"scope": "nearest"}, EXACT, "按本机与候选的距离判定最近"),
    ({"scope": "distance"}, EXACT, "计算在本机与候选之间的实际距离"),
    ({"scope": "walking_time"}, EXACT, "用本机作为步行起点按耗时筛选"),
    ({"radius_m": 350}, EXACT, "以本机为中心执行小半径硬筛选"),
)
SEARCH_BORDER = (
    ({"radius_m": 1200}, REVIEW, "较大半径硬筛选，v11 没有确定精度"),
    ({"scope": "nearest", "level": "city"}, REVIEW, "最近排序与只提供城市粒度冲突"),
    ({"level": "country"}, OUTSIDE, "只请求所在国家，超出当前三档"),
)


def make_cases(catalog):
    result = []

    def add(code, family, slots, label, reason):
        result.append((code, family, slots, label, reason))

    for code in catalog["search"]:
        for slots, expected, note in (*SEARCH_RULES, *SEARCH_BORDER):
            if slots.get("scope") == "walking_time" and code in {"jobs.search", "traffic.query"}:
                continue
            add(code, "search_constraint", {"src": CURRENT, **slots}, expected, note)
        for source in FIXED_SOURCES:
            for scope in ("nearby", "nearest"):
                add(code, "search_anchor", {"src": source, "scope": scope}, NA,
                    f"以{SOURCE_NAMES[source]}为搜索参照")
        add(code, "search_anchor", {"scope": "nearby", "anchor": "unresolved"}, REVIEW,
            "说了附近但前文可能指向未确认地点")

    for code, operations in catalog["search_operations"].items():
        for operation, restrictions in operations.items():
            for index in restrictions:
                slots, expected, note = SEARCH_RULES[index]
                add(code, "search_operation", {"src": CURRENT, "op": operation, **slots}, expected, note)
            add(code, "search_operation", {"src": "named_place", "op": operation}, NA,
                "用指定位置执行该查询操作")

    for code in catalog["city_default"]:
        for slots in ({}, {"src": CURRENT}, {"src": CURRENT, "level": "city"}):
            add(code, "city_context", slots, CITY, "城市级聚合查询，明确或默认使用本机所在城市")
        for source in FIXED_SOURCES:
            add(code, "city_context", {"src": source}, NA, f"查询区域由{SOURCE_NAMES[source]}提供")
        add(code, "city_context", {"anchor": "unresolved"}, REVIEW, "查询地区的指代未确认")

    for code in catalog["route"] + list(catalog["tickets"]):
        tier = EXACT if code in catalog["route"] else CITY
        for device_role, other_role in (("from_src", "to_src"), ("to_src", "from_src")):
            for other in (None, *FIXED_SOURCES):
                slots = {device_role: CURRENT}
                if other is not None:
                    slots[other_role] = other
                add(code, "endpoint_roles", slots, tier,
                    f"本机用于确定{'出发地' if device_role == 'from_src' else '目的地'}")
        for start, end in (("named_place", "named_place"), ("saved_place", "named_place"),
                           ("previous_entity", "saved_place"), ("named_place", "previous_entity")):
            add(code, "endpoint_roles", {"from_src": start, "to_src": end}, NA, "起终点均有独立位置来源")
        add(code, "endpoint_roles", {"anchor": "unresolved"}, REVIEW, "任务的起点或终点未被确认")

    for code, operations in catalog["tickets"].items():
        for op in operations:
            for role, other in (("from_src", "to_src"), ("to_src", "from_src")):
                add(code, "ticket_operation", {role: CURRENT, other: "named_place", "op": op}, CITY,
                    "本机位置用于确定城市级票务端点")
            add(code, "ticket_operation", {"from_src": "named_place", "to_src": "named_place", "op": op},
                NA, "出发与到达地已给定")

    for destination in (None, *FIXED_SOURCES, "target_device"):
        for tracking in (None, "route", "no_route"):
            slots = {"from_src": CURRENT}
            if destination is not None:
                slots["to_src"] = destination
            if tracking is not None:
                slots["track"] = tracking
            add("navigation.start", "live_navigation", slots, NA if tracking == "no_route" else EXACT,
                "仅预览路线" if tracking == "no_route" else "持续引导使用本机精确位置")
    for source in FIXED_SOURCES:
        for destination in ("named_place", "saved_place"):
            add("navigation.start", "navigation_preview",
                {"from_src": source, "to_src": destination, "track": "no_route"}, NA,
                "起终点已知且只预览路线")

    for code, operations in catalog["content"].items():
        for source in (None, *FIXED_SOURCES):
            for trigger in operations:
                slots = {"trigger": trigger}
                if source is not None:
                    slots["fence_src"] = source
                add(code, "location_trigger", slots, EXACT, "检测本机进入或离开地理围栏")
        for trigger in catalog["non_location_triggers"][code]:
            add(code, "non_location_trigger", {"trigger": trigger}, NA,
                "时间、连接状态或手动操作足以触发")

    for code in catalog["current_content"]:
        add(code, "location_attachment", {"src": CURRENT, "op": "share_current_location"}, CITY,
            "文档或动态只需附带本机所在城市")
        add(code, "location_attachment", {"src": CURRENT, "op": "share_current_location", "level": "city"},
            CITY, "显式要求附上当前城市")
        for source in FIXED_SOURCES:
            add(code, "location_attachment", {"src": source}, NA, "沿用已知地点作为内容标签")
        add(code, "location_attachment", {}, NA, "普通内容操作不附上本机位置")

    for code, item in catalog["addresses"].items():
        role = item["role"]
        for operation in item["operations"]:
            add(code, "service_address", {role: CURRENT, "op": operation}, EXACT,
                "服务使用本机当前位置作为准确交接点")
            for source in FIXED_SOURCES:
                add(code, "service_address", {role: source, "op": operation}, NA,
                    f"服务直接使用{SOURCE_NAMES[source]}")
            add(code, "service_address", {"op": operation, "anchor": "unresolved"}, REVIEW,
                "交接地点或地址未确认")
        for source in FIXED_SOURCES:
            add(code, "service_address", {role: source}, NA, "固定交接点可直接读取")
        add(code, "service_address", {role: CURRENT}, EXACT, "明确用本机当前位置交接")

    for code, cases in catalog["specific"].items():
        for slots, value, reason in cases:
            add(code, "intent_specific", slots, value, reason)
    return result


def exported(row):
    return {field: row[field] for field in ("intent", "slots", "label")}


def core_key(row):
    slots = {field: value for field, value in row["slots"].items() if field != "fence_src"}
    if slots.get("op") not in {"share_current_location", "navigate_to_target", "query_target_location", "ring"}:
        slots.pop("op", None)
    return key({"intent": row["intent"], "slots": slots})


def export(base, out, catalog, intents, get_policy, ref_kind, threshold):
    domains = {code: domain for domain, codes in catalog["domains"].items() for code in codes}
    if len(domains) != sum(map(len, catalog["domains"].values())) or domains.keys() - intents.keys():
        raise ValueError("领域映射包含重复或未知意图")
    by_name = {intents[code]: domain for code, domain in domains.items()}
    indexed = {}
    raw = read_jsonl(base)
    for row in raw:
        signature = key(row)
        if signature in indexed or row["label"] not in LABELS or row["intent"] not in by_name:
            raise ValueError(f"基础数据含重复、无效标签或无领域映射的意图：{row}")
        indexed[signature] = exported(row)
    base_keys = set(indexed)
    audit, controls, review = {}, [], []
    for code, family, slots, expected, reason in make_cases(catalog):
        if code not in domains:
            raise ValueError(f"意图 {code} 缺少领域映射")
        case = {"intent": intents[code], "slots": slots}
        normalized = canonical(case, ref_kind, threshold)
        if "fence_src" in slots:
            normalized["slots"]["fence_src"] = slots["fence_src"]
        signature = key(normalized)
        tier = get_policy(code, slots).tier
        policy = DISPLAY.get(tier, tier)
        if signature in audit:
            if audit[signature]["label"] != expected:
                raise ValueError(f"同一组合人工标签冲突：{signature}")
            continue
        previous = indexed.get(signature)
        if previous is not None and previous["label"] != expected:
            raise ValueError(f"与现有训练标签冲突：{signature}")
        record = {
            **normalized, "label": expected, "domain": domains[code], "family": family,
            "source": "v13_synthetic", "original_slots": slots, "rule_label": policy, "reason": reason,
        }
        audit[signature] = record
        if policy != expected or expected in (REVIEW, OUTSIDE):
            review.append(record)
        elif expected == NA:
            controls.append(record)
        elif expected in LABELS:
            indexed.setdefault(signature, exported(record))
        else:
            raise ValueError(f"未知标签：{expected}")
    assert base_keys <= set(indexed)
    train = list(indexed.values())
    additions = [row for signature, row in indexed.items() if signature not in base_keys]
    original_domains = Counter(by_name[row["intent"]] for row in raw)
    additions_domains = defaultdict(Counter)
    controls_domains = Counter(row["domain"] for row in controls)
    counts = defaultdict(Counter)
    for row in additions:
        additions_domains[by_name[row["intent"]]][row["label"]] += 1
    for row in train:
        counts[by_name[row["intent"]]][row["label"]] += 1
    summary = {
        "base_rows": len(raw), "added_train": len(additions), "train_rows": len(train),
        "base_core_combinations": len({core_key(row) for row in raw}),
        "train_core_combinations": len({core_key(row) for row in train}),
        "train_intents": len({row["intent"] for row in train}), "train_domains": len(counts),
        "audited_intents": len({row["intent"] for row in audit.values()}), "audited_domains": len({row["domain"] for row in audit.values()}),
        "train_labels": dict(Counter(row["label"] for row in train)),
        "added_labels": dict(Counter(row["label"] for row in additions)),
        "synthetic_unique": len(audit), "synthetic_overlap_with_base": len(audit.keys() & base_keys),
        "not_applicable": len(controls), "review_or_outside": len(review),
        "review_labels": dict(Counter(row["label"] for row in review)),
        "policy_mismatches": sum(row["rule_label"] != row["label"] for row in review),
        "by_domain": {
            domain: {"base": original_domains[domain], "added": sum(additions_domains[domain].values()),
                     "labels": dict(counts[domain]), "controls": controls_domains[domain]}
            for domain in catalog["domains"]
        },
    }
    out.mkdir(parents=True)
    write_jsonl(out / "train.jsonl", train)
    write_jsonl(out / "added_train.jsonl", additions)
    write_jsonl(out / "synthetic.jsonl", audit.values())
    write_jsonl(out / "not_applicable.jsonl", controls)
    write_jsonl(out / "review.jsonl", review)
    summary["train_sha256"] = sha256((out / "train.jsonl").read_bytes()).hexdigest()
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path, help="v12 全量训练文件")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--repo", type=Path, default=ROOT.parent, help="兼容 v11 标注规则的仓库目录")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("--out 需要使用新目录")
    sys.path.insert(0, str(args.repo.resolve()))
    from corpora.policy import POLICY_VERSION, RADIUS_PRECISE_M
    from corpora.schema import INTENTS, policy_from_slots, ref_kind
    if POLICY_VERSION != "precision-weak-v11-whole-dialogue":
        parser.error(f"要求 v11 规则，实际为 {POLICY_VERSION}")
    catalog = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
    export(args.base, args.out, catalog, INTENTS, policy_from_slots, ref_kind, RADIUS_PRECISE_M)


if __name__ == "__main__":
    main()
