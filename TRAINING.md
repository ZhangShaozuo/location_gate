# 已发起定位调用时的精度训练

## 首轮实验

1. 以 `precision_for` 作为条件规则基线。对已经进入定位流程的意图，使用精确和模糊二分类。模型输入取 `model_input.intent_with_parameters` 中的意图 ID 和决策相关的结构化参数，例如 `operation`、`trigger_type`、`requested_granularity`、`tracking_mode`。模型输出字段是 `label.precision`，模糊粒度另存于 `label.coarse_level`。
2. CPU 上用 `OneHotEncoder` 加 `LogisticRegression(class_weight="balanced")` 跑一个轻量对照。将只用意图 ID 和附带结构化参数的结果对比。待人工样本覆盖充分后，用 CatBoost 做第二个基线。
3. 按现网用途抽取人工样本，按对话和模板分组切分。逐项查看精确误放行率、精确召回率与宏平均 F1。模型阈值在验证集确定，再对锁定的测试集报告结果。

[Scikit-learn OneHotEncoder](https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.OneHotEncoder.html) · [Scikit-learn LogisticRegression](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LogisticRegression.html) · [CatBoost 类别特征](https://catboost.ai/docs/en/features/categorical-features)

## 样本使用

- 精确和模糊二分类以主划分为起点。保留 `not_applicable/` 用作调用边界检查。信息不足的意图保留在 `needs_review/`，例如查找设备缺少操作参数。
- `augmentation/device-find-contrast.jsonl` 包含三对合成样本。响铃和定位属于同一意图下的参数对照，可用作规则验收。精确和模糊二分类中，只加入精度属于这两类的合成行。每对样本使用相同的 `group_id`，固定在训练划分。
- 只从 `model_input` 提取训练字段。原句通过 `reference` 供人工复核。避免把来源、原句、样本 ID、规则名和标签元数据引入模型输入。
- 两库重跑得到 5,770 条精度弱标注，二分类有精确和模糊两种标签。用实际已发起定位调用的人工样本独立测试。若后续训练模糊粒度子模型，再补齐目前缺失的国家级样本。
