# 从五套公开数据生成定位精度训练集

`prepare.py` 下载、解析并统一 MASSIVE zh-CN、CMPA-SLU、CrossWOZ、RiSAWOZ 和 Google Schema-Guided Dialogue（SGD）。输出的每行对应一个原子意图。安全模型有两种输入视图，分别是不带参数的意图标签和带参数的结构化意图。两种视图共用精度标签。

## 在 Linux 上运行

新版策略见 [现网动作映射](POLICY.md)，模型与人工评估见 [训练方案](TRAINING.md)。

需要 Python 3.10 或更高版本，并使用 Python 自带的 SQLite。仅用标准库即可运行。在内存受限的服务器上，可以安装可选的 `ijson` 以流式解析体积较大的 JSON 文件。

```bash
git clone https://github.com/ZhangShaozuo/location_gate.git
cd location_gate

python3 prepare.py \
  --raw-dir ./raw \
  --out-dir ./data-all
```

默认下载全部五套数据，复用已缓存的文件。需要先看两套中文单轮数据时，使用：

```bash
python3 prepare.py \
  --raw-dir ./raw \
  --out-dir ./data-zh-single \
  --datasets massive cmpa \
  --with-reference
```

已有文件可以按下表放入缓存目录，再加 `--offline` 运行。临时 SQLite 和结果写到输出目录的同一个父目录。磁盘空间有限时，建议把原始数据和输出放在工作盘，再把对应路径传给 `--raw-dir` 和 `--out-dir`。

| 来源 | 缓存路径（相对 `--raw-dir`） | 下载来源 |
|---|---|---|
| MASSIVE 1.1 zh-CN | `massive-1.1.tar.gz`，或解压出的 `zh-CN.jsonl` | [Amazon 官方发布](https://github.com/alexa/massive) |
| CMPA-SLU | `cmpa-full.zip`（发布包 `Full_Category.zip`） | [官方仓库](https://github.com/XingChen-AGI/CMPA-SLU) |
| CrossWOZ | `crosswoz/train.json.zip`、`crosswoz/val.json.zip`、`crosswoz/test.json.zip` | [清华 CoAI 官方仓库](https://github.com/thu-coai/CrossWOZ) |
| RiSAWOZ | `risawoz/train.json`、`risawoz/dev.json`、`risawoz/test.json` | [GEM 导出的原始 JSON](https://huggingface.co/datasets/GEM/RiSAWOZ/tree/main) |
| Google SGD | `sgd.tar.gz`，或解压后的 `sgd/{train,dev,test}/dialogues_*.json` | [Google Research 官方仓库](https://github.com/google-research-datasets/dstc8-schema-guided-dialogue) |

输出目录须为新路径。CMPA-SLU、CrossWOZ 和 SGD 的下载固定 Git 提交。MASSIVE 和 CMPA-SLU 校验下载包的 SHA-256，RiSAWOZ 使用 GEM 的 `main`。所有原始输入文件的 SHA-256 都写入报告。下载使用默认 TLS 证书校验。有证书错误时，可在受信任的网络下载文件后用 `--offline` 运行。使用数据时遵循各来源的许可。

## 多轮数据怎样变成一条意图

| 数据源 | 提取依据 | 转换方式 |
|---|---|---|
| MASSIVE | `intent`、`annot_utt` | 每条原始记录一条意图。解析原始槽位，再补充部分位置来源。 |
| CMPA-SLU | `output` 中的意图和槽位 | 每条原始记录一条意图。保留未提供的参数状态，例如只有目的地时不推断上车点。 |
| CrossWOZ | 用户轮的 `dialog_act`、已出现的实体 | 按当前行动领域分组，累积已表达的约束，从先前系统轮提取已出现的参照实体。 |
| RiSAWOZ | `user_actions` 与当轮 `belief_state` | 使用当前行动领域的槽位，按该领域提取已知信息和本轮问的字段。 |
| Google SGD | 用户轮 `frames[].state` 和 `actions` | 每个服务帧独立抽取当前意图和槽位。同服务的前一轮确认与当前用户回复可形成确认状态。 |

多轮处理在当前用户轮截止。一个用户轮可产生多条意图行。相同上下文中未变化的意图状态不重复输出。CrossWOZ 与 RiSAWOZ 中能确定的「这里」「他家」会关联到前文实体。无法可靠解析的引用保留为不明确。只纳入在对话中有证据的任务，整段对话保留官方划分。CrossWOZ 的 `val` 统一命名为 `dev`。

天气、路线、导航、叫车、外卖、附近搜索等公共意图使用统一的意图 ID 和参数键。其他意图保留源意图名称或领域，未做跨数据集语义合并。当前适配器按相关领域或服务拆分任务。同一领域里同时提出多个不同任务时，CrossWOZ 和 RiSAWOZ 可能仍合并为一条带多个槽位的意图，建议在正式测试集中人工检查此类对话。

## 输出字段

每次输出 `train.jsonl`、`dev.jsonl`、`test.jsonl` 和 `summary.json`。JSONL 的每一行是一个完整 JSON 对象。下例仅展示模型输入和标签。

```json
{
  "model_input": {
    "intent_label": "叫车",
    "intent_with_parameters": {
      "intent_id": "ride.order",
      "label": "叫车",
      "parameters": {
        "destination": "机场",
        "pickup_source": "unknown"
      }
    }
  },
  "label": {
    "precision": "精确",
    "coarse_level": null
  }
}
```

- **意图输入**用 `model_input.intent_label` 或 `model_input.intent_with_parameters`。用同一批样本和划分就能对比两种输入。
- **标签**用 `label.precision` 做精确和模糊二分类，或用 `label.coarse_level or label.precision` 做精度分档。「精确」和「不涉及」的 `coarse_level` 为 `null`。
- **审核**用 `annotation.rule` 和 `annotation.review_required`。每条记录也有 `source`、`source_id`、`group_id` 和 `turn_index`，方便回到原始样本。
- **参考文本**默认输出到每条记录顶层的 `reference`。其中 `reference.utterance` 是原始用户输入，`reference.turns_through_current_user` 保存当前轮及最近几条对话，供人工核对。主划分和两个旁路目录都保留该字段。安全模型直接读取选定的 `model_input` 字段。旧版可显式传 `--with-reference`，需要导出省略原文的副本时传 `--no-reference`。

## 精度弱标注

精度标签由 [现网动作映射](POLICY.md) 生成。规则假定智能体已尝试调用定位服务，按结构化意图判断所需精度。比如叫车在此条件下标为精确，天气与查订火车票标为模糊城市级。是否调用仍由智能体判断。

「不涉及」写作 `{"precision":"不涉及","coarse_level":null}`，用于设置普通闹钟、调音量、查询事实、搜索互联网、普通社交发布、消息及已复核的应用内操作等。发布时明确附带当前位置按模糊城市级标注。智能情景只有在结构化触发参数表明使用围栏时标为精确。查找设备时，查看目标设备位置或仅响铃均标为不涉及，从发起手机的当前位置导航到目标设备标为精确。查找设备缺少操作类型、智能情景缺少触发方式时进入待复核。

默认主划分只包含位置精度样本。去重后的「不涉及」样本按划分放在 `not_applicable/`，待复核样本放在 `needs_review/`。需要把「不涉及」作为第五类时，加 `--include-not-applicable`。此时主划分和 `not_applicable/` 中可能同时存在该类记录，训练直接读取主划分即可。

终端为每个划分分别打印主文件条数 `total`、去重总数 `deduplicated_total`，以及 `not_applicable_saved` 和 `needs_review_saved`。主文件的标签分布见 `classes`。

合成对照样本单独输出到 `augmentation/device-find-contrast.jsonl`。手机、手表和平板各有一组，每组对照 `query_target_location`、`ring` 和 `navigate_to_target`，共 9 条。合成样本标为训练划分，单独计数。

这些标签用于训练原型和检查覆盖范围。精确放行效果应在有人工真值的测试集上测量。弱标签和真实用户位置授权属于不同环节。

## 数据量、去重和类别分布

脚本先生成候选意图，再按规范化的当前原话与结构化意图去除完全重复。相同记录出现在多个划分时，优先保留测试集，其次验证集。按标签分流后可对主训练集设总上限、每类上限，并选择自然比例或尽可能均衡的抽样。主验证集和主测试集保留各自符合纳入规则的去重样本。训练采样不复制少数类样本。

```bash
python3 prepare.py \
  --raw-dir ./raw \
  --out-dir ./data-train-capped \
  --offline \
  --max-train 12000 \
  --train-sampling balanced
```

可以加 `--max-train-per-class 4000` 限制每类训练行数。均衡模式在指定总量下尽量给每个有余量的类相近配额。某类耗尽后，余量分给其他类，因此结果可能仍明显偏斜。类别名额充足时，该类中每个有数据的来源先保留一条，其余按来源的样本量分配。可用 `--seed` 固定抽样。

`summary.json` 的 `stages` 包含提取后、去重后和主划分的分布。每阶段都有按来源、按划分和按标签的计数。`sidecars` 记录另存的两组样本。`exported_intent_distribution` 给出主划分每个意图的总数及各标签数。`intent_labels_with_multiple_precision_classes` 列出主划分中同一个无参数意图对应多个精度标签的情况，例如明确要求不同粒度的「查询当前位置」。

在 MASSIVE zh-CN 和 CMPA-SLU 上重新标注全部 23,580 条去重记录。v6 的公开语料记录与 v5 逐条比对一致。28 条待复核样本包括 19 条触发方式不明的智能情景和 9 条操作不明的查找设备。其余三套使用样本验证适配。

| 划分 | 主划分 | 精确 | 区域级 | 城市级 | 国家级 | 不涉及 | 待复核 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 训练 | 3,934 | 478 | 752 | 2,704 | 0 | 11,588 | 16 |
| 验证 | 802 | 102 | 150 | 550 | 0 | 2,721 | 6 |
| 测试 | 1,034 | 113 | 182 | 739 | 0 | 3,473 | 6 |

已有原始数据时，在仓库目录拉取新版后离线生成。

```bash
git pull --ff-only origin main
python3 prepare.py --raw-dir ./raw --out-dir ./data-location-v6 --datasets massive cmpa --offline
```

`summary.json` 的 `label_policy` 记录当前标注版本，`augmentation` 记录合成对照集位置。旧版数据可用同一批原始缓存按新版策略整体重建。

可运行 `python3 -m unittest discover -s tests -v` 核查多轮引用、条件精度、对照数据和划分。
