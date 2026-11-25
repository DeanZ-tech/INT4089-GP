# Smart Library USB Serial Protocol v1.0

**状态：开发版契约；待真实 Arduino UNO 编译、上传和串口联调验收。**

## 适用范围与边界

- 一台 Arduino UNO、一套传感器、一个实体座位 `A01`。
- USB 串口，**9600 baud（特意保持 V2.2 原设定）**，8N1；每条消息为一行紧凑 JSON，末尾 `\n`。Arduino 兼容 `\r\n` 入站。
- 编码：出站仅 ASCII（因此也是合法 UTF-8）；所有业务枚举使用英文大写。
- 保持原版逻辑不变：椅垫 D2、托盘 A0、测距与 OLED 共用 I2C；140mm 距离阈值；300/500 滞回；2秒稳定、3秒空闲确认、10秒暂离锁定；EEPROM、OLED 第二行「超时待确认」和管理员释放规则。
- **只改变通信协议**。不新增锁定事件编号、不改变告警触发算法、不增加额外硬件，不改变 9600 波特率。
- 必须确保 Arduino IDE 的 Serial Monitor 和 Python 不同时独占同一 COM 端口。

## 消息类型总览

| `type` | 方向 | 说明 |
|---|---|---|
| `boot` | Arduino → Python | 每次启动（含 USB 打开导致 UNO 自动复位）输出一次；包含 EEPROM 恢复的锁定信息 |
| `telemetry` | Arduino → Python | 每轮采样结束输出一次，含物理状态、最终状态、原始传感器证据 |
| `error` | Arduino → Python | 初始化失败、命令无法识别或超过行长度 |
| `command` | Python → Arduino | 管理员释放 A01 |
| `ack` | Arduino → Python | 释放指令处理结果，不能与“已经确认空闲”混淆 |

所有消息共有 `v:1`、`type`、`id:"A01"`。一个 JSON 对象独占一行；没有前缀日志、没有 Markdown 代码围栏、不在值内输出换行。

## 1. `boot`（UNO → Python）

```json
{"v":1,"type":"boot","id":"A01","locked":true,"armed":false,"away_ms":10031}
```

| 字段 | JSON 类型 | 含义 |
|---|---|---|
| `locked` | boolean | EEPROM 恢复的超时锁定；不因 UNO 重启自动解锁 |
| `armed` | boolean | 旧告警解除后是否已经具备再次超时检测资格 |
| `away_ms` | integer | 锁定时最后保存的暂离时长快照；不是服务器当前时间 |

## 2. `telemetry`（UNO → Python）

```json
{"v":1,"type":"telemetry","id":"A01","seq":12,"ms":16324,"seat":true,"tray_raw":24,"tray":true,"distance_mm":110,"distance_valid":true,"physical":"IN_USE","state":"LOCKED","locked":true,"armed":false,"away_ms":10124,"reason":"WAIT_ADMIN","new_alert":false}
```

| 字段 | JSON 类型 | 解释 |
|---|---|---|
| `seq` | integer | 本次启动后递增；重启可从0开始，不是永久事件 ID |
| `ms` | integer | 本次启动后的 `millis()`，**不是 Unix 时间戳** |
| `seat` | boolean | D2=LOW 时 `true`，表示椅垫触发 |
| `tray_raw` | integer | A0 原始模拟值（通常0～1023） |
| `tray` | boolean 或 null | 根据300/500滞回阈值得到的有物/无物；尚未确定时为 `null` |
| `distance_mm` | integer 或 null | VL53L0X 有效距离，单位毫米；无效为 `null` |
| `distance_valid` | boolean | 本轮测距是否有效 |
| `physical` | string | 传感器推断物理状态 `UNKNOWN` / `IN_USE` / `AWAY` / `FREE` |
| `state` | string | 最终**对外**状态；锁定优先，否则等于 `physical` |
| `locked` | boolean | 超时锁定是否有效。锁定时即使 `physical=IN_USE`，`state` 仍为 `LOCKED` |
| `armed` | boolean | 是否允许触发下一次超时锁定 |
| `away_ms` | integer | OLED 同源的显示时长；锁定后可能保持快照 |
| `reason` | string | 代码化诊断原因，见下 |
| `new_alert` | boolean | 本轮刚达到超时触发点；**判断锁定应以 `locked` 为准**，不能只监听这一瞬时标志 |

`state` 枚举：`UNKNOWN`、`IN_USE`、`AWAY`、`FREE`、`LOCKED`。

`reason` 当前输出枚举：`WAIT_ADMIN`、`CONFIG_INVALID`、`TRAY_UNKNOWN`、`DISTANCE_INIT_FAILED`、`DISTANCE_INVALID`、`DISTANCE_UNCERTAIN`、`SENSOR_CONFLICT`、`STABILIZING`、`NORMAL`。

**网页状态原则：** `locked=true` 时必须显示超时待确认，不能显示可用；设备离线由 Python 根据最后一次接收时间独立判断，不能以物理 `FREE` 代替。

## 3. 管理员释放指令 `command`（Python → UNO）

```json
{"v":1,"type":"command","action":"RELEASE","id":"A01"}
```

注意：为避免在 UNO R3 上引入大型 JSON 解析依赖，**这一个入站命令必须保持字节顺序、大小写、键名和无多余空格完全一致**。传输时追加 `\n`，程序可忽略 `\r`。这是合法 JSON Lines 的一个受限子集，不代表 Arduino 支持任意字段顺序的 JSON 对象。

它取代了 V2.2 的 `RELEASE:A01` 文本指令。身份验证属于 Python 后端，Arduino 只识别指定协议字节，不负责登录。Arduino 仍采用 V2.2 的 `releaseSeatByAdmin()` 行为。

## 4. 执行应答 `ack`（UNO → Python）

成功：

```json
{"v":1,"type":"ack","id":"A01","action":"RELEASE","result":"RELEASED","locked":false}
```

没有处于锁定状态时：

```json
{"v":1,"type":"ack","id":"A01","action":"RELEASE","result":"NO_ACTIVE_LOCK","locked":false}
```

ACK 仅表示 UNO 接受并执行了释放逻辑；后续 `state` 需等待实时传感器重新确认。**管理员网页在收到 `RELEASED` ACK 之前不能显示释放成功。**

## 5. 错误消息 `error`（UNO → Python）

```json
{"v":1,"type":"error","id":"A01","code":"BAD_COMMAND"}
```

支持的 `code`：
- `BAD_COMMAND`：未知格式或无效管理指令
- `COMMAND_TOO_LONG`：超过固定缓冲长度的输入行，丢弃至换行
- `OLED_NOT_FOUND`：未找到 OLED I2C 地址
- `DISTANCE_INIT_FAILED`：测距初始化失败
- `CONFIG_INVALID`：演示阈值设置无效

即使 OLED 未找到，后续串口监测数据仍可以继续发送；此行为与原版一致。

## 6. Python 状态归一化与事件

Python 只负责：
1. 按 `\n` 读取串口、`json.loads()`、验证 `v/type/id`；不得解析 V2.2 人类可读中文日志。
2. 以 `locked` 和 `state` 为设备状态来源；存储接收时间、重要状态变化、`boot/error/ack` 等历史事件。
3. 通过 WebSocket 实时推送给 React；设备超过4秒未收到有效协议消息时，报告 `OFFLINE`（后端 UI 判定，不改变 Arduino 状态）。
4. 管理员网页请求释放时，后端验证管理凭证，再发送**完全一致**的单行 `command`。
5. 等待 `ack`，收到 `RELEASED` 后以新一轮 `telemetry` 判定占用；不直接将座位置为 `FREE`。

当状态为 `LOCKED` 且传感器 `physical=IN_USE`：系统仍然锁定，不能重新分配。

**未解决而明确保留的 V2.2 限制：** 无持久的事件 `lock_id`；没有通用 JSON 命令解析器；同一旧锁事件和新事件不能靠事件编号区分；传感器阈值和计时恢复规则仍是 V2.2 的行为；9600 baud 的串口吞吐会限制实际采样速度。这些均不在本次用户授权的修改范围内。
