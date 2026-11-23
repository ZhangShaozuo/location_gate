#!/usr/bin/env python3
"""Compare CPU classifiers on the same held-out synthetic scenarios."""

import argparse
from collections import Counter
import json
from pathlib import Path

from build import LABELS, read_jsonl


def features(row, with_slots):
    model_input = {"intent": row["intent"]}
    if with_slots:
        model_input.update({f"slot:{name}": value for name, value in row["slots"].items()})
    return model_input


def metrics(actual, predicted):
    from sklearn.metrics import accuracy_score, confusion_matrix, f1_score

    forbidden = [prediction for label, prediction in zip(actual, predicted) if label != LABELS[0]]
    blocked = [prediction for label, prediction in zip(actual, predicted) if label == LABELS[0]]
    return {
        "samples": len(actual),
        "accuracy": round(float(accuracy_score(actual, predicted)), 4),
        "macro_f1": round(float(f1_score(actual, predicted, labels=LABELS, average="macro", zero_division=0)), 4),
        "precision_overgrant": {"count": forbidden.count(LABELS[0]), "total": len(forbidden)},
        "precise_downgrade": {"count": len(blocked) - blocked.count(LABELS[0]), "total": len(blocked)},
        "confusion_matrix": confusion_matrix(actual, predicted, labels=LABELS).tolist(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, type=Path, help="build.py 写出的数据目录")
    args = parser.parse_args()
    try:
        from sklearn.feature_extraction import DictVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
    except ImportError:
        parser.error("运行前请在训练环境安装 scikit-learn")

    model_dir = args.data_dir / "model"
    datasets = {split: read_jsonl(model_dir / f"{split}.jsonl")
                for split in ("train_base_dedup", "train", "dev", "test")}
    results = {"label_order": LABELS}
    for split in ("train_base_dedup", "train"):
        train = datasets[split]
        actual_train = [row["label"] for row in train]
        for use_slots in (False, True):
            name = f"{split}/{'intent+slots' if use_slots else 'intent-only'}"
            estimator = make_pipeline(
                DictVectorizer(),
                LogisticRegression(class_weight="balanced", max_iter=1000),
            )
            estimator.fit([features(row, use_slots) for row in train], actual_train)
            results[name] = {}
            for evaluation in ("dev", "test"):
                rows = datasets[evaluation]
                predicted = estimator.predict([features(row, use_slots) for row in rows])
                results[name][evaluation] = metrics([row["label"] for row in rows], predicted)

    train_majority = Counter(row["label"] for row in datasets["train"]).most_common(1)[0][0]
    results["majority"] = {
        split: metrics([row["label"] for row in datasets[split]], [train_majority] * len(datasets[split]))
        for split in ("dev", "test")
    }
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
