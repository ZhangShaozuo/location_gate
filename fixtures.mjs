// Public landmarks and synthetic boundary points. Coordinates and city mappings are demo fixtures.
const place = (name, city, latitude, longitude, density = "dense") => ({ name, city, latitude, longitude, density });
export const locations = Object.freeze({
  shenzhen: place("深圳 · 福田中心区", "深圳市", 22.531472, 114.047613),
  shenzhen_coast: place("深圳 · 大鹏海岸", "深圳市", 22.58710, 114.52020, "sparse"),
  beijing: place("北京 · 国贸", "北京市", 39.90870, 116.45658),
  beijing_north: place("北京 · 延庆城区", "北京市", 40.45690, 115.97417, "medium"),
  shanghai: place("上海 · 外滩", "上海市", 31.23840, 121.48960),
  shanghai_island: place("上海 · 崇明东滩", "上海市", 31.52175, 121.95154, "sparse"),
  guangzhou: place("广州 · 珠江新城", "广州市", 23.11926, 113.32365),
  hangzhou: place("杭州 · 西湖东岸", "杭州市", 30.24944, 120.16015),
  chengdu: place("成都 · 春熙路", "成都市", 30.65440, 104.08368),
  chongqing: place("重庆 · 解放碑", "重庆市", 29.55726, 106.57791),
  wuhan: place("武汉 · 光谷", "武汉市", 30.50644, 114.39788),
  nanjing: place("南京 · 新街口", "南京市", 32.04129, 118.78401),
  xian: place("西安 · 钟楼", "西安市", 34.26119, 108.94222),
  suzhou: place("苏州 · 金鸡湖", "苏州市", 31.31310, 120.69651),
  ningbo: place("宁波 · 东钱湖", "宁波市", 29.78020, 121.65090, "medium"),
  xiamen: place("厦门 · 环岛路", "厦门市", 24.43227, 118.13027),
  qingdao: place("青岛 · 五四广场", "青岛市", 36.06294, 120.38444),
  changsha: place("长沙 · 五一广场", "长沙市", 28.19653, 112.97692),
  kunming: place("昆明 · 滇池北岸", "昆明市", 24.95397, 102.64905, "medium"),
  dali: place("大理 · 洱海西岸", "大理市", 25.67100, 100.19100, "medium"),
  huangshan: place("黄山 · 汤口镇", "黄山市", 30.08660, 118.17760, "medium"),
  sanya: place("三亚 · 亚龙湾", "三亚市", 18.23256, 109.64031, "medium"),
  harbin: place("哈尔滨 · 中央大街", "哈尔滨市", 45.77805, 126.61974),
  urumqi: place("乌鲁木齐 · 红山公园", "乌鲁木齐市", 43.80790, 87.60560, "medium"),
  lhasa: place("拉萨 · 八廓街", "拉萨市", 29.65293, 91.13288, "medium"),
  qilian: place("青海 · 祁连山区", "", 38.01723, 100.26422, "sparse"),
  singapore: place("新加坡 · 滨海湾", "新加坡", 1.28342, 103.86071),
  tokyo: place("东京 · 涩谷", "东京", 35.65803, 139.70164),
  sydney: place("悉尼 · 环形码头", "悉尼", -33.86111, 151.21054),
  oslo: place("奥斯陆 · 港区", "奥斯陆", 59.90678, 10.75307, "medium"),
  reykjavik: place("雷克雅未克 · 港区", "雷克雅未克", 64.15108, -21.94149, "medium"),
  anchorage: place("安克雷奇 · 市中心", "安克雷奇", 61.21807, -149.90033, "medium"),
  dateline_east: place("国际日期变更线 · 东经侧", "", 5.2, 179.9997, "unavailable"),
  dateline_west: place("国际日期变更线 · 西经侧", "", 5.2, -179.9997, "unavailable"),
  arctic: place("北极圈 · 高纬合成点", "", 78.2, 15.6, "sparse"),
});

const cityAliases = { shenzhen_coast: "shenzhen", beijing_north: "beijing", shanghai_island: "shanghai" };
export function cityForLocation(id) {
  if (!Object.hasOwn(locations, id) || !locations[id].city) return "";
  return Object.hasOwn(cityAliases, id) ? cityAliases[id] : id;
}

export const cityFixtures = Object.freeze(Object.fromEntries(
  Object.entries(locations).filter(([, point]) => point.city).map(([id, point]) => {
    const representative = {
      shenzhen: [22.5431, 114.0579],
      beijing: [39.9042, 116.4074],
      shanghai: [31.2304, 121.4737],
    };
    const cityId = cityForLocation(id);
    const [latitude, longitude] = representative[cityId] ?? [point.latitude, point.longitude].map(
      value => Number(value.toFixed(2)),
    );
    return [cityId, { name: point.city, latitude, longitude }];
  }),
));

const local = { src: "device_current" };
const places = { from_src: "named_place", to_src: "named_place" };
const fromHere = { ...places, from_src: "device_current" };
const near = { ...local, scope: "nearby" };
const city = { ...local, level: "city" };
const nearest = { ...local, scope: "nearest" };
const fixed = { src: "named_place" };
const share = { ...local, op: "share_current_location" };
const E = "精确", R = "区域级模糊", C = "城市级模糊", N = "不涉及";
const sample = (id, domain, title, intent, slots, location, expected, settings = {}) =>
  ({ id, domain, title, intent, slots, location, expected, ...settings });

export const cases = [
  sample("navigation", "导航", "从当前位置开始实时导航", "开始导航", { ...fromHere, track: "route" }, "shenzhen", E),
  sample("route-home", "导航", "查询回收藏地址的路线", "查询路线", { from_src: "device_current", to_src: "saved_place" }, "chengdu", E),
  sample("route-duration", "导航", "查询去机场的时长", "查询路线距离或耗时", fromHere, "shanghai", E),
  sample("route-fixed", "导航", "只查两个已知地标之间的路线", "查询路线", places, "beijing", N),
  sample("navigation-coarse", "导航", "实时导航仅获模糊权限", "开始导航", { ...fromHere, track: "route" }, "nanjing", E, { access: "approximate" }),
  sample("traffic-near", "驾车路况", "查看周边路况概况", "查询路况", near, "wuhan", R),
  sample("traffic-route", "驾车路况", "查询到家路线上的路况", "查询路况", { from_src: "device_current", to_src: "saved_place" }, "chongqing", E),
  sample("weather", "天气与环境", "按本机所在城市查天气", "查天气", { "位置来源": "当前位置" }, "shenzhen", C),
  sample("rain", "天气与环境", "查询本市是否下雨", "查询降雨", city, "hangzhou", C),
  sample("weather-alert", "天气与环境", "查询本市天气预警", "查询天气预警", local, "harbin", C),
  sample("weather-named", "天气与环境", "设备在哈尔滨，查乌鲁木齐天气", "查询天气", { loc: "乌鲁木齐市" }, "harbin", N),
  sample("environment", "天气与环境", "查本市空气质量和生活指数", "查询环境或生活指数", city, "xian", C),
  sample("weather-blocked", "天气与环境", "天气查询未获得定位授权", "查询天气", local, "guangzhou", C, { access: "denied" }),
  sample("weather-coarse", "天气与环境", "仅获模糊权限时查询本市天气", "查询天气", local, "oslo", C, { access: "approximate" }),
  sample("nearby", "地图与地点", "查找附近地点", "查找或推荐地点", { "位置来源": "当前位置", "搜索约束": "附近" }, "shenzhen", R),
  sample("gym-nearest", "地图与地点", "找离当前位置最近的健身房", "查找或推荐地点", { ...nearest, target: "健身房" }, "guangzhou", E),
  sample("pharmacy-350m", "地图与地点", "严格筛选 350 米内的药店", "查找或推荐地点", { ...local, radius_m: "350 米", target: "药店" }, "qingdao", E),
  sample("poi-radius", "地图与地点", "按可放宽的约 3 公里找充电站", "查找或推荐地点", { ...local, scope: "rough_radius", radius_m: "3 公里", target: "充电站" }, "suzhou", R),
  sample("unrelated", "地图与地点", "设备在深圳，找北京地标周边地点", "查找或推荐地点", { scope: "nearby", near: "航空航天博物馆" }, "shenzhen", N),
  sample("poi-dense", "地图与地点", "高密度档位查附近商店", "查找或推荐地点", { ...near, target: "商店" }, "singapore", R),
  sample("poi-sparse", "地图与地点", "低密度档位查周边休息点", "查找或推荐地点", { ...near, target: "休息点" }, "qilian", R),
  sample("poi-fallback", "地图与地点", "日期变更线附近模拟缺少密度数据", "查找或推荐地点", near, "dateline_east", R),
  sample("poi-arctic", "地图与地点", "在高纬度合成点查找附近地点", "查找或推荐地点", near, "arctic", R),
  sample("address-here", "当前位置", "查询脚下位置的地址", "查询地点地址", local, "nanjing", E),
  sample("position-exact", "当前位置", "查看当前准确坐标", "查询当前位置", { level: "precise" }, "lhasa", E),
  sample("position-district", "当前位置", "查看当前所在区域", "查询当前位置", { level: "district" }, "reykjavik", R),
  sample("position-city", "当前位置", "查看当前所在城市", "查询当前位置", { level: "city" }, "sydney", C),
  sample("position-unresolved", "当前位置", "日期变更线附近没有城市解析", "查询当前位置", { level: "city" }, "dateline_west", C),
  sample("restaurant-near", "餐饮与外卖", "推荐大致周边餐馆", "查找或推荐餐馆", near, "chengdu", R),
  sample("restaurant-walk", "餐饮与外卖", "按步行耗时查餐馆", "查找或推荐餐馆", { ...local, scope: "walking_time" }, "changsha", E),
  sample("restaurant-fixed", "餐饮与外卖", "已给定黄山，查询当地小吃", "查找或推荐餐馆", { scope: "nearby", near: "黄山市" }, "hangzhou", N),
  sample("restaurant-book", "餐饮与外卖", "只按所在城市预订餐馆", "预订餐馆", city, "xiamen", C),
  sample("delivery-near", "餐饮与外卖", "浏览附近可配送的外卖", "查找外卖", near, "tokyo", R),
  sample("delivery-order", "餐饮与外卖", "下单外卖，使用默认定位策略", "下单外卖", {}, "shanghai", E),
  sample("delivery-status", "餐饮与外卖", "查看已下单外卖状态", "查询外卖订单状态", {}, "chengdu", N),
  sample("hotel-near", "住宿", "查大鹏海岸附近住宿", "查找或推荐酒店", near, "shenzhen_coast", R),
  sample("hotel-nearest", "住宿", "筛选最近的酒店", "查找或推荐酒店", nearest, "sanya", E),
  sample("hotel-city", "住宿", "在所在城市选酒店", "预订酒店", city, "dali", C),
  sample("ride", "用车", "从当前所在点叫车", "叫车", { pickup_src: "device_current", to_src: "named_place" }, "wuhan", E),
  sample("ride-saved", "用车", "上车点使用收藏地址", "叫车", { pickup_src: "saved_place" }, "qingdao", N),
  sample("stations-near", "公交地铁", "查看附近公共交通选项", "查询公共交通", near, "tokyo", R),
  sample("station-nearest", "公交地铁", "查找最近的地铁站", "查询公交地铁", nearest, "singapore", E),
  sample("transit-qr", "公交地铁", "打开指定城市的乘车码", "查看乘车码", { loc: "上海市" }, "xian", N),
  sample("train", "交通票务", "查从本市出发的火车票", "查询或预订火车票", fromHere, "changsha", C),
  sample("flight", "交通票务", "查从本市出发的航班", "查询或预订机票", { from_src: "device_current" }, "urumqi", C),
  sample("airport-flow", "交通票务", "查看本市机场航班流量", "查询机场航班流量", city, "anchorage", C),
  sample("coach", "交通票务", "查看从本市出发的城际客车", "查询城际客车", fromHere, "ningbo", C),
  sample("cinema", "休闲与活动", "查找附近电影院", "查询影院或影片", near, "beijing_north", R),
  sample("events", "休闲与活动", "查附近的周末活动", "查找或推荐活动", near, "shanghai_island", R),
  sample("release-date", "休闲与活动", "查询影片上映日期", "查询影片上映日期", {}, "hangzhou", N),
  sample("repair", "本地服务", "按城市查找家电维修", "查找本地服务", city, "chongqing", C),
  sample("cleaning", "本地服务", "查看附近保洁服务", "查找本地服务", { ...near, target: "保洁" }, "ningbo", R),
  sample("career-city", "招聘", "查本市招聘信息", "查找招聘信息", city, "suzhou", C),
  sample("career-near", "招聘", "浏览附近招聘信息", "查找招聘信息", near, "shanghai", R),
  sample("tour-index", "旅游", "查所在城市旅游指数", "查询旅游指数", local, "huangshan", C),
  sample("tour-specified", "旅游", "设备在昆明，查三亚旅游指数", "查询旅游指数", { loc: "三亚市" }, "kunming", N),
  sample("parcel-send", "快递", "按本机位置预约上门寄件", "寄快递", local, "xiamen", E),
  sample("parcel-receive", "快递", "收件交接使用当前位置", "收快递", local, "guangzhou", E),
  sample("parcel-status", "快递", "查询物流状态", "查询快递状态", {}, "dali", N),
  sample("device-route", "设备查找", "从本机导航到目标设备", "查找设备", { from_src: "device_current", op: "navigate_to_target", to_src: "target_device" }, "beijing", E),
  sample("device-ring", "设备查找", "让另一台设备响铃", "查找设备", { op: "ring" }, "shenzhen", N),
  sample("device-target", "设备查找", "查询另一台设备的位置", "查找设备", { op: "query_target_location" }, "beijing", N),
  sample("fitness-route", "运动", "开始户外运动并记录轨迹", "开始运动", { ...local, track: "route" }, "sanya", E),
  sample("fitness-indoor", "运动", "开启运动但关闭轨迹", "开始运动", { track: "no_route" }, "xian", N),
  sample("fitness-history", "运动", "查询已保存运动轨迹", "查询运动轨迹", { src: "stored_history" }, "kunming", N),
  sample("calendar-city", "日程与提醒", "修改日程并仅附上当前城市", "修改日程", { ...share, level: "city" }, "lhasa", C),
  sample("calendar-geofence", "日程与提醒", "创建到达围栏触发的日程", "创建日程", { trigger: "enter_location" }, "hangzhou", E),
  sample("remind-city", "日程与提醒", "创建提醒并附当前城市", "创建提醒", { ...share, level: "city" }, "shenzhen", C),
  sample("remind-timed", "日程与提醒", "设置定时提醒", "创建提醒", { trigger: "time" }, "chengdu", N),
  sample("memo", "备忘与记录", "创建备忘并记下当前城市", "创建备忘", { ...share, level: "city" }, "sydney", C),
  sample("record", "备忘与记录", "记录信息时附当前城市", "记录信息", share, "reykjavik", C),
  sample("scene-fence", "智能情景", "到达收藏地点时启动智能情景", "启动智能情景", { trigger: "enter_location", to_src: "saved_place" }, "shenzhen_coast", E),
  sample("scene-driving", "智能情景", "按驾驶状态启动情景", "启动智能情景", { trigger: "driving" }, "nanjing", N),
  sample("social-city", "社交与资讯", "发帖并仅附当前城市", "发布社交内容", { ...share, level: "city" }, "singapore", C),
  sample("social-text", "社交与资讯", "只发文字动态", "发布社交内容", {}, "sydney", N),
  sample("news-local", "社交与资讯", "查询本地新闻", "查询新闻", local, "harbin", C),
];
