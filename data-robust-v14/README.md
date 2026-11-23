# 本机定位精度 v14

输入是中文意图和位置槽位，输出是精确、区域级模糊或城市级模糊。数据包含同义的意图、中文槽位名、同义槽位值、标点，以及米与公里的等价表达。处理支持的别名用显式词典归一化。尚未登记的意图别名会报错，新增时可编辑 `intent_aliases.tsv`。槽位词典在 `schema_v14.py`。

| 划分 | 表达样本 | 语义组 |
| --- | ---: | ---: |
| 训练 | 1,864 | 167 |
| 验证 | 302 | 38 |
| 测试 | 459 | 51 |
| 不涉及对照 | 743 | 205 |

三分类数据有 2,625 条表达，源于 v13 的 401 个结构化输入。去掉不影响精度的辅助业务动作和围栏来源后，按 256 个语义组切分。每组的标准写法和所有同义改写进入同一划分，训练中该组的所有写法共用一份权重。同义改写的效果通过规则可控的归一化实现。模型学习归一化后不同意图和位置约束的精度。地名、原始用户文本、场景编号和改写类型均不进入模型特征。

半径按同一个阈值转换为训练特征和规则输入。`350 米`、`0.35 公里` 和其对应的半径分档会得到同样的规则输入。硬半径与允许放宽的近似半径通过 `scope` 区分。新构建校验所有基础样本的归一化规则标签，阻止跨拆分重复和改写变义。

## Linux 快速运行

在仓库根目录运行。生成数据和训练目录均使用新路径。已有生成数据时可从训练开始。

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r data-robust-v14/requirements.txt

python data-robust-v14/run.py prepare --out data-v14
python data-robust-v14/run.py train --data data-v14 --run runs/v14
python data-robust-v14/run.py test --data data-v14 --run runs/v14
python data-robust-v14/run.py dashboard --data data-v14 --run runs/v14
```

训练使用 CPU 逻辑回归。批量测试输出 `metrics.json` 和 `errors.jsonl`。训练完成后用浏览器打开 `runs/v14/dashboard.html`。看板展示语义组 Macro-F1、各类改写的准确率、混淆矩阵、模糊误判成精确和对照结果。CPU 训练一次完成，看板显示训练后的指标。

### 测一条意图

```bash
python data-robust-v14/run.py predict --run runs/v14 --input \
  '{"intent":"搜索路线","slots":{"起点来源":"本机实时位置","终点来源":"指定地点"}}'
```

这一例会归一为「查询路线」，模型与规则均返回精确。预测输出包含归一化输入、规则参考结果和模型预测。如果规则判不涉及、待复核或超出范围，预测接口显示该结果，模型精度字段为 null。离线对照指标也记录跳过规则时三分类模型会输出多少精确。

### 评估完成后用全部样本训练

```bash
python data-robust-v14/run.py train --data data-v14 --run runs/v14-full --all
```

这会使用 2,625 条三分类表达和全部 256 个语义组，包含原验证与测试数据。全量模型的效果需用新的测试集评估。已有看板反映的是按训练集拟合的模型。

## 文件与历史版本

`seed_train.jsonl` 和 `seed_controls.jsonl` 是通过 v13 生成并核验的种子。 `dataset.py` 构建固定划分和同义改写，`run.py` 提供运行入口，`dashboard.py` 生成单文件看板。现有 `corpora/` 供规则复算，`prepare.py` 仍用于公开语料处理。v12 与 v13 的实验目录可在各自的历史分支查阅。

测试结果衡量相同规则体系下未参加训练的语义组合，以及已配置同义词的表达稳定性。用于核验的场景均源于现有结构化样本，真实流量及人工独立标注的泛化结果仍待测。
