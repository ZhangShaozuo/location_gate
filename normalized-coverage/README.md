# 归一化定位精度组合扩充

本次直接补充标准意图和归一化后的槽位组合。每个组合保留一条。同一个意图只换别名、标点或单位写法，计为同一个组合。

| 用途 | 基线组合 | 上一版组合 | 当前组合 |
| --- | ---: | ---: | ---: |
| 训练 | 167 | 267 | 284 |
| 验证 | 38 | 38 | 38 |
| 内部测试 | 51 | 51 | 51 |
| 三分类全量 | 256 | 356 | 373 |
| 不涉及定位对照 | 205 | 233 | 235 |

本次新增 17 个三分类训练组合，精确 14、城市级模糊 3。全量标签分布为精确 181、区域级模糊 88、城市级模糊 104。原外部测试的 30 个新语义组合继续留出。

`data/coverage_matrix.tsv` 列出 646 个唯一组合，本轮已清空矩阵中的待确认项。排除 12 个同时要求按实际距离找最近和只使用城市级位置的冲突组合。`data/live_actions.tsv` 列出现网表 17 个领域的动作映射。

| 任务 | 归一化槽位 | 标签 |
| --- | --- | --- |
| 查找或推荐地点，要求严格半径 | `src=device_current, scope=strict_radius, radius_band=above_policy_limit` | 精确 |
| 查看乘车码，按当前城市选码 | `src=device_current` | 城市级模糊 |
| 创建提醒，进入或离开地理围栏 | `trigger=enter_location` 或 `trigger=leave_location` | 精确 |
| 删除日程或查询运动轨迹，按本机当前城市筛选 | `op=filter_by_city, src=device_current` | 城市级模糊 |
| 删除日程或查询运动轨迹，按用户指定的城市筛选 | `op=filter_by_city, src=named_place` | 不涉及 |

「不涉及」对照由规则复算，独立存储在 `data/controls.jsonl`。三分类训练读取 `train.jsonl`，全量训练再读取 `dev.jsonl` 和 `test.jsonl`。

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

本地实跑结果见 `verification.json`。原外部合成测试的新语义为 30/30，同义改写为 6/6。只拟合训练集时，模型在原内部验证集判对 35/38，其中 2 条区域级样本被误判为精确。在原内部测试集判对 50/51，其中 1 条精确样本被误判为城市级。当前实验仍未验证真实流量中的效果。
