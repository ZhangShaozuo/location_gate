# 结构化位置精度模型训练建议

## 首轮实验

1. 以 `precision_for` 作为确定性基线。结构化动作和位置角色齐全时直接执行策略。意图缺项时收集缺项类型并请求补充，例如叫车只有目的地时补问上车点。
2. 需要训练模型时，先用 CPU 跑 `OneHotEncoder` 加 `LogisticRegression(class_weight="balanced")`。输入只取 `model_input.intent_with_parameters` 的意图 ID 和经允许的类别参数，包括位置来源及角色、所需粒度、确认状态和轨迹模式。另做只含意图 ID 的对照，量化缺少位置角色时的误差。
3. 人工标注覆盖充分后，用支持类别特征的 CatBoost 做第二个基线。对比其精度、误放行率和覆盖率。模型输出作为候选精度，跑过规则定义的位置来源和精度上限之后，由业务侧执行告知或确认。

[Scikit-learn OneHotEncoder](https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.OneHotEncoder.html) · [Scikit-learn LogisticRegression](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LogisticRegression.html) · [CatBoost 类别特征](https://catboost.ai/docs/en/features/categorical-features)

## 数据建设

- 主精度任务读取主划分，标签为精确、区域级、城市级、国家级。按前置规则处理不涉及设备定位的记录，保留这批数据供人工回溯和测试策略。待复核记录补齐位置角色、参照来源或所需粒度后进入人工标注。
- 只从模型记录提取训练字段。原始请求在 `reference` 供审核。排除数据来源、样本 ID、规则名、告知方式和历史标签等可能携带答案的字段。
- 用现网 DAU 确定优先抽样动作，先覆盖导航、查询设备位置、天气、当前位置和提醒。每个动作补配对样本，例如「上车点来自当前位置」与「上车点已给定」。叠加低频业务和信息不足样本。原表的 DAU 可能跨行重叠，可保留自然比例测试集，再建立按场景覆盖的压力测试集。
- 完整地保留同一对话、同一主体或同一模板的样本组。划分后再做加权或采样。弱标注用于初始化和检查数据链路。独立人工测试集可从每个精度档 50 条起步。当前两套语料没有国家级训练样本，优先补足这档和其余少样本场景，再评估四分类。

## 验收

同时报告各档支持样本数、精确率、召回率、宏平均 F1，以及精确误放行率。精确误放行率以人工真值为模糊或不涉及设备定位的样本为分母，统计预测或放行到精确的比例。单独统计查找设备、持续跟踪、位置来源未明、位置已给定和用户明确要求更粗粒度的用例。先用验证集确定阈值或复核策略，再对锁定测试集报告效果。缺类的测试集应明确标为尚未覆盖该档。
