"""Render training and robustness metrics as a self-contained HTML dashboard."""

from collections import Counter
from html import escape
import json

from dataset import read


def table(headers, rows):
    def line(values, tag):
        return "<tr>" + "".join(f"<{tag}>{escape(str(value))}</{tag}>" for value in values) + "</tr>"
    return "<table><thead>" + line(headers, "th") + "</thead><tbody>" + "".join(line(row, "td") for row in rows) + "</tbody></table>"


def render(data, run):
    def load(path):
        return json.loads(path.read_text(encoding="utf-8"))

    info = load(data / "dataset_summary.json")["splits"]
    training = load(run / "training.json")
    metrics = load(run / "metrics.json")
    labels = metrics["labels"]
    named = {"train": "训练", "dev": "验证", "test": "测试", "controls": "不涉及对照"}
    test = metrics["evaluation"]["test"]
    risks = test["coarse_overprecision_groups"]
    control = metrics["controls"]
    cards = [
        ("测试语义组 Macro-F1", f"{test['macro_f1_by_group']:.3f}"),
        ("测试改写预测变化", f"{test['variant_changed_vs_canonical']} / {test['rows']}"),
        ("模糊组误判精确", f"{risks['errors']} / {risks['total']}"),
    ]
    contents = ['<div class="cards">' + "".join(f"<article><span>{label}</span><strong>{value}</strong></article>" for label, value in cards) + "</div>"]
    contents.append("<h2>数据分布</h2>" + table(
        ("划分", "语义组", "表达样本", *labels),
        [(named[split], n["semantic_groups"], n["rows"], *[n["labels"].get(label, 0) for label in labels])
         for split, n in info.items()],
    ))
    contents.append("<h2>验证与测试</h2>" + table(
        ("划分", "表达样本准确率", "语义组 Macro-F1", "全部变体正确的组", "模糊组误判精确"),
        [(named[split], f"{row['row_accuracy']:.1%}", f"{row['macro_f1_by_group']:.3f}",
          f"{row['groups_all_variants_correct']} / {row['semantic_groups']}",
          f"{row['coarse_overprecision_groups']['errors']} / {row['coarse_overprecision_groups']['total']}")
         for split, row in metrics["evaluation"].items()],
    ))
    contents.append("<h2>测试集混淆矩阵</h2><p>每个语义组统计一次。行是真实标签，列是模型预测。</p>" +
                    table(("真实标签", *labels), [(label, *row) for label, row in zip(labels, test["group_confusion"])]))
    contents.append("<h2>按改写类型测试</h2>" + table(
        ("改写类型", "正确", "样本", "准确率"),
        [(name, result["correct"], result["rows"], f"{result['correct'] / result['rows']:.1%}")
         for name, result in test["by_variant"].items()],
    ))
    contents.append("<h2>不涉及本机定位的对照</h2>" + table(
        ("对照表达", "语义组", "规则识别不涉及", "仅跑三分类时预测精确"),
        [(control["rows"], control["semantic_groups"], control["rule_not_applicable"], control["model_alone_predicted_exact"])],
    ))
    mistakes = read(run / "errors.jsonl")
    error_counts = Counter(row["scenario"] for row in mistakes if row["split"] == "test")
    examples = [row for row in mistakes if row["split"] == "test" and row["variant"] == "canonical"]
    contents.append("<h2>测试误判</h2><p>此表每个语义组显示一个标准输入。完整误判在 errors.jsonl。</p>"
                    + (table(("意图", "输入槽位", "参考标签", "模型预测", "该组误判表达数"),
                             [(r["intent"], json.dumps(r["slots"], ensure_ascii=False), r["label"], r["predicted"],
                               error_counts[r["scenario"]]) for r in examples]) if examples else "<p>标准输入无误判。</p>"))
    result = run / "dashboard.html"
    result.write_text(
        """<!doctype html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>本机定位精度模型看板</title>
<style>
:root{font:16px system-ui,sans-serif;color:#142a38;background:#f4f7f8}
body{margin:0}main{max-width:1100px;margin:auto;padding:36px 24px 64px}
h1{font-size:32px;margin:0 0 10px}h2{font-size:21px;margin:34px 0 10px}p{color:#406070;margin:8px 0 16px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:30px 0}
article{padding:17px;background:#fff;border:1px solid #d6e4e8;border-left:4px solid #006a6e;border-radius:6px}
strong,span{display:block}strong{font-size:28px;margin-top:6px;color:#06595e}
table{border-collapse:collapse;width:100%;background:#fff}th,td{text-align:left;padding:9px 12px;border-bottom:1px solid #dde7ea}
th{background:#e3edf0;font-size:14px}td{overflow-wrap:anywhere}
@media(max-width:600px){main{padding:20px 12px}table{font-size:12px}th,td{padding:6px}h1{font-size:25px}}
</style></head><body><main><h1>本机定位精度模型看板</h1>"""
        + f"<p>{escape(training['model'])} · 训练 {training['semantic_groups']} 个语义组</p>"
        + "<p>结果来自规则标注的合成场景和已配置的同义写法。测试语义组与训练集隔离。</p>"
        + "".join(contents) + "</main></body></html>",
        encoding="utf-8",
    )
    return result
