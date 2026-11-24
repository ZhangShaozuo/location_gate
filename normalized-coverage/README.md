# 归一化定位精度组合扩充

本次直接补充标准意图和归一化后的槽位组合。每个组合保留一条。同一个意图只换别名、标点或单位写法，计为同一个组合。

| 用途 | 扩充前组合 | 扩充后组合 |
| --- | ---: | ---: |
| 训练 | 167 | 267 |
| 验证 | 38 | 38 |
| 内部测试 | 51 | 51 |
| 三分类全量 | 256 | 356 |
| 不涉及定位对照 | 205 | 233 |

新增 100 个三分类训练组合，精确 66、区域级模糊 29、城市级模糊 5。原外部测试的 30 个新语义组合继续留出。三分类语义组合的定义沿用原模型的 `semantic_key`。

`data/coverage_matrix.tsv` 列出 656 个唯一组合。包含原有组合、补充组合、保留的外测组合及待确认的组合。补充时先列出允许的场景和预期标签，再以原规则复算；29 个口径待确认的组合不进入训练。例子包括查看乘车码、按本机所在城市筛选后删除日程、围栏提醒，以及超过当前阈值且要求严格半径的地点搜索。`data/live_actions.tsv` 列出现网表 17 个领域的动作映射。公交查询和乘车码分开核对。

本次覆盖以现网表和现有槽位规则为边界。更多现网动作组合需要依据实际槽位约束和真实输入继续确认。

## 运行

在仓库根目录运行。已安装依赖时可直接开始训练。

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r precision/requirements.txt

python precision/run.py train \
  --data normalized-coverage/data --run runs/normalized-full --all

python external-test/batch_test.py \
  --data normalized-coverage/data --run runs/normalized-full \
  --out external-test-normalized
```

第二条使用仓库里的独立外测用例。要复现实验用的内部测试，在全量拟合之外单独运行以下命令。

```bash
python precision/run.py train \
  --data normalized-coverage/data --run runs/normalized-eval
python precision/run.py test \
  --data normalized-coverage/data --run runs/normalized-eval
```

## 复现组合矩阵

```bash
python precision/run.py prepare --out data-baseline
python normalized-coverage/build_coverage.py \
  --base data-baseline \
  --external external-test/external_test.jsonl \
  --out normalized-coverage-rebuilt
```

本地实跑结果见 `verification.json`。旧外部合成测试中的新语义仍为 30/30，同义改写仍为 6/6。扩充后的分组模型在原内部验证集判对 34/38，在原内部测试集判对 50/51。旧模型分别为 36/38 和 51/51。样本覆盖扩大，当前实验仍未验证真实流量中的效果。
