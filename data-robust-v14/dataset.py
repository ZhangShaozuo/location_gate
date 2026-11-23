"""Build grouped train/dev/test splits and controlled paraphrases from the v13 seeds."""

from collections import Counter, defaultdict
import json
from pathlib import Path
import random

from schema_v14 import (
    KEYS, LABELS, NA, VALUES, combination, intent_aliases,
    normalize, rule_label, semantic_key,
)

ROOT = Path(__file__).resolve().parent
SPLITS = ("train", "dev", "test")
SEED = 2026
STYLES = {
    "train": ("canonical", "intent_a", "keys_a", "values_a", "ui_a", "intent_b", "mixed_a", "meters_a"),
    "dev": ("canonical", "intent_b", "keys_b", "values_b", "mixed_b", "kilometers_b"),
    "test": ("canonical", "intent_c", "keys_b", "values_b", "mixed_c", "kilometers_c", "format_c"),
    "controls": ("canonical", "intent_c", "mixed_c", "kilometers_c"),
}
DISPLAY = {
    "canonical": "标准输入", "intent_a": "意图别名 A", "intent_b": "意图别名 B", "intent_c": "意图别名 C",
    "keys_a": "中文字段名 A", "keys_b": "中文字段名 B", "values_a": "同义槽位值 A",
    "values_b": "同义槽位值 B", "ui_a": "中文字段和值 A", "mixed_a": "组合改写 A", "mixed_b": "组合改写 B",
    "mixed_c": "组合改写 C", "meters_a": "米制半径改写", "kilometers_b": "公里半径改写",
    "kilometers_c": "小数公里改写", "format_c": "空白和标点变化",
}


def read(path):
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write(path, rows):
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def case_id(row):
    return row["scenario"]


def partition(groups):
    rng = random.Random(SEED)
    results = {split: [] for split in SPLITS}
    by_label = defaultdict(list)
    intent_left = Counter(rows[0]["intent"] for rows in groups.values())
    for name, rows in groups.items():
        labels = {row["label"] for row in rows}
        if len(labels) != 1:
            raise ValueError(f"一个语义场景组出现多种标签：{name}")
        by_label[labels.pop()].append(name)
    for label in LABELS:
        candidates = sorted(by_label[label])
        rng.shuffle(candidates)
        size = len(candidates)
        for split, share in (("test", 0.2), ("dev", 0.15)):
            for name in candidates.copy():
                if len([g for g in results[split] if groups[g][0]["label"] == label]) >= round(size * share):
                    break
                intent = groups[name][0]["intent"]
                if intent_left[intent] > 1:
                    intent_left[intent] -= 1
                    candidates.remove(name)
                    results[split].append(name)
        results["train"].extend(candidates)
    return results


def variant(row, style):
    if style == "canonical":
        return row["intent"], row["slots"]
    intent = row["intent"]
    aliases = intent_aliases()[intent]
    alias_no = {"intent_a": 0, "intent_b": 1, "intent_c": 2, "mixed_a": 0, "mixed_b": 1,
                "mixed_c": 2, "kilometers_c": 2}.get(style)
    if alias_no is not None:
        intent = aliases[alias_no]
    if style == "format_c":
        intent = f"  {aliases[2]}！ "
    key_no = {"keys_a": 0, "ui_a": 0, "mixed_a": 1, "keys_b": 1, "mixed_b": 0,
              "mixed_c": 1, "meters_a": 0, "kilometers_b": 0, "kilometers_c": 1}.get(style)
    value_no = {"values_a": 0, "ui_a": 0, "mixed_a": 0, "values_b": 1, "mixed_b": 1,
                "mixed_c": 1, "kilometers_c": 0}.get(style)
    slots = {}
    for field, value in row["slots"].items():
        key = field if key_no is None else KEYS[field][key_no]
        if field == "radius_band" and style in {"meters_a", "kilometers_b", "kilometers_c"}:
            # Valid in-band values, distinct by split where expressed as meters or kilometers.
            near = value == "up_to_policy_limit"
            radius = {"meters_a": ("300 m", "1200 m"),
                      "kilometers_b": ("0.4km", "1.4km"),
                      "kilometers_c": ("0.35 公里", "1.55 公里")}[style][not near]
            slots[KEYS["radius_m"][key_no]] = radius
        else:
            aliases = VALUES.get(field, {}).get(value)
            slots[key] = aliases[value_no] if aliases and value_no is not None else value
    return intent, slots


def augment(groups, names, split):
    output = []
    inputs = set()
    for name in names:
        for row in groups[name]:
            for style in STYLES[split]:
                if style.startswith(("meters_", "kilometers_")) and "radius_band" not in row["slots"]:
                    continue
                intent, slots = variant(row, style)
                sample = {"intent": intent, "slots": slots, "label": row["label"], "scenario": name, "variant": style}
                if normalize(sample) != {"intent": row["intent"], "slots": row["slots"]}:
                    raise ValueError(f"改写改变了槽位语义：{sample}")
                signature = combination(sample)
                if signature not in inputs:
                    inputs.add(signature)
                    output.append(sample)
    return output


def build(out):
    if out.exists():
        raise ValueError("请为生成数据指定一个新目录")
    groups = defaultdict(list)
    inputs = set()
    for file, expected in (("seed_train.jsonl", LABELS), ("seed_controls.jsonl", (NA,))):
        rows = read(ROOT / file)
        for source in rows:
            row = {**normalize(source), "label": source["label"]}
            signature = combination(row)
            if signature in inputs or row["label"] not in expected or rule_label(row) != row["label"]:
                raise ValueError(f"样本重复或规则无法按归一化槽位复算：{row}")
            inputs.add(signature)
            groups[semantic_key(row)].append(row)
        if file == "seed_train.jsonl":
            splits = partition(groups)
            groups_before_controls = set(groups)
    splits["controls"] = sorted(set(groups) - groups_before_controls)
    for split, names in splits.items():
        for other, others in splits.items():
            if split != other and set(names) & set(others):
                raise ValueError(f"语义场景跨集合：{split}, {other}")

    datasets = {split: augment(groups, names, split) for split, names in splits.items()}
    # Verify both exact raw keys and the normalized semantic keys have no cross-split overlap.
    input_sets = {split: {combination(r) for r in rows} for split, rows in datasets.items()}
    for i, split in enumerate(datasets):
        for other in tuple(datasets)[i + 1:]:
            if input_sets[split] & input_sets[other]:
                raise ValueError(f"原始输入跨集合：{split}, {other}")
    summary = {"seed": SEED, "labels": LABELS, "splits": {}}
    for split, rows in datasets.items():
        names = splits[split]
        summary["splits"][split] = {
            "rows": len(rows), "source_combinations": sum(len(groups[n]) for n in names),
            "semantic_groups": len(names), "labels": dict(Counter(r["label"] for r in rows)),
            "groups_by_label": dict(Counter(groups[n][0]["label"] for n in names)),
            "intents": len({groups[n][0]["intent"] for n in names}),
            "variant_counts": dict(Counter(r["variant"] for r in rows)),
        }
    out.mkdir(parents=True)
    for split, rows in datasets.items():
        write(out / f"{split}.jsonl", rows)
    dump(out / "dataset_summary.json", summary)
    return summary
