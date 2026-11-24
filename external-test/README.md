# 定位精度模型外部测试

`external_test.jsonl` 有 46 条合成用例。默认通过当前归一化组合数据训练的全量模型进行评估。 

| 类型 | 条数 | 用途 |
| --- | ---: | --- |
| 新语义 | 30 | 训练未见的意图与槽位组合，三档精度各 10 条 |
| 同义改写 | 6 | 已见语义的不同写法 |
| 规则对照 | 10 | 验证不涉及本机定位的输入 |

```bash
python external-test/batch_test.py \
  --data normalized-coverage/data \
  --run runs/normalized-full \
  --out external-test-results
```

输出目录里，`summary.json` 按测试类型统计结果，`predictions.jsonl` 保存逐条结果，`errors.jsonl` 保存错例。脚本校验测试样本与训练语义组的关系。重复运行时请使用新的输出路径。
