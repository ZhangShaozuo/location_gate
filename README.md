# 从五套公开数据生成定位精度训练集

`prepare.py` 下载、解析并统一 MASSIVE zh-CN、CMPA-SLU、CrossWOZ、RiSAWOZ 和 Google Schema-Guided Dialogue（SGD）。输出的每行对应一个原子意图。安全模型有两种输入视图，分别是不带参数的意图标签和带参数的结构化意图。两种视图共用精度标签。

## 在 Linux 上运行

需要 Python 3.10 或更高版本，并使用 Python 自带的 SQLite。仅用标准库即可运行。在内存受限的服务器上，可以安装可选的 `ijson` 以流式解析体积较大的 JSON 文件。

```bash
unzip location-intent-corpora.zip
cd location-intent-corpora

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
    "precision": "模糊",
    "coarse_level": "区域级"
  }
}
```

- **意图输入**用 `model_input.intent_label` 或 `model_input.intent_with_parameters`。用同一批样本和划分就能对比两种输入。
- **标签**用 `label.precision` 做精确和模糊二分类，或用 `label.coarse_level or label.precision` 做精度分档。「精确」和「不涉及」的 `coarse_level` 为 `null`。
- **审核**用 `annotation.rule` 和 `annotation.review_required`。每条记录也有 `source`、`source_id`、`group_id` 和 `turn_index`，方便回到原始样本。
- **参考文本**用 `--with-reference` 输出到 `reference`。它包含原句和最近几个对话消息，供人工核对。安全模型直接读取选定的 `model_input` 字段。

## 精度弱标注

精度标签由本项目的规则生成。规则函数 `precision_for` 接收归一后的意图和参数。精确类别表示意图已有清楚的位置角色或精度诉求，所有精确样本标为需要优先复核。

| 已提取的意图和参数 | 标注结果 |
|---|---|
| 本地天气，或查询地点未指定 | 模糊·城市级 |
| 已指定查询地名的天气，如「北京天气」 | 不涉及设备定位 |
| 找设备附近的餐馆或查询区域路况 | 模糊·区域级 |
| 搜索参照点为已确定的前文实体或外部地名 | 不涉及设备定位 |
| 导航起点、打车上车点或外卖配送地址明确为设备当前位置 | 精确 |
| 用户明确查询自己的坐标、具体位置或详细地址 | 精确 |
| 用户明确问自己在哪个国家、城市或区 | 对应的模糊级别 |
| 未说明导航起点、打车上车点或当前位置所需精度 | 模糊·区域级，并标记为优先复核 |
| 设置定时闹钟、调音量等与设备位置无关的任务 | 不涉及设备定位 |
| 「到家后提醒」等带位置触发条件的非定位领域意图，或现有规则未覆盖的意图 | 待复核，精度为 `null` |

「国家级」用于确实需要设备位置且只需国家范围的任务，例如「我在哪个国家」。「不涉及」在 JSON 中写作 `{"precision":"不涉及","coarse_level":null}`。缺少规则依据的意图单独进入复核。

默认主划分只包含位置精度样本。去重后的「不涉及」样本按划分放在 `not_applicable/`，待复核样本放在 `needs_review/`。需要把「不涉及」作为第五类时，加 `--include-not-applicable`。此时主划分和 `not_applicable/` 中可能同时存在该类记录，训练直接读取主划分即可。

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

`summary.json` 的 `stages` 包含提取后、去重后和主划分的分布。每阶段都有按来源、按划分和按标签的计数。`sidecars` 记录另存的两组样本。`exported_intent_distribution` 给出主划分每个意图的总数及各标签数。`intent_labels_with_multiple_precision_classes` 列出同一个无参数意图对应多个标签的情况，例如「叫车」会因上车点来源不同而改变标签。

MASSIVE zh-CN 和 CMPA-SLU 全量实测合计输入 24,341 条，去重后的 23,580 条分布如下。其余三个来源用样本验证，完整五库总量以实际运行的统计报告为准。

| 划分 | 主划分总数 | 精确 | 模糊·区域级 | 模糊·城市级 | 模糊·国家级 | 不涉及 | 待复核 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 训练 | 1,594 | 9 | 906 | 679 | 0 | 10,041 | 3,903 |
| 验证 | 353 | 2 | 177 | 174 | 0 | 2,122 | 1,054 |
| 测试 | 416 | 3 | 205 | 208 | 0 | 2,880 | 1,217 |

可运行 `python3 -m unittest discover -s tests -v` 核查多轮引用、确认状态、去重和训练集配额。
