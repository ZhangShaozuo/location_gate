# 定位精度三分类工具

输入是中文意图和位置槽位，输出为精确、区域级模糊或城市级模糊。先将已登记的意图别名、槽位名、槽位值和半径单位归一化，再用类别特征训练 CPU 逻辑回归。同义表达及同一槽位组合共享语义组。词典位于 `intent_aliases.tsv` 和 `location_schema.py`。

[归一化组合数据](../normalized-coverage/README.md) 是当前训练入口，包含 356 个三分类组合。仓库自带 46 条独立合成用例。30 条新语义未进入三分类训练，另有 6 条同义写法和 10 条前置规则对照。

## 基线数据生成

```bash
python precision/run.py prepare --out data-baseline
```

基线含 2,625 条三分类表达，对应 256 个语义组合。生成时，同一语义组下的不同写法始终放在同一划分中。 `prepare` 的输出可以用于复现归一化组合数据。

## 推理与看板

```bash
python precision/run.py predict --run runs/normalized-full --input \
  '{"intent":"搜索路线","slots":{"起点来源":"本机实时位置","终点来源":"指定地点"}}'

python precision/run.py dashboard --data normalized-coverage/data --run runs/normalized-eval
```

看板使用保留内部测试集的评估模型。先运行评估模型的 `train` 和 `test`，再用浏览器打开 `runs/normalized-eval/dashboard.html`。全量训练使用三个分片，因此要用单独的合成用例验证。真实用户请求仍需独立采集和人工标注。
