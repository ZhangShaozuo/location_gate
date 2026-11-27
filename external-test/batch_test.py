#!/usr/bin/env python3
"""Run new cases against an existing location precision model and save row-level decisions."""

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent


def score(rows, labels, exact):
    matrix = {label: Counter() for label in labels}
    for row in rows:
        matrix[row["label"]][row["decision"]] += 1
    correct = sum(row["label"] == row["decision"] for row in rows)
    coarse = [row for row in rows if row["label"] != exact]
    return {
        "rows": len(rows), "correct": correct, "accuracy": round(correct / len(rows), 4) if rows else None,
        "coarse_overprecision": {"errors": sum(row["decision"] == exact for row in coarse), "total": len(coarse)},
        "confusion_by_label": {label: dict(counts) for label, counts in matrix.items()},
    }


def evaluate(args):
    script_dir = args.repo.resolve() / "precision"
    if not (script_dir / "location_schema.py").is_file():
        raise ValueError(f"未找到定位精度代码，请检查 --repo：{script_dir}")
    sys.path.insert(0, str(script_dir))
    import joblib
    from dataset import dump, read, write
    from run import predictions, training_digest
    from location_schema import EXACT, LABELS, NA, combination, normalize, rule_label, semantic_key

    if args.out.exists():
        raise ValueError("输出目录已存在，请指定新目录")
    with (args.run / "training.json").open(encoding="utf-8") as stream:
        training = json.load(stream)
    if training.get("source_splits") != ["train", "dev", "test"]:
        raise ValueError("请指定使用 --all 训练的全量模型")
    if training.get("training_sha256") != training_digest(args.data):
        raise ValueError("指定的 --data 与该模型的训练数据不匹配")
    trained = [row for split in training["source_splits"] for row in read(args.data / f"{split}.jsonl")]
    trained_inputs = {combination(row) for row in trained}
    trained_groups = {semantic_key(normalize(row)) for row in trained}
    if (len(trained), len(trained_groups)) != (training["training_rows"], training["semantic_groups"]):
        raise ValueError("训练记录中的样本数与 --data 不一致")

    cases = read(args.cases)
    if not cases:
        raise ValueError("测试文件为空")
    normalized, ids, used_groups = [], set(), set()
    expected_labels = {"new": LABELS, "phrase": LABELS, "control": (NA,)}
    for case in cases:
        try:
            row = normalize(case)
        except (KeyError, ValueError) as error:
            raise ValueError(f"{case.get('id', '缺少编号')} 无法归一化：{error}") from error
        key = semantic_key(row)
        if case["id"] in ids or key in used_groups:
            raise ValueError(f"测试样本重复：{case['id']}")
        if case["label"] not in expected_labels.get(case["suite"], ()):
            raise ValueError(f"测试类型或标签无效：{case['id']}")
        if combination(case) in trained_inputs or (key in trained_groups) != (case["suite"] == "phrase"):
            raise ValueError(f"样本新颖性与其测试类型不符：{case['id']}")
        ids.add(case["id"])
        used_groups.add(key)
        normalized.append(row)

    model = joblib.load(args.run / "model.joblib")
    results = []
    for case, row, model_prediction in zip(cases, normalized, predictions(model, normalized), strict=True):
        rule = rule_label(row)
        # Match the prediction CLI: keep the rule's non-class outcomes.
        decision = rule if rule in {NA, "待复核", "超出范围"} else model_prediction
        results.append({
            **case, "normalized": row, "seen_semantic_group": case["suite"] == "phrase",
            "rule_reference": rule, "model_prediction": model_prediction,
            "decision": decision, "correct": decision == case["label"],
        })

    groups = {suite: [r for r in results if r["suite"] == suite] for suite in expected_labels}
    controls = groups["control"]
    summary = {
        "training_rows": len(trained), "training_semantic_groups": len(trained_groups),
        "test_rows": len(results),
        "new_semantics": score(groups["new"], LABELS, EXACT),
        "new_phrasings_of_known_semantics": score(groups["phrase"], LABELS, EXACT),
        "not_applicable_controls": {
            "rows": len(controls), "rule_kept_not_applicable": sum(r["decision"] == NA for r in controls),
            "model_alone_predicted_exact": sum(r["model_prediction"] == EXACT for r in controls),
        },
        "reference_disagreements": sum(r["rule_reference"] != r["label"] for r in results),
        "errors": sum(not r["correct"] for r in results),
    }
    args.out.mkdir(parents=True)
    dump(args.out / "summary.json", summary)
    write(args.out / "predictions.jsonl", results)
    write(args.out / "errors.jsonl", [r for r in results if not r["correct"]])
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--data", type=Path, default=Path("normalized-coverage/data"))
    parser.add_argument("--run", type=Path, default=Path("runs/normalized-full"))
    parser.add_argument("--cases", type=Path, default=HERE / "external_test.jsonl")
    parser.add_argument("--out", type=Path, default=Path("external-test-results"))
    args = parser.parse_args()
    try:
        summary = evaluate(args)
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
