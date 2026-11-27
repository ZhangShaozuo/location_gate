# HarmonyOS 公开标准意图目录

[标准意图目录](catalog.jsonl)提取自华为开发者联盟的[《附录：标准意图接入规范》](https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/insight-intent-access-specifications/)，核对日期为 2026-11-27。目录含公开附录中的全部 100 个意图、14 个领域和 174 个顶层入参条目，其中 20 个意图无入参。

目录覆盖华为公开的标准意图。小艺内部的任务计划、各应用注册的自定义意图，以及指定设备上实际可用的能力清单属于其他范围。华为另在 SDK 中保存标准意图 JSON Schema，并支持开发者定义自定义意图。参见[《意图开发概述》](https://developer.huawei.com/consumer/cn/doc/harmonyOS-Guides/insight-intent-definition/)。

## 文件格式

每行一个意图。以下是 `ViewTravelCardCode` 的目录记录：

```json
{
  "name": "ViewTravelCardCode",
  "domain": "NavigationDomain",
  "since": "1.0.1",
  "param": {
    "travelCardType": {
      "type": "string", "required": false,
      "values": ["Metro", "Bus"], "defaultFrom": "last_viewed_type"
    },
    "adminCode": {
      "type": "number", "required": false, "defaultFrom": "current_city"
    }
  }
}
```

- `name`、`domain` 和 `since` 分别为官方意图名、领域标识和意图起始版本。起始版本指意图版本。
- `param` 以入参名称为键，记录公开表中的类型和必选标记。`param: {}` 表示该意图未列出入参。
- 部分重点字段补充了对象子字段、可选值和默认行为。对象的 `fields` 来自公开文字定义，`exampleFields` 来自样例。二者均只记录字段名。语音入口下的 `StartNavigate.wayPoints` 等条件必填，以及公开表所述的组合约束，单独记录。
- 该文件用于查询和映射。实际开发时用目标 SDK 的 JSON Schema 校验。目录中的类型按公开表保留，例如 `ViewSmartDevice.functionType` 表中标为 `object`，但示例为字符串。

`ViewTravelCardCode` 的 `adminCode` 描述应用打开哪个城市的乘车码。`defaultFrom: "current_city"` 记录省略时的业务默认值；公开表未说明哪个组件补齐城市。调用记录只有城市编码时，不能反推出编码来自用户指定地点还是本机定位。生成本项目模型输入时，位置来源槽位需要来自可信的执行上下文。

## 查询

```bash
jq 'select(.name == "StartNavigate" or .name == "ViewTravelCardCode")' harmonyos-intents/catalog.jsonl
jq -s 'group_by(.domain) | map({domain: .[0].domain, count: length})' harmonyos-intents/catalog.jsonl
```
