# 统一定位精度数据

`prepare.py` 将公开语料转成统一意图、位置槽位和精度标签。主文件从四档精度中写入语料实际覆盖的标签。每行对应一个原子意图。当前核验的组合是 MASSIVE zh-CN、CMPA-SLU、CrossWOZ 和 SMP2019-ECDT。RiSAWOZ 和 Google Schema-Guided Dialogue（SGD）也可通过 `--datasets` 选择。

## Linux 运行

在仓库目录运行。需要 Python 3.10 或更高版本，使用自带 SQLite。首次运行会下载缺少的原始文件。已有全部缓存时可加 `--offline`，输出目录使用新路径。可选安装 `ijson` 以流式解析大型 JSON。

```bash
git pull --ff-only origin main
python3 prepare.py \
  --raw-dir ./raw \
  --out-dir ./data-location-slots-v7-zh \
  --datasets massive cmpa crosswoz smp2019
```

按来源限制主训练文件时，可加 `--max-train-per-source 5000 --train-sampling balanced`，并换一个输出目录。先对每个来源分配类别配额，再应用可选的 `--max-train` 总量和 `--max-train-per-class` 类别上限。均衡抽样做无放回选取，验证集和测试集保留各自完整的去重结果。

| 来源 | 缓存路径（相对 `--raw-dir`） | 下载来源 |
|---|---|---|
| MASSIVE 1.1 zh-CN | `massive-1.1.tar.gz` 或 `zh-CN.jsonl` | [Amazon 官方发布](https://github.com/alexa/massive) |
| CMPA-SLU | `cmpa-full.zip` | [官方仓库](https://github.com/XingChen-AGI/CMPA-SLU) |
| CrossWOZ | `crosswoz/train.json.zip`、`crosswoz/val.json.zip`、`crosswoz/test.json.zip` | [清华 CoAI](https://github.com/thu-coai/CrossWOZ) |
| SMP2019-ECDT | `smp2019/train.json` | [公开训练副本](https://github.com/ygwpz/SMP2019-ECDT-NLU/blob/65ad29bba6a625dea72b3353298171c43f927e4a/dataSet/train.json) |
| RiSAWOZ | `risawoz/train.json`、`risawoz/dev.json`、`risawoz/test.json` | [GEM 数据](https://huggingface.co/datasets/GEM/RiSAWOZ/tree/main) |
| Google SGD | `sgd.tar.gz` 或 `sgd/{train,dev,test}/dialogues_*.json` | [Google Research](https://github.com/google-research-datasets/dstc8-schema-guided-dialogue) |

SMP2019 读取公开副本的 2,579 条训练样本，仅进入训练划分。发布版 MASSIVE、CMPA-SLU 和 SMP2019 输入文件校验 SHA-256。报告记录每个实际输入文件的哈希及下载地址。TLS 证书错误时，可在受信任网络缓存原始文件后离线处理。

## 意图和槽位

`schema` 为 `location-slots-v4`。导出使用统一中文意图名称，下例是一条 SMP2019 导出行。

```json
{"id":"smp2019:train:200:0:0","intent":"查询路线","slots":{"from":"济源市","to":"河南省电信分公司"},"label":"精确","ref":{"text":"从济源市到河南省电信分公司怎么走","native":"map.route"},"meta":{"review":true,"rule":"route.query"}}
```

| 字段 | 含义 |
|---|---|
| `intent` | 统一的中文意图名称。MASSIVE、CMPA-SLU 与 SMP2019 的查询天气均导出为「查询天气」，查询降雨导出为「查询降雨」。 |
| `slots` | 可为空的对象，只保留与位置有关的参数或条件。 |
| `label` | `精确`、`区域级模糊`、`城市级模糊`、`国家级模糊`。旁路文件还使用 `不涉及` 和 `待复核`。 |
| `id` | 包含来源、划分、原始记录或对话 ID、轮次和序号，供回查和按对话分组。 |
| `ref` | 保留 `text` 原话、`native` 源标签，以及适用时的 `ctx` 历史消息。用 `--no-reference` 可省略。 |
| `meta` | 按需记录复核标记、依据或调用要求，如 `notice` 和 `mode`。 |

模型输入为 `intent` 或 `intent + slots`，目标为 `label`。 `from` 和 `to` 表示起点和终点，`pickup` 表示上车点，`loc` 表示显式地点，`near` 表示附近搜索的参照地点。明确的来源用 `src`、`from_src`、`to_src` 和 `pickup_src` 表示，如 `device_current`、`saved_place`、`previous_entity`。命名地点直接用地点值，缺失来源用省略槽位表示。

`op` 表示会影响定位的操作，例如让设备响铃或导航到目标设备。 `level` 表示查询当前位置时明确要求的粒度，取 `precise`、`district`、`city`、`country` 或 `coarse_unspecified`。 `trigger` 表示触发方式，例如地理围栏，`track` 表示影响位置使用的运动追踪条件。餐品、人数、价格等参数留在原语料和参考文本中。

适配器使用原始意图与槽位，按领域和动作归并。SMP2019 的地图 `ROUTE` 映射为 `route.query`，有明确查询目标的 `POSITION` 映射为 `location.address`。票务的 `startLoc_*`、`endLoc_*` 与城际客车的 `Src`、`Dest` 分别归并到起点与终点。CrossWOZ 从当前及之前的对话行动提取约束，将同轮明确给出的参照实体保留为 `near`，再按任务领域输出。人工复核时可用 `ref` 检查同一领域里叠加了多个任务的样本。

## 划分、统计和弱标注

- 顶层 `train.jsonl`、`dev.jsonl`、`test.jsonl` 默认用于精度分类。按规范化原话、统一意图和槽位去重，跨划分重复时优先保留测试集，其次验证集。
- `not_applicable/` 保存「不涉及」样本。加 `--include-not-applicable` 可以把这类样本同时纳入主文件。 `needs_review/` 保存暂未定档的样本。
- `summary.json` 的 `stages` 按来源、划分、标签统计提取、去重及导出结果。 `label_names` 将历史统计简称映射到 JSONL 中的完整标签。 `exported_intent_distribution` 以内部意图 ID 为键，`label` 为导出的中文意图名称。 `sidecars` 记录两个旁路目录的分布。
- `augmentation/` 提供两组规则验收文件。 `device-find-contrast.jsonl` 覆盖查询目标、响铃、导航。 `self-location-contrast.jsonl` 覆盖同一意图请求四档精度的四条合成记录。合成样本单独计数。
- 精度来自 [现网规则](POLICY.md) 的弱标注。训练和评估方式见 [训练方案](TRAINING.md)。

运行 `python3 -m unittest discover -s tests -v` 检查预处理和规则。
