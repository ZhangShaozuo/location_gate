#!/usr/bin/env python3
"""Download public intent corpora and build per-intent location precision JSONL."""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from tarfile import TarError
from tempfile import TemporaryDirectory
from zipfile import BadZipFile

from corpora.adapters import Candidate, adapt
from corpora.policy import POLICY_VERSION
from corpora.review import ground_single_turn_review
from corpora.schema import (
    CLASSES, NEEDS_REVIEW, NOT_APPLICABLE, PRECISION_CLASSES, REPORTED_TIERS,
    canonical_intent_code, canonical_json, chinese_intent_name, compact, make_intent,
    INTENT_CODES_BY_NAME, model_slots, policy_from_slots, precision_for, reviewed_label,
)
from corpora.sources import NAMES, SPLITS, TRAIN_ONLY_SOURCES, ensure_source, source_records


SCHEMA_VERSION = "location-device-slots-v6"
LABEL_NAMES = {
    "精确": "精确", "区域级": "区域级模糊", "城市级": "城市级模糊", "国家级": "国家级模糊",
    NOT_APPLICABLE: NOT_APPLICABLE, NEEDS_REVIEW: NEEDS_REVIEW,
}


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("必须是正整数")
    return number


def nonnegative_int(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("必须是非负整数")
    return number


def stable_hash(value):
    return hashlib.blake2b(value.encode("utf-8"), digest_size=16).hexdigest()


def make_row(candidate, source, split, native_id, sequence, with_reference, *, intent=None):
    intent = intent if intent is not None else candidate.intent
    slots = model_slots(intent)
    policy = policy_from_slots(canonical_intent_code(intent), slots)
    expected = precision_for(intent)
    if policy.tier != expected.tier:
        raise ValueError(f"{chinese_intent_name(intent)} 的槽位无法还原标签：{slots} / {expected.tier} / {policy.tier}")
    group = f"{source}:{split}:{native_id}"
    row = {
        "id": f"{group}:{candidate.turn}:{sequence}",
        "intent": chinese_intent_name(intent),
        "slots": slots,
        "label": LABEL_NAMES[policy.tier],
    }
    if with_reference:
        row["ref"] = {"text": candidate.utterance, "native": candidate.original_intent}
        if len(candidate.context) > 1:
            row["ref"]["ctx"] = candidate.context[:-1]
    metadata = expected.requirements()
    if expected.review:
        metadata.update(review=True, rule=expected.rule)
    if metadata:
        row["meta"] = metadata
    return row, policy.tier


def init_database(conn):
    conn.executescript("""
        CREATE TABLE candidates(
            id TEXT PRIMARY KEY,
            dataset TEXT NOT NULL,
            split TEXT NOT NULL,
            priority INTEGER NOT NULL,
            tier TEXT NOT NULL,
            read_order INTEGER NOT NULL,
            digest TEXT NOT NULL,
            rank TEXT NOT NULL,
            intent_id TEXT NOT NULL,
            intent_label TEXT NOT NULL,
            review INTEGER NOT NULL,
            row_json TEXT NOT NULL
        );
        CREATE TABLE native_groups(dataset TEXT, split TEXT, native_id TEXT,
            PRIMARY KEY(dataset, split, native_id));
        CREATE TABLE single_turn_candidates(id TEXT PRIMARY KEY);
    """)


def ingest(conn, datasets, args):
    groups = defaultdict(Counter)
    no_intents = defaultdict(Counter)
    split_priority = {name: i for i, name in enumerate(SPLITS)}
    total = 0
    for source in datasets:
        print(f"处理 {source}…", flush=True)
        for split, native_id, raw in source_records(args.raw_dir, source):
            if split not in SPLITS:
                raise ValueError(f"{source} {native_id} 的划分无效：{split}")
            try:
                conn.execute("INSERT INTO native_groups VALUES(?,?,?)", (source, split, native_id))
                groups[source][split] += 1
                converted = 0
                for sequence, candidate in enumerate(adapt(source, raw, args.context_turns)):
                    original = candidate.intent
                    intent = original
                    single_turn = candidate.turn == 0 and len(candidate.context) == 1
                    if single_turn and precision_for(original).tier == NEEDS_REVIEW:
                        intent = ground_single_turn_review(original, candidate.utterance)
                    row, tier = make_row(
                        candidate, source, split, native_id, sequence, args.with_reference, intent=intent,
                    )
                    if intent is not original:
                        row.setdefault("meta", {})["single_turn_review"] = True
                    fingerprint = stable_hash(canonical_json([
                        compact(candidate.utterance).casefold(), canonical_intent_code(original), original["parameters"],
                    ]))
                    conn.execute("INSERT INTO candidates VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (
                        row["id"], source, split, split_priority[split], tier, total, fingerprint,
                        stable_hash(f"{args.seed}:{row['id']}"),
                        canonical_intent_code(intent), row["intent"],
                        int(row.get("meta", {}).get("review", False)), canonical_json(row),
                    ))
                    if single_turn:
                        conn.execute("INSERT INTO single_turn_candidates VALUES(?)", (row["id"],))
                    total += 1
                    converted += 1
                if not converted:
                    no_intents[source][split] += 1
            except (KeyError, TypeError, ValueError, sqlite3.IntegrityError) as exc:
                raise ValueError(f"{source} {split} {native_id} 处理失败：{exc}") from exc
        required_splits = ("train",) if source in TRAIN_ONLY_SOURCES else SPLITS
        if not all(groups[source].get(split) for split in required_splits):
            raise ValueError(f"{source} 缺少必需的划分：{', '.join(required_splits)}")
        conn.commit()
    if not total:
        raise ValueError("没有产生任何意图样本")
    return groups, no_intents


def deduplicate(conn):
    # Prefer a held-out record if the same sentence and resolved intent recur.
    conn.executescript("""
        CREATE INDEX candidate_digests ON candidates(digest, priority DESC, rank);
        CREATE TABLE eligible AS
            SELECT id, dataset, split, tier, rank, review
            FROM (
                SELECT id, dataset, split, tier, rank, review,
                    ROW_NUMBER() OVER (
                        PARTITION BY digest ORDER BY priority DESC, rank, id
                    ) AS position
                FROM candidates
            )
            WHERE position = 1;
        CREATE INDEX eligible_sampling ON eligible(split, tier, dataset, rank, id);
        CREATE TABLE selected(id TEXT PRIMARY KEY);
    """)


def quotas(capacities, limit, mode, keys=CLASSES):
    if limit is None or limit >= sum(capacities.values()):
        return capacities.copy()
    result = dict.fromkeys(keys, 0)
    initial = [tier for tier in keys if capacities[tier]]
    remaining = limit
    for tier in initial:
        if not remaining:
            break
        result[tier] += 1
        remaining -= 1
    while remaining:
        left = {tier: capacities[tier] - result[tier] for tier in keys}
        available = [tier for tier in keys if left[tier]]
        weights = {tier: left[tier] if mode == "natural" else 1 for tier in available}
        weight_sum = sum(weights.values())
        shares = {tier: remaining * weights[tier] / weight_sum for tier in available}
        step = {tier: min(left[tier], math.floor(shares[tier])) for tier in available}
        if not any(step.values()):
            step[max(available, key=lambda tier: shares[tier])] = 1
        for tier, count in step.items():
            result[tier] += count
            remaining -= count
    return result


def sample(conn, args):
    classes = CLASSES if args.include_not_applicable else PRECISION_CLASSES
    placeholders = ",".join("?" for _ in classes)
    conn.execute(f"""
        INSERT INTO selected SELECT id FROM eligible
        WHERE split != 'train' AND tier IN ({placeholders})
    """, classes)
    tiers_by_source = defaultdict(Counter)
    for tier, dataset, count in conn.execute(f"""
        SELECT tier, dataset, COUNT(*) FROM eligible
        WHERE split='train' AND tier IN ({placeholders}) GROUP BY tier, dataset
    """, classes):
        tiers_by_source[dataset][tier] = count
    sources_by_tier = defaultdict(Counter)
    for dataset, tiers in tiers_by_source.items():
        for tier, count in quotas(tiers, args.max_train_per_source, args.train_sampling, classes).items():
            if count:
                sources_by_tier[tier][dataset] = count
    counts = Counter({tier: sum(sources.values()) for tier, sources in sources_by_tier.items()})
    if args.max_train_per_class:
        counts = Counter({tier: min(n, args.max_train_per_class) for tier, n in counts.items()})
    amounts = quotas(counts, args.max_train, args.train_sampling, classes)
    for tier, amount in amounts.items():
        sources = sources_by_tier[tier]
        # Give available sources at least one example if the class budget permits it.
        source_order = sorted(sources, key=lambda source: (sources[source], source))
        for dataset, count in quotas(sources, amount, "natural", source_order).items():
            conn.execute("""
                INSERT INTO selected
                SELECT id FROM eligible WHERE split='train' AND tier=? AND dataset=?
                ORDER BY rank,id LIMIT ?
            """, (tier, dataset, count))
    conn.commit()


def distribution(conn, table, tier_filter=None):
    data = {}
    for source, split, tier, count, review in conn.execute(f"""
        SELECT dataset, split, tier, COUNT(*), SUM(review)
        FROM {table} WHERE (? IS NULL OR tier=?) GROUP BY dataset, split, tier
    """, (tier_filter, tier_filter)):
        block = data.setdefault(source, {}).setdefault(split, {
            "total": 0, "review_required": 0, "classes": dict.fromkeys(REPORTED_TIERS, 0),
        })
        block["total"] += count
        block["classes"][tier] = count
        block["review_required"] += review
    return data


def sum_splits(distributions):
    result = {}
    for split in SPLITS:
        combined = Counter(dict.fromkeys(REPORTED_TIERS, 0))
        for per_source in distributions.values():
            combined.update(per_source.get(split, {}).get("classes", {}))
        result[split] = {"total": sum(combined.values()), "classes": dict(combined)}
    return result


def intent_distribution(conn):
    by_split = {split: {} for split in SPLITS}
    for split, code, label, tier, count in conn.execute("""
        SELECT split, intent_id, intent_label, tier, COUNT(*)
        FROM output_rows GROUP BY split, intent_id, intent_label, tier
    """):
        entry = by_split[split].setdefault(code, {
            "label": label, "total": 0, "classes": dict.fromkeys(CLASSES, 0),
        })
        entry["total"] += count
        entry["classes"][tier] += count
    return by_split


def write_device_find_contrasts(data_dir, with_reference):
    relative = Path("augmentation/device-find-contrast.jsonl")
    output = data_dir / relative
    output.parent.mkdir()
    counts = Counter()
    with output.open("w", encoding="utf-8") as stream:
        for kind, name in (("phone", "手机"), ("watch", "手表"), ("tablet", "平板")):
            for sequence, (operation, text) in enumerate((
                ("query_target_location", f"帮我查一下我的{name}在哪里"),
                ("ring", f"让我的{name}响铃"),
                ("navigate_to_target", f"从我的当前位置导航到我的{name}所在的位置"),
            )):
                intent = {
                    "intent_id": "device.find", "label": "查找设备",
                    "parameters": {"target_device_type": kind, "operation": operation},
                }
                candidate = Candidate(intent, text, (("user", text),), 0, "device.find")
                row, tier = make_row(candidate, "synthetic", "train", kind, sequence, with_reference)
                stream.write(canonical_json(row) + "\n")
                counts[LABEL_NAMES[tier]] += 1
    return {"path": relative.as_posix(), "total": sum(counts.values()), "classes": dict(counts)}


def write_self_location_contrasts(data_dir, with_reference):
    relative = Path("augmentation/self-location-contrast.jsonl")
    counts = Counter()
    with (data_dir / relative).open("w", encoding="utf-8") as stream:
        for sequence, (level, text) in enumerate((
            ("precise", "告诉我现在的精确坐标"),
            ("district", "我现在在哪个行政区"),
            ("city", "我现在在哪座城市"),
            ("country", "我现在在哪个国家"),
        )):
            intent = make_intent("location.self", [("requested_granularity", level)])
            candidate = Candidate(intent, text, (("user", text),), 0, "location.self")
            row, tier = make_row(candidate, "synthetic", "train", "self-location", sequence, with_reference)
            stream.write(canonical_json(row) + "\n")
            counts[LABEL_NAMES[tier]] += 1
    return {"path": relative.as_posix(), "total": sum(counts.values()), "classes": dict(counts)}


def model_record(row):
    return {key: row[key] for key in ("intent", "slots", "label")}


def validate_model_inputs(conn):
    labels = {}
    reviewed = Counter()
    for split, encoded in conn.execute("""
        SELECT e.split, c.row_json FROM eligible e JOIN candidates c ON e.id=c.id
        WHERE e.tier != ?
    """, (NEEDS_REVIEW,)):
        row = json.loads(encoded)
        if row["intent"] in INTENT_CODES_BY_NAME:
            tier = reviewed_label(row["intent"], row["slots"])
            if LABEL_NAMES[tier] != row["label"]:
                raise ValueError(f"中文意图和位置槽位无法还原样本标签：{row['id']}")
        key = (row["intent"], canonical_json(row["slots"]))
        previous = labels.setdefault(key, row["label"])
        if row["label"] != previous:
            raise ValueError(f"同一模型输入的标签冲突：{key} / {previous} / {row['label']}")
        if row.get("meta", {}).get("single_turn_review"):
            reviewed[split, row["label"]] += 1
    return {
        "conflicting_inputs": 0, "distinct_finalized_inputs": len(labels),
        "single_turn_reviews": {
            split: {label: count for (part, label), count in reviewed.items() if part == split}
            for split in SPLITS
        },
    }


def write_output(conn, data_dir, args, inputs, groups, no_intents):
    model_checks = validate_model_inputs(conn)
    model_dir = data_dir / "model"
    model_dir.mkdir()
    conn.execute("""
        CREATE TEMP VIEW output_rows AS
        SELECT c.* FROM candidates c JOIN selected s ON c.id = s.id
    """)
    sidecars = {}
    for name, tier in ((None, None), ("not_applicable", NOT_APPLICABLE), ("needs_review", NEEDS_REVIEW)):
        directory = data_dir / name if name else data_dir
        if name:
            directory.mkdir()
            per_source = distribution(conn, "eligible", tier)
            sidecars[name] = {"by_source": per_source, "by_split": sum_splits(per_source)}
        for split in SPLITS:
            with (directory / f"{split}.jsonl").open("w", encoding="utf-8") as out:
                if name:
                    rows = conn.execute("""
                        SELECT c.row_json FROM candidates c JOIN eligible e ON c.id=e.id
                        WHERE e.split=? AND e.tier=? ORDER BY e.rank,e.id
                    """, (split, tier))
                else:
                    rows = conn.execute("""
                        SELECT row_json FROM output_rows WHERE split=? ORDER BY rank,id
                    """, (split,))
                for (encoded,) in rows:
                    out.write(encoded + "\n")
    model_splits = {}
    for split in SPLITS:
        classes = Counter(dict.fromkeys(LABEL_NAMES.values(), 0))
        with (model_dir / f"{split}.jsonl").open("w", encoding="utf-8") as out:
            for (encoded,) in conn.execute("""
                SELECT o.row_json FROM output_rows o
                JOIN single_turn_candidates s ON o.id=s.id
                WHERE o.split=? ORDER BY o.rank,o.id
            """, (split,)):
                record = model_record(json.loads(encoded))
                classes[record["label"]] += 1
                out.write(canonical_json(record) + "\n")
        model_splits[split] = {"total": sum(classes.values()), "classes": dict(classes)}
    stages = {}
    for stage, table in (("extracted", "candidates"), ("deduplicated", "eligible"), ("exported", "output_rows")):
        per_source = distribution(conn, table)
        stages[stage] = {"by_source": per_source, "by_split": sum_splits(per_source)}
    final = stages["exported"]["by_split"]
    classes = CLASSES if args.include_not_applicable else PRECISION_CLASSES
    warnings = [
        f"{split} 的 {tier} 只有 {count} 条弱标注样本"
        for split, info in final.items()
        for tier, count in info["classes"].items() if tier in classes and count < 20
    ]
    conflict = [
        {"intent_label": label, "precision_classes": nclasses}
        for label, nclasses in conn.execute("""
            SELECT intent_label, COUNT(DISTINCT tier) AS count_classes
            FROM output_rows GROUP BY intent_label HAVING count_classes > 1
            ORDER BY count_classes DESC, intent_label
        """)
    ]
    report = {
        "schema": SCHEMA_VERSION,
        "label_policy": POLICY_VERSION,
        "label_names": LABEL_NAMES,
        "download_inputs": inputs,
        "official_groups": groups,
        "groups_without_emitted_intents": no_intents,
        "settings": {
            "max_train": args.max_train, "max_train_per_class": args.max_train_per_class,
            "max_train_per_source": args.max_train_per_source,
            "train_sampling": args.train_sampling, "seed": args.seed,
            "include_reference": args.with_reference, "context_turns": args.context_turns,
            "include_not_applicable": args.include_not_applicable,
        },
        "stages": stages,
        "model_input_checks": model_checks,
        "model_input_splits": model_splits,
        "sidecars": sidecars,
        "augmentation": write_device_find_contrasts(data_dir, args.with_reference),
        "self_location_contrasts": write_self_location_contrasts(data_dir, args.with_reference),
        "exported_intent_distribution": intent_distribution(conn),
        "intent_labels_with_multiple_precision_classes": conflict,
        "warnings": warnings,
    }
    (data_dir / "summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {
        split: {
            **final[split],
            "deduplicated_total": stages["deduplicated"]["by_split"][split]["total"],
            "not_applicable_saved": sidecars["not_applicable"]["by_split"][split]["total"],
            "needs_review_saved": sidecars["needs_review"]["by_split"][split]["total"],
        }
        for split in SPLITS
    }


def prepare(args):
    sources = list(dict.fromkeys(args.datasets))
    if args.out_dir.exists():
        raise ValueError(f"输出目录已存在，请指定新路径：{args.out_dir}")
    inputs = {}
    for source in sources:
        print(f"检查原始数据 {source}…", flush=True)
        inputs[source] = ensure_source(
            args.raw_dir, source, args.offline, args.timeout, args.retries
        )
    args.out_dir.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".location-intent-", dir=args.out_dir.parent) as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "result"
        data_dir.mkdir()
        conn = sqlite3.connect(tmp / "staging.sqlite")
        try:
            init_database(conn)
            groups, no_intents = ingest(conn, sources, args)
            deduplicate(conn)
            sample(conn, args)
            final = write_output(conn, data_dir, args, inputs, groups, no_intents)
        finally:
            conn.close()
        data_dir.rename(args.out_dir)
    return final


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=Path("raw"), help="下载缓存目录")
    parser.add_argument("--out-dir", type=Path, required=True, help="输出到新目录")
    parser.add_argument("--datasets", nargs="+", choices=NAMES, default=list(NAMES))
    parser.add_argument("--offline", action="store_true", help="使用本地缓存，关闭下载")
    parser.add_argument("--timeout", type=positive_int, default=60, help="网络连接和读取超时（秒）")
    parser.add_argument("--retries", type=nonnegative_int, default=2)
    reference_options = parser.add_mutually_exclusive_group()
    reference_options.add_argument(
        "--with-reference", action="store_true", default=True,
        help="保留原句和最近对话作为核对资料（默认）",
    )
    reference_options.add_argument(
        "--no-reference", dest="with_reference", action="store_false",
        help="导出省略参考文本的副本",
    )
    parser.add_argument(
        "--include-not-applicable", action="store_true",
        help="将「不涉及」纳入主划分，供五分类实验",
    )
    parser.add_argument("--context-turns", type=positive_int, default=6)
    parser.add_argument("--max-train", type=positive_int, help="训练集总上限")
    parser.add_argument("--max-train-per-class", type=positive_int, help="训练集每个精度类的上限")
    parser.add_argument("--max-train-per-source", type=positive_int, help="主训练集每个语料来源的条数上限")
    parser.add_argument("--train-sampling", choices=("natural", "balanced"), default="natural")
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    if args.train_sampling == "balanced" and args.max_train is None and args.max_train_per_source is None:
        parser.error("--train-sampling balanced 需要给出 --max-train 或 --max-train-per-source")
    try:
        final = prepare(args)
    except (OSError, ValueError, BadZipFile, TarError) as exc:
        parser.exit(2, f"处理失败：{exc}\n")
    print(json.dumps(final, indent=2, ensure_ascii=False))
    print(f"输出目录：{args.out_dir}")


if __name__ == "__main__":
    main()
