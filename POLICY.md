# 按位置用途和来源决定所需精度

统一意图由 `intent_id` 和 `parameters` 表达。策略入口为 `corpora.policy.precision_for(intent)`。参数标记位置在任务里的角色与来源。原始请求由数据生成器另存到 `reference.utterance`，用于人工核对。

| 现网动作 | 统一意图 | 位置证据与精度 |
|---|---|---|
| 路线规划、查询距离或耗时 | `route.query`、`route.estimate` | 设备当前位置参与起终点时精确，两端均已给定时不涉及设备定位 |
| 导航实时引导 | `navigation.start` | 使用设备当前位置时精确，标记持续使用 |
| 查天气、天气预警 | `weather.query`、`weather.alert` | 使用当前位置查天气时城市级，已有城市时不涉及设备定位 |
| 主动查询当前位置 | `location.self` | 精确并提示，用户明确指定国家、城市或区域时按该粒度处理 |
| 查找地点 | `place.search` | 以设备当前位置查具体地点时精确并告知，已有明确搜索参照点时不涉及设备定位 |
| 呼叫车辆 | `ride.order` | 设备当前位置用作上车点时精确，明确给出上车点时不涉及设备定位 |
| 查询或预订机票、查航班流量 | `transit.flight_ticket`、`transit.flight_traffic` | 用设备位置确定城市时城市级 |
| 查询或预订火车票 | `transit.rail_ticket` | 用设备位置确定出发或目的城市时城市级，车站直接作为查询参数 |
| 搜公交地铁、查看乘车码 | `transit.bus_query`、`transit.ride_code` | 查设备附近站点时精确，按当前位置选乘车码城市时城市级 |
| 查找设备 | `device.find`、`device.find_menu` | 查询目标设备位置时精确，单独打开查找界面时不涉及设备定位 |
| 开始运动 | `fitness.start` | 使用设备位置记录轨迹时持续精确并告知，明确无轨迹时不涉及设备定位 |
| 查询运动数据、查看运动类型 | `fitness.history`、`fitness.activity_types` | 请求存量轨迹时标记区域级和路线概览，查看运动类型时不涉及设备定位 |
| 寄快递 | `package.ship` | 用设备当前位置填寄件地址时精确 |
| 收快递、查收件状态 | `package.receive`、`package.status` | 用设备当前位置填收件地址时精确，查待签收和已签收状态时不涉及设备定位 |
| 查找家电维修、保洁、收纳 | `local_service.search` | 使用设备位置时城市级 |
| 查询旅游指数 | `travel.index` | 使用设备位置时城市级 |
| 查找招聘信息 | `jobs.search` | 使用设备位置时城市级 |
| 叫外卖 | `delivery.order` | 用设备当前位置作为送餐地址时精确 |
| 预订餐厅 | `restaurant.reserve` | 使用设备位置匹配餐厅城市时城市级 |
| 修改、取消、删除日程 | `calendar.update`、`calendar.remove` | 需要附加设备当前位置时城市级，按时间处理日程时不涉及设备定位 |
| 创建提醒 | `reminder.create` | 给提醒附上设备所在城市时城市级，进入或离开某地点触发的提醒送复核 |
| 创建备忘 | `note.create` | 给备忘附上设备所在城市时城市级 |
| 记录信息 | `information.capture` | 给记录附上设备所在城市时城市级 |

## 结构化参数和输出

- `location_source` 表示普通位置参照点，`origin_source`、`destination_source` 表示路线端点，`pickup_source`、`delivery_source`、`address_source` 分别表示上车点、外卖地址和快递地址。用途证据按角色匹配。
- 来源枚举包括 `device_current`、`target_device`、`stored_history`、`named_place`、`saved_place`、`previous_entity`、`none` 和 `unknown`。需要判断的角色缺失或存在冲突时进入 `needs_review/`。
- `requested_granularity` 支持 `precise`、`district`、`city`、`country`，用于主动查询当前位置。明确请求粗略位置但缺少粒度时进入复核。
- 主标签为 `label.precision` 和 `label.coarse_level`。`annotation.location_requirements` 保存 `prompt`、`notify`、`continuous` 或 `route_overview` 等需要业务侧实施的要求。系统鉴权、弹窗、会话结束后停止定位、旧轨迹降采样由调用系统实现。
- 用户表里的「模糊」需要落实到具体档位。此版按表中用途把天气、票务、餐厅和位置附注等落在城市级。把乘车码按城市选择、历史轨迹的路线概览按区域级标注，属于本次实现口径。

公共语料的适配器把可识别的动作和槽位转换成这些字段。适配覆盖情况以 `summary.json` 为准。复核时可回到 `reference` 核实抽取结果。
