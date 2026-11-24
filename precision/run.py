#!/usr/bin/env python3
"""Prepare, train, evaluate, or query the three-class location precision model."""

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path

from dataset import DISPLAY, build, case_id, dump, read, write
from location_schema import EXACT, LABELS, NA, normalize, rule_label, semantic_key, semantic_slots


def features(row):
    return {"intent": row["intent"], **{f"slot:{k}": v for k, v in semantic_slots(row).items()}}


def checked(rows):
    for row in rows:
        normalized = normalize(row)
        if semantic_key(normalized) != case_id(row):
            raise ValueError(f"场景标识与归一化输入不符：{row}")
        yield normalized


def training_digest(data):
    return sha256((data / "train.jsonl").read_bytes()).hexdigest()


def train(data, output, all_data=False):
    import joblib
    import sklearn
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline

    if output.exists():
        raise ValueError("请为本次训练指定一个新目录")
    splits = ("train", "dev", "test") if all_data else ("train",)
    rows = [row for split in splits for row in read(data / f"{split}.jsonl")]
    labels_by_group = {case_id(row): row["label"] for row in rows}
    groups_by_label = Counter(labels_by_group.values())
    if set(groups_by_label) != set(LABELS) or any(row["label"] != labels_by_group[case_id(row)] for row in rows):
        raise ValueError("训练标签缺档或同一场景标签不一致")
    multiplicity = Counter(case_id(row) for row in rows)
    label_weights = {label: len(labels_by_group) / (len(LABELS) * count)
                     for label, count in groups_by_label.items()}
    weights = [label_weights[row["label"]] / multiplicity[case_id(row)] for row in rows]
    normalized = list(checked(rows))
    estimator = make_pipeline(DictVectorizer(), LogisticRegression(max_iter=1000))
    estimator.fit([features(row) for row in normalized], [row["label"] for row in rows],
                  logisticregression__sample_weight=weights)
    summary = {
        "model": "类别特征 + CPU 逻辑回归", "sklearn": sklearn.__version__,
        "training_rows": len(rows), "semantic_groups": len(labels_by_group),
        "groups_by_label": dict(groups_by_label), "class_weights": label_weights,
        "training_sha256": training_digest(data),
        "source_splits": splits,
    }
    output.mkdir(parents=True)
    joblib.dump(estimator, output / "model.joblib")
    dump(output / "training.json", summary)
    return summary


def predictions(model, normalized):
    return model.predict([features(row) for row in normalized]).tolist()


def measure(rows, actual_predictions):
    from sklearn.metrics import accuracy_score, confusion_matrix, f1_score

    actual = [row["label"] for row in rows]
    groups = defaultdict(list)
    variants = defaultdict(list)
    canonical = {}
    for row, prediction in zip(rows, actual_predictions, strict=True):
        group = case_id(row)
        groups[group].append((row["label"], prediction))
        variants[row["variant"]].append(prediction == row["label"])
        if row["variant"] == "canonical":
            canonical.setdefault(group, (row["label"], prediction))
    changed = sum(p != canonical[case_id(row)][1] for row, p in zip(rows, actual_predictions, strict=True))
    coarse = sum(label != EXACT for label in actual)
    over = sum(prediction == EXACT and label != EXACT for label, prediction in zip(actual, actual_predictions))
    actual_groups, predicted_groups = zip(*canonical.values())
    return {
        "rows": len(rows), "semantic_groups": len(groups),
        "row_accuracy": float(accuracy_score(actual, actual_predictions)),
        "variant_changed_vs_canonical": changed,
        "groups_all_variants_correct": sum(all(label == prediction for label, prediction in group) for group in groups.values()),
        "macro_f1_by_group": float(f1_score(actual_groups, predicted_groups, labels=LABELS, average="macro", zero_division=0)),
        "group_confusion": confusion_matrix(actual_groups, predicted_groups, labels=LABELS).tolist(),
        "coarse_overprecision_rows": {"errors": over, "total": coarse},
        "coarse_overprecision_groups": {
            "errors": sum(expected != EXACT and predicted == EXACT for expected, predicted in canonical.values()),
            "total": sum(expected != EXACT for expected, _ in canonical.values()),
        },
        "by_variant": {DISPLAY[name]: {"rows": len(results), "correct": sum(results)}
                       for name, results in variants.items()},
    }


def evaluate(data, run):
    import joblib

    model = joblib.load(run / "model.joblib")
    training_summary = json.loads((run / "training.json").read_text(encoding="utf-8"))
    if training_summary.get("source_splits") != ["train"]:
        raise ValueError("全量模型已训练过验证和测试样本，请使用按训练集拟合的模型执行测试")
    if training_summary["training_sha256"] != training_digest(data):
        raise ValueError("当前数据目录与此模型的训练数据不匹配")
    train_groups = {case_id(row) for row in read(data / "train.jsonl")}
    metrics = {"labels": LABELS, "evaluation": {}}
    errors = []
    for split in ("dev", "test"):
        rows = read(data / f"{split}.jsonl")
        if train_groups & {case_id(row) for row in rows}:
            raise ValueError(f"{split} 包含训练场景")
        inferred = predictions(model, list(checked(rows)))
        metrics["evaluation"][split] = measure(rows, inferred)
        errors.extend({"split": split, "predicted": guess, **row}
                      for row, guess in zip(rows, inferred, strict=True) if guess != row["label"])

    controls = read(data / "controls.jsonl")
    normalized = list(checked(controls))
    raw_guesses = predictions(model, normalized)
    policy_guesses = [rule_label(row) for row in normalized]
    metrics["controls"] = {
        "rows": len(controls), "semantic_groups": len({case_id(row) for row in controls}),
        "rule_not_applicable": policy_guesses.count(NA),
        "model_alone_predicted_exact": raw_guesses.count(EXACT),
    }
    dump(run / "metrics.json", metrics)
    write(run / "errors.jsonl", errors)
    return metrics


def infer(run, query):
    import joblib

    normalized = normalize(query)
    model = joblib.load(run / "model.joblib")
    result = {"normalized": normalized, "rule_reference": rule_label(normalized)}
    if result["rule_reference"] in {NA, "待复核", "超出范围"}:
        result["predicted_precision"] = None
    else:
        result["predicted_precision"] = predictions(model, [normalized])[0]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="生成按语义分组的训练、验证和测试数据")
    prepare.add_argument("--out", required=True, type=Path)
    for action in ("train", "test"):
        command = commands.add_parser(action)
        command.add_argument("--data", required=True, type=Path)
        command.add_argument("--run", required=True, type=Path)
        if action == "train":
            command.add_argument("--all", action="store_true", help="合并三分类划分后拟合全量模型")
    predict = commands.add_parser("predict", help="输入一个包含 intent 和 slots 的 JSON")
    predict.add_argument("--run", required=True, type=Path)
    predict.add_argument("--input", required=True)
    dashboard = commands.add_parser("dashboard", help="生成本地可打开的 HTML 看板")
    dashboard.add_argument("--data", required=True, type=Path)
    dashboard.add_argument("--run", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            result = build(args.out)
        elif args.command == "train":
            result = train(args.data, args.run, all_data=args.all)
        elif args.command == "test":
            result = evaluate(args.data, args.run)
        elif args.command == "predict":
            result = infer(args.run, json.loads(args.input))
        else:
            from dashboard import render
            result = {"dashboard": str(render(args.data, args.run))}
    except (OSError, KeyError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
