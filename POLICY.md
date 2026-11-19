# 按已发起的定位调用标注最低所需精度

这里标注的是**在智能体已经尝试调用定位服务的前提下，当前意图需要什么精度**。智能体负责识别意图及判断是否调用。位置精度规则的输入是统一意图 ID 及结构化参数，输出为精确或模糊及其粒度。

意图可能合理使用设备位置时，即使查天气省略城市、叫车省略上车点、火车票已给定两个车站，也按意图标注调用精度。原句只记录在 `reference.utterance`，供人工审核。源语料意图和原句不一致时，依照统一意图标注。

| 现网动作 | 统一意图 | 已发起定位调用时的精度 |
|---|---|---|
| 路线规划、查询距离或耗时 | `route.query`、`route.estimate` | 精确 |
| 导航实时引导 | `navigation.start` | 精确，标记持续使用 |
| 查天气、天气预警 | `weather.query`、`weather.alert` | 模糊·城市级 |
| 查询当前位置 | `location.self` | 缺省精确并提示，明确指定国家、城市或区域时使用该粒度 |
| 查找地点或地址 | `place.search`、`location.address` | 精确并告知 |
| 呼叫车辆 | `ride.order` | 精确 |
| 查订机票及航班流量 | `transit.flight_ticket`、`transit.flight_traffic` | 模糊·城市级 |
| 查订火车票 | `transit.rail_ticket` | 模糊·城市级 |
| 搜公交地铁、查看乘车码 | `transit.bus_query`、`transit.ride_code` | 搜站点精确，乘车码模糊·城市级 |
| 查找设备 | `device.find` | 查询目标设备位置时精确，仅响铃时不涉及 |
| 开始运动 | `fitness.start` | 精确并告知，标记持续使用；明确不记录轨迹时不涉及 |
| 查询运动轨迹、查看运动类型 | `fitness.history`、`fitness.activity_types` | 轨迹概览标为模糊·区域级，运动类型不涉及 |
| 寄快递、收快递 | `package.ship`、`package.receive` | 精确，单独查询快递状态标为不涉及 |
| 查找本地服务 | `local_service.search` | 模糊·城市级 |
| 查询旅游指数 | `travel.index` | 模糊·城市级 |
| 查找招聘 | `jobs.search` | 模糊·城市级 |
| 叫外卖 | `delivery.order` | 精确 |
| 预订餐厅 | `restaurant.reserve` | 模糊·城市级 |
| 创建、修改或删除日程 | `calendar.set`、`calendar.update`、`calendar.remove` | 模糊·城市级 |
| 创建提醒 | `reminder.create` | 模糊·城市级 |
| 创建备忘、记录信息 | `note.create`、`information.capture` | 模糊·城市级 |

本地新闻采用城市级。通用交通信息采用区域级。明确要求粗略当前位置但未指定档位时采用城市级。明确由位置进入或离开触发的闹钟仍需单独确认档位。

已复核的「其他意图」、查询事实、搜索互联网、查询社交内容、发短信和发微信消息均标为不涉及。小程序或公众号操作、支付宝功能、应用内关键词搜索、买东西和查询应用内图片等本批已复核操作也标为不涉及。

## 参数可以改变同一意图的标注

| 意图 | 结构化参数 | 标签 |
|---|---|---|
| 查找设备 | `operation=query_target_location` | 精确 |
| 查找设备 | `operation=ring` | 不涉及 |
| 查找设备 | `operation` 缺失或未识别 | 待复核 |
| 发布社交内容 | `operation=share_current_location` | 模糊·城市级（当前默认） |
| 发布社交内容 | 普通发布，未选择附带当前设备位置 | 不涉及 |
| 启动智能情景 | `trigger_type` 为 `geofence`、`enter_location` 或 `leave_location` | 精确 |
| 启动智能情景 | `trigger_type` 为 `manual`、`schedule` 或 `time` | 不涉及 |
| 启动智能情景 | `trigger_type` 缺失或未识别 | 待复核 |

发布内容里的地点名可以单独作为参数保留。涉及当前位置的社交发布由智能体提供 `operation=share_current_location`。MASSIVE zh-CN 的 15387 号样本经人工检查，在数据适配阶段补录了原数据遗漏的该参数。智能情景的触发类型也来自结构化参数，例如场景配置中的「到达地点」。

设备查找样本保留目标设备类型。对照样本中的同一对使用相同的类型及意图，各对仅改变 `operation`。是否需要告知、可否持续使用、返回轨迹概览等要求存放在 `annotation.location_requirements` 中，由调用系统执行。
