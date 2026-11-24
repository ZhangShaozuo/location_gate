#!/usr/bin/env python3
"""Extend the location classifier's explicitly enumerated normalized combinations."""

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import sys

from matrix import ACTIONS, NA, cases

ROOT = Path(__file__).resolve().parent
SPLITS = ("train", "dev", "test", "controls")


def table(out, name, rows):
    with (out / name).open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def build(args):
    if args.out.exists():
        raise ValueError(f"输出目录已存在：{args.out}")
    sys.path.insert(0, str(args.repo.resolve() / "precision"))
    from dataset import dump, read, write
    from location_schema import INTENT_CODES_BY_NAME, LABELS, normalize, rule_label, semantic_key

    code_to_intent = {code: name for name, code in INTENT_CODES_BY_NAME.items()}
    domains = json.loads((ROOT / "domains.json").read_text(encoding="utf-8"))
    by_code = {code: domain for domain, codes in domains.items() for code in codes}
    groups = {}
    data = {s: {} for s in SPLITS}
    for split in SPLITS:
        for row in read(args.base / f"{split}.jsonl"):
            key = semantic_key(normalize(row))
            canonical_intent, canonical_slots = json.loads(key)
            item = {"intent": canonical_intent, "slots": canonical_slots, "label": row["label"],
                    "scenario": key, "variant": "canonical"}
            if key != row["scenario"]:
                raise ValueError(f"原数据语义键不一致：{key}")
            previous = groups.setdefault(key, (split, row["label"]))
            if previous != (split, row["label"]) or rule_label(item) != row["label"]:
                raise ValueError(f"原数据跨集合重复或标签冲突：{key}")
            data[split][key] = item
    before = {s: len(rows) for s, rows in data.items()}
    if not all(before.values()):
        raise ValueError("原数据存在空划分")

    reserved = {}
    for row in read(args.external):
        key = semantic_key(normalize(row))
        if row["suite"] == "phrase":
            if key not in groups or groups[key][1] != row["label"]:
                raise ValueError(f"原同义改写例缺少训练参考：{row['id']}")
        elif row["suite"] in ("new", "control"):
            previous = reserved.setdefault(key, row)
            if previous["label"] != row["label"]:
                raise ValueError(f"原外测标签冲突：{row['id']}")
            if key in groups and groups[key][0] != "controls":
                raise ValueError(f"原外测已进入三分类数据：{row['id']}")
        else:
            raise ValueError(f"未知外测类别：{row['suite']}")

    inventory = {}
    for code, slots, label, note, pending in cases():
        n = normalize({"intent": code_to_intent[code], "slots": slots})
        key = semantic_key(n)
        intent, slots = json.loads(key)
        rule = rule_label(n)
        if (not pending and rule != label) or (label not in (*LABELS, NA, "待复核")):
            raise ValueError(f"矩阵标签与当前规则不一致：{key}，预期 {label}，规则 {rule}")
        original = groups.get(key)
        if original and original[1] != label:
            raise ValueError(f"矩阵与现有标签冲突：{key}")
        if key in reserved and reserved[key]["label"] != label:
            raise ValueError(f"矩阵与既有外测标签冲突：{key}")
        if pending:
            status = "待确认"
        elif key in reserved:
            status = "保留在外部测试"
        elif original:
            status = {"train": "已有训练", "dev": "保留在验证", "test": "保留在内部测试",
                      "controls": "已有对照"}[original[0]]
        else:
            target = "controls" if label == NA else "train"
            status = "新增对照" if target == "controls" else "新增训练"
            data[target][key] = {"intent": intent, "slots": slots, "label": label,
                                 "scenario": key, "variant": "canonical"}
        record = {"领域": by_code[code], "标准意图": intent, "归一化槽位": json.dumps(slots, ensure_ascii=False),
                  "业务预期": label, "当前规则": rule, "状态": status, "场景": note}
        if key in inventory and inventory[key] != record:
            raise ValueError(f"矩阵重复定义：{key}")
        inventory[key] = record

    all_class = {key for s in ("train", "dev", "test") for key in data[s]}
    if all_class & reserved.keys():
        raise ValueError("外部留出集与三分类数据重叠")
    if len(all_class) != sum(len(data[s]) for s in ("train", "dev", "test")):
        raise ValueError("三分类集合重叠")

    matrix_counts = dict(Counter(r["状态"] for r in inventory.values()))
    status_by_split = {"train": "已有训练", "dev": "保留在验证", "test": "保留在内部测试", "controls": "已有对照"}
    for key in groups.keys() | reserved.keys():
        if key in inventory:
            continue
        intent, slots = json.loads(key)
        if key in reserved:
            label, status = reserved[key]["label"], "保留在外部测试"
        else:
            split, label = groups[key]
            status = status_by_split[split]
        inventory[key] = {"领域": by_code[INTENT_CODES_BY_NAME[intent]], "标准意图": intent,
                          "归一化槽位": json.dumps(slots, ensure_ascii=False), "业务预期": label,
                          "当前规则": rule_label({"intent": intent, "slots": slots}),
                          "状态": status, "场景": "原数据中的既有组合"}

    actions = []
    for domain, name, codes, note in ACTIONS:
        names = {code_to_intent[c] for c in codes}
        actions.append({"现网领域": domain, "动作": name,
                        "训练组合数": sum(row["intent"] in names for row in data["train"].values()),
                        "内部留出组合数": sum(row["intent"] in names for s in ("dev", "test") for row in data[s].values()),
                        "对照组合数": sum(row["intent"] in names for row in data["controls"].values()),
                        "说明": note or ""})
    summary = {"scope": "normalized_semantic_keys", "previous_groups_by_split": before,
               "classes": LABELS, "reserved_external_new": sum(r["suite"] == "new" for r in reserved.values()),
               "reserved_external_controls": sum(r["suite"] == "control" for r in reserved.values()),
               "new_groups_by_label": dict(Counter(r["业务预期"] for r in inventory.values() if r["状态"] == "新增训练")),
               "enumeration_status": matrix_counts,
               "matrix_rows": len(inventory),
               "matrix_status": dict(Counter(r["状态"] for r in inventory.values())), "splits": {}}
    args.out.mkdir(parents=True)
    for split, rows in data.items():
        write(args.out / f"{split}.jsonl", rows.values())
        summary["splits"][split] = {"rows": len(rows), "semantic_groups": len(rows),
                                     "labels": dict(Counter(r["label"] for r in rows.values())),
                                     "variant_counts": {"canonical": len(rows)}}
    dump(args.out / "dataset_summary.json", summary)
    table(args.out, "coverage_matrix.tsv", sorted(inventory.values(), key=lambda r: (
        r["领域"], r["标准意图"], r["归一化槽位"])))
    table(args.out, "live_actions.tsv", actions)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--external", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    try:
        summary = build(parser.parse_args())
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
