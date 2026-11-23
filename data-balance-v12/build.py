#!/usr/bin/env python3
"""Build deduplicated three-class location-precision data and synthetic holdouts."""

import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
LABELS = ("精确", "区域级模糊", "城市级模糊")
DISPLAY = {"区域级": "区域级模糊", "城市级": "城市级模糊"}
NA = "不涉及"
REVIEW = "待复核"
GROUPS = ("train", "dev", "test", "control", "review")
REFERENCE_FIELDS = {
    "src": ("loc", "near"), "from_src": ("from",),
    "to_src": ("to",), "pickup_src": ("pickup",),
}
BEHAVIOR_FIELDS = ("level", "scope", "op", "track", "trigger", "anchor")


def read_jsonl(path):
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write_jsonl(path, rows):
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def canonical(row, ref_kind, radius_boundary):
    """Keep evidence types and constraints without memorizing names or destinations."""
    slots = row["slots"]
    evidence = {field: slots[field] for field in BEHAVIOR_FIELDS if field in slots}
    for source, raw_fields in REFERENCE_FIELDS.items():
        value = next((slots[field] for field in raw_fields if slots.get(field)), None)
        kind = slots.get(source) or ref_kind(value)
        if source == "src" and kind == "unknown" and slots.get("candidates"):
            kind = "previous_entity"
        if kind != "unknown":
            evidence[source] = "named_place" if kind == "fixed" else kind
        elif value:
            evidence[source] = "unresolved_reference"
    if "radius_m" in slots:
        radius = slots["radius_m"]
        if not isinstance(radius, int) or isinstance(radius, bool) or radius < 1:
            raise ValueError(f"无效的半径：{radius!r}")
        evidence["radius_band"] = "up_to_policy_limit" if radius <= radius_boundary else "above_policy_limit"
    return {"intent": row["intent"], "slots": evidence}


def key(row):
    return row["intent"], json.dumps(row["slots"], ensure_ascii=False, sort_keys=True)


def read_cases(intents, normalize, get_policy):
    known = set(BEHAVIOR_FIELDS) | set(REFERENCE_FIELDS) | {"radius_m", "target", "places", "candidates"}
    known.update(field for fields in REFERENCE_FIELDS.values() for field in fields)
    groups = {split: [] for split in GROUPS}
    families, indexed = {}, {}
    with (ROOT / "cases.tsv").open(encoding="utf-8", newline="") as stream:
        for line_no, row in enumerate(csv.DictReader(stream, delimiter="\t"), start=2):
            split, family, code = (row[field] for field in ("split", "family", "code"))
            if split not in groups or code not in intents or not family:
                raise ValueError(f"cases.tsv 第 {line_no} 行的集合、场景族或意图代码无效")
            slots = json.loads(row["slots"])
            if not isinstance(slots, dict) or slots.keys() - known:
                raise ValueError(f"cases.tsv 第 {line_no} 行的槽位无效")
            label = row["label"]
            expected = {NA} if split == "control" else ({NA, REVIEW, *LABELS} if split == "review" else set(LABELS))
            if label not in expected or not row["text"] or not row["reason"]:
                raise ValueError(f"cases.tsv 第 {line_no} 行的标签、原话或依据无效")
            if split in ("train", "dev", "test") and families.setdefault(family, split) != split:
                raise ValueError(f"场景族跨训练或评估集合：{family}")
            draft = {
                "id": f"synthetic:v12:{line_no:03d}", "source": "synthetic", "split": split,
                "family": family, "intent": intents[code], "slots": slots, "label": label,
                "ref": {"text": row["text"], "reason": row["reason"]},
            }
            tier = get_policy(code, slots).tier
            draft["rule_label"] = DISPLAY.get(tier, tier)
            if split in {"train", "control"} and label != draft["rule_label"]:
                raise ValueError(f"cases.tsv 第 {line_no} 行与 v11 规则不一致：{label} <> {draft['rule_label']}")
            normalized = normalize(draft)
            if split in ("train", "dev", "test"):
                signature = key(normalized)
                if signature in indexed:
                    raise ValueError(f"重复的生成语义组合：{indexed[signature]}、第 {line_no} 行：{signature}")
                indexed[signature] = line_no
            groups[split].append({**draft, "semantic_slots": normalized["slots"]})
    return groups


def normalized_model(row, normalize):
    return {**normalize(row), "label": row["label"]}


def plan(base_dir, groups, normalize):
    original = {s: read_jsonl(base_dir / f"{s}.jsonl") for s in ("train", "dev", "test")}
    legacy_holdout = {key(normalize(row)) for split in ("dev", "test") for row in original[split]}
    candidate_holdout = {key(normalize(row)) for split in ("dev", "test") for row in groups[split]}
    embargo = candidate_holdout
    if any(row["label"] not in LABELS for rows in original.values() for row in rows):
        raise ValueError("原模型目录包含非三分类标签")
    indexed = defaultdict(Counter)
    raw_keys = set()
    for row in original["train"]:
        indexed[key(normalize(row))][row["label"]] += 1
        raw_keys.add(key(row))
    conflicted = {signature for signature, labels in indexed.items() if len(labels) > 1}
    output = {}
    for signature, labels in indexed.items():
        if signature not in embargo and signature not in conflicted:
            intent, slots = signature
            output[signature] = {"intent": intent, "slots": json.loads(slots), "label": next(iter(labels))}
    baseline = list(output.values())
    trace = []
    for row in groups["train"]:
        model = normalized_model(row, normalize)
        signature = key(model)
        if signature in embargo:
            status = "heldout"
        elif signature in conflicted or (signature in output and output[signature]["label"] != row["label"]):
            status = "conflict"
        elif signature in output:
            status = "existing"
        else:
            status = "added"
            output[signature] = model
        trace.append({"id": row["id"], "intent": row["intent"], "label": row["label"], "status": status})
    data = {
        "train_base_dedup": baseline,
        "train": list(output.values()),
        **{split: [normalized_model(row, normalize) for row in groups[split]] for split in ("dev", "test")},
    }
    for left, right in (("train", "dev"), ("train", "test"), ("dev", "test")):
        overlap = {key(row) for row in data[left]} & {key(row) for row in data[right]}
        if overlap:
            raise ValueError(f"{left} 与 {right} 有训练语义泄漏：{overlap}")
    match = set(indexed) & candidate_holdout
    stats = {
        "base_train_rows": len(original["train"]),
        "base_raw_combinations": len(raw_keys),
        "base_semantic_combinations": len(indexed),
        "base_conflicted_combinations": len(conflicted),
        "base_heldout_combinations": len(set(indexed) & embargo),
        "candidate_holdout_seen_in_original_train": len(match),
        "legacy_holdout_semantic_overlap_with_new_train": len(set(output) & legacy_holdout),
        "synthetic_train_outcomes": dict(Counter(row["status"] for row in trace)),
        "synthetic_added_labels": dict(Counter(row["label"] for row in trace if row["status"] == "added")),
    }
    conflicts = [{"intent": intent, "slots": json.loads(slots), "counts": indexed[intent, slots]}
                 for intent, slots in sorted(conflicted)]
    return data, stats, trace, conflicts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--base-model-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("--out 需要使用新目录")
    sys.path.insert(0, str(args.repo.resolve()))
    from corpora.policy import POLICY_VERSION, RADIUS_PRECISE_M
    from corpora.schema import INTENTS, policy_from_slots, ref_kind
    if POLICY_VERSION != "precision-weak-v11-whole-dialogue":
        parser.error(f"要求 v11 标注规则，当前为 {POLICY_VERSION}")
    def normalize(row):
        return canonical(row, ref_kind, RADIUS_PRECISE_M)

    groups = read_cases(INTENTS, normalize, policy_from_slots)
    data, summary, trace, conflicts = plan(args.base_model_dir, groups, normalize)
    summary["synthetic_rows"] = {
        group: dict(Counter(row["label"] for row in rows)) for group, rows in groups.items()
    }
    summary["synthetic_holdout_rule_disagreements"] = {
        split: sum(row["label"] != row["rule_label"] for row in groups[split]) for split in ("dev", "test")
    }
    summary["model"] = {group: dict(Counter(row["label"] for row in rows)) for group, rows in data.items()}
    if set(summary["model"]["train"]) != set(LABELS):
        raise ValueError("生成后训练集缺少精度类别")
    summary["class_weights"] = {
        label: len(data["train"]) / (len(LABELS) * summary["model"]["train"][label]) for label in LABELS
    }
    (args.out / "model").mkdir(parents=True)
    (args.out / "audit").mkdir()
    for split, rows in data.items():
        write_jsonl(args.out / "model" / f"{split}.jsonl", rows)
    for group, rows in groups.items():
        write_jsonl(args.out / "audit" / f"{group}.jsonl", rows)
    write_jsonl(args.out / "audit" / "train_outcomes.jsonl", trace)
    write_jsonl(args.out / "audit" / "base_conflicts.jsonl", conflicts)
    (args.out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
