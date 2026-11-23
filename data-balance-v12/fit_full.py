#!/usr/bin/env python3
"""Fit the location-precision classifier on all three v12 splits."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from build import LABELS, key, read_jsonl, write_jsonl
from evaluate import features, make_classifier


def load_training_data(model_dir):
    rows, counts, seen = [], {}, {}
    for split in ("train", "dev", "test"):
        path = model_dir / f"{split}.jsonl"
        records = read_jsonl(path)
        if not records:
            raise ValueError(f"{path} 为空")
        for index, record in enumerate(records, start=1):
            if (not isinstance(record, dict) or not isinstance(record.get("intent"), str)
                    or not record["intent"].strip() or not isinstance(record.get("slots"), dict)
                    or record.get("label") not in LABELS):
                raise ValueError(f"{path} 第 {index} 条不是有效的三分类样本")
            signature = key(record)
            if signature in seen:
                raise ValueError(f"{path} 第 {index} 条与 {seen[signature]} 的意图和槽位重复")
            seen[signature] = f"{path} 第 {index} 条"
            rows.append({field: record[field] for field in ("intent", "slots", "label")})
        counts[split] = len(records)

    labels = Counter(row["label"] for row in rows)
    if set(labels) != set(LABELS):
        raise ValueError("训练数据缺少一个或多个精度标签")
    return rows, counts, labels


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, type=Path, help="v12 build.py 生成的数据目录")
    parser.add_argument("--out", required=True, type=Path, help="保存全量训练集与模型的新目录")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("--out 需要使用新目录")
    try:
        rows, counts, labels = load_training_data(args.data_dir / "model")
    except (OSError, ValueError) as error:
        parser.error(str(error))

    classifier = make_classifier()
    import joblib
    import sklearn

    classifier.fit([features(row, with_slots=True) for row in rows], [row["label"] for row in rows])
    summary = {
        "training_rows": len(rows),
        "source_splits": counts,
        "labels": {label: labels[label] for label in LABELS},
        "class_weights": {label: len(rows) / (len(LABELS) * labels[label]) for label in LABELS},
        "model": "DictVectorizer + LogisticRegression",
        "sklearn_version": sklearn.__version__,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=args.out.parent, prefix=".fit-full-") as tmp:
        stage = Path(tmp) / "output"
        stage.mkdir()
        train_file = stage / "train.jsonl"
        write_jsonl(train_file, rows)
        summary["train_sha256"] = sha256(train_file.read_bytes()).hexdigest()
        joblib.dump(classifier, stage / "model.joblib")
        (stage / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                                            encoding="utf-8")
        stage.rename(args.out)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
