# Web Studio VikingBot 产品与实现方案

状态：设计与首期实现说明。首期支持网页对话；IM 渠道接入通过 provider 扩展，当前已注册 Telegram provider，其他 IM 在 Studio 中标注“开发中”。

## 当前分支实现说明

- 页面入口 `/vikingbot`；新增管理接口集中在 `/api/v1/admin`，网页聊天继续复用原有接口。
- IM 连接和收发时间线持久化到 Bot 数据目录的 `studio.sqlite3`，文件权限 0600。它含应用与专用用户凭证，备份需按服务端配置处理。
- Studio 管理的 IM 会话仅开放带绑定身份的 OpenViking 查询与记忆工具；Shell、本地文件、定时任务及未显式批准的 MCP 工具默认不可用。
- 首期仅服务管理员可管理渠道；按当前 account 隔离连接及 IM 历史。接入时选择同账户普通用户，由服务端绑定现有凭证；浏览器无需接收或输入用户 API Key。管理员身份不可选，仅存储哈希而无法自动绑定凭证的用户显示不可用。
- 受管启动时自动为父子进程生成内部管理令牌，不写回配置文件。独立 Gateway 需要额外的管理部署支持。
- 连接生命周期支持凭证更新、暂停/恢复、重启恢复连接与群内验证；具体接入方式（扫码、手动表单等）由各平台 provider 实现。
- IM 时间线展示 Studio 连接建立后捕获的消息，不自动接管原 ov.conf 渠道或补录它们的旧历史。既有渠道的迁移需要后续显式绑定与身份确认。
- 支持暂停连接并保留历史，也支持确认后删除连接及其本地收发记录。删除不会删除外部平台应用或平台中的消息。IM 会话首期只读。
- 受管 Agent 会话以连接 ID 隔离；删除重建后不继承旧连接上下文，也不发送旧连接未完成的回复。同一连接暂停恢复或重启后仍可续接。此前未按连接隔离的 Agent 历史不自动迁移，Studio 已捕获的只读消息记录不受影响。
- 自动化和模拟接口浏览器验证不等同真实 IM 群验收；真实收发仍需部署后使用应用凭证与测试群验证。


## 接口范围与复用依据

路由遵循仓库管理接口约定：`/api/v1/admin` 为管理前缀，账号在 URL 中指定，router 自身声明 prefix/tags，并由 `routers/__init__.py` 导出、`app.py` 统一挂载。业务管理仍仅允许 ROOT，不能因挂入 admin 前缀而放宽为账号 ADMIN。

以下表格用 `B` 代表 `/api/v1/admin/accounts/{account_id}/bot`：

| HTTP 路由 | 调用场景与契约 |
| --- | --- |
| `GET /api/v1/admin/bot/capabilities` | 判断 Bot 启用及 ROOT 管理能力；与运行健康检查职责不同。 |
| `GET /api/v1/admin/accounts/{account_id}/users?role=user&include_credentials=false` | **复用现有接口**。返回 `user_id`、`role`、`api_key_available`，不返回密钥或前缀。默认参数保持原有接口行为。 |
| `GET B/connections` | 渠道列表、混合会话来源、扫码完成后加载连接。 |
| `POST B/connections` | 手动连接；请求包含 `type`、`user_id`、平台自有的 `credentials` 对象。 |
| `PATCH B/connections/{id}` | 更新 `enabled`；提交 `revision` 保留并发保护。 |
| `DELETE B/connections/{id}?revision=N` | 删除连接及其本地记录；不删除外部平台应用。 |
| `POST B/connections/{id}/credentials` | 更新平台凭证，包含 `credentials`、`user_id`、`revision`；服务端重新绑定身份。 |
| `POST B/connections/{id}/verifications` | 发起可选群验证，提交 `revision`。 |
| `GET B/connections/{id}/conversations` | 连接下的收发会话列表。 |
| `GET B/connections/{id}/messages?conversation=...&before=...` | 捕获消息及发送状态；平台会话标识保留在查询参数中。 |
| `POST B/onboarding-runs` | 创建自动接入任务，显式传 `type`、`user_id`、`request_id` 和可选 `name`。 |
| `GET B/onboarding-runs/current?type=...` | 查询指定平台当前未完成任务；没有任务时返回 null。不是全量任务列表。 |
| `GET B/onboarding-runs/{id}` | 轮询指定任务。 |
| `POST B/onboarding-runs/{id}/actions` | 请求体 `action` 严格限定为 `retry`、`cancel`、`manual`，保留各操作的状态校验。 |

浏览器管理接口共 13 个，加上复用的用户列表接口。扫码任务的重试、取消和转手动共用一个 actions 接口，连接生命周期保持独立方法。Studio 管理路由及 Gateway 内部 dispatch 均不进入 OpenAPI schema；接口仍正常注册并保留原鉴权。旧的 `PATCH {action: ...}` 和 `X-OpenViking-Studio-Account` 已移除。该变更调整当前未发布 PR 内的接口，前后端需一起更新；不为旧的临时浏览器接口保留兼容入口。

网页会话创建、列表、历史、删除、Bot 聊天流式响应和健康状态继续复用既有 API。平台收发记录按连接归属并保存发送状态，不能直接替换为 OpenViking 上下文会话历史。

`POST /bot/v1/studio/dispatch` 仅在 Bot Gateway 内部保留，用内部令牌及 loopback 限制服务端调用。浏览器不直接调用；账号和绑定用户仍在 OpenViking 服务端校验。

### 后续接入钉钉等平台

- URL 按连接和接入任务组织，不含具体平台名称。平台由显式 `type` 决定；未知平台由 provider registry 拒绝，不能默认为任何平台。
- 平台凭证放入 `credentials` 对象，例如 `app_id/app_secret`，各平台可以使用自己的字段。具体校验、连接运行、凭证更新及公开配置字段由 provider 负责；浏览器不能借凭证字段替换服务端身份。
- 暂停、恢复、删除、收发记录和任务查询共享资源接口。各平台的授权实现与前端表单放入 provider 目录；平台特有能力不应直接加入全局路径或假设所有平台支持扫码/群验证。
- 当前已注册 Telegram provider：管理员粘贴 @BotFather 生成的 Bot Token，服务端通过 `getMe` 校验并以长轮询收发消息，无需公网地址。Telegram Bot 可被任何人搜索到，因此 Studio 接入必须填写允许对话的 Telegram 用户 ID 或 @用户名（`settings.allow_from`，可在设置中修改），名单外的消息不进入 Agent 与历史记录。更换 Token 时必须属于同一个 Bot。
- 新增钉钉等平台需要实现它的鉴权、连接、消息转换和 UI，并验证其接入状态流；通用路由不是钉钉功能已完成的证明。

未使用的定时任务接口及 UI、旧独立 IM 会话列表、旧 `step` 操作已删除，既有 CLI/Agent 定时任务功能不受影响。

## 1. 用户目标与首期范围

用户可以在 Web Studio 中直接与 VikingBot 对话、查阅历史，并在 IM provider 可用时通过引导将同一个 Bot 接入 IM 群。网页和各个群的对话上下文独立；共用 Bot 不代表共享所有会话或个人记忆。

首期交付：

- 一级导航新增 **VikingBot**，包含“对话”和“渠道”两个页面。
- 网页新建对话、流式回复、停止生成、继续历史对话。
- 查看有权限访问的网页会话，以及已接入 IM 的单聊、普通群、话题群历史。
- IM 渠道的连接检查、群内验证、暂停和恢复连接（接入向导由 provider 提供）。
- Slack、钉钉、Discord 等尚无 provider 的平台展示“开发中”，无配置表单、无可点击的接入按钮。文案说明“Studio 接入管理开发中”，避免误称底层完全不支持。

首期不提供从 Studio 代发群消息、导入机器人入群前的 IM 历史、跨群共享上下文。网页聊天不依赖 IM 配置完成。

## 2. 页面结构

```text
VikingBot                         Bot 运行正常
  对话 | 渠道

对话页
┌──────────────────┬──────────────────────────────────┐
│ 新建对话          │ 需求分析 · 网页                   │
│ 搜索对话          │ 问题、回复与流式输出               │
│ 全部 / 网页 / IM   │ 姓名、时间、正文、发送状态           │
│                  │                                  │
│ 今天             │ 工具调用默认折叠                   │
│ 需求分析 · 网页   │                                  │
│ 项目讨论群 · IM   │ IM 会话只读，请前往原平台继续对话     │
└──────────────────┴──────────────────────────────────┘
```

“对话”默认选中最近一次打开且仍有权限的会话，否则显示欢迎页。窄屏先显示列表，选择后进入详情，提供返回列表操作。

列表显示标题、来源、最后消息摘要和时间；IM 话题显示“群名 / 话题摘要”。不向普通用户暴露群 ID、消息 ID 或内部 SessionKey。名称暂不可用时显示“群聊（名称待同步）”，技术 ID 仅在管理员诊断详情中展示。

“渠道”页包含网页渠道、已连接的 IM 应用、由已注册 provider 提供的添加入口，以及其他 IM 的开发中卡片。一个应用可以服务多个群；应用连接和群会话分别展示，不把一个群建成一个渠道。

## 3. 首次启用与网页对话

### 3.1 进入页面

页面分别检测 Bot 服务、模型配置和当前身份权限：

| 状态 | 页面文案与操作 |
|---|---|
| Bot 未启用 | “先启用 VikingBot”；管理员看到 `openviking-server --with-bot` 与部署说明，普通用户看到“请联系管理员启用” |
| 服务不可达 | “暂时无法连接 VikingBot”；显示重试与管理员诊断入口，不清除已有历史 |
| 模型未配置 | “配置对话模型后即可开始”；链接现有模型配置说明，说明默认继承根级 `vlm` |
| 可以使用 | “开始与 VikingBot 对话”；主按钮“新建对话”；有可用 IM provider 时显示次按钮“连接 IM” |

读取配置只代表模型已配置，不代表调用成功。首次正常对话成功后记录模型可用；模型调用失败保留输入并提供重试。

### 3.2 开始与继续对话

1. 点击“新建对话”，输入问题。
2. 首次发送时建立持久会话；提交接受前保留输入、阻止重复发送。
3. 流式展示回答，工具调用折叠展示，支持停止生成。
4. 左侧立即出现新会话，标题取首条问题，可重命名。
5. 刷新、重新登录或服务重启后，可重新打开历史继续对话。

切换会话、取消或卸载页面时，旧请求不能覆盖新会话内容。停止浏览器流不自动表示服务端任务已取消；产品只有在服务端确认取消后才显示“已停止”，否则显示“已停止接收，任务可能仍在运行”。

## 4. 身份、权限和上下文

- 渠道配置及密钥修改仅管理员可用；服务端逐接口鉴权，不能仅隐藏按钮。
- 首期群历史仅对该连接所属管理范围内的管理员开放。普通 Studio 用户只查看自己的网页会话；后续另行实现 IM 成员身份绑定与按群授权。
- 外部应用必须绑定明确的 OpenViking account/workspace 与运行身份；无绑定或无权限时拒绝启用，不回退 root 身份。
- 群会话不得继承管理员私人网页会话或个人记忆。群可访问资源与记忆范围使用受限的渠道身份配置。
- 列表、搜索、详情、附件、流事件均使用同一服务端权限过滤；禁止先全量返回再由前端过滤。
- 群历史中的文字只是消息内容，不作为 Studio 管理指令执行。

## 5. 当前可复用能力与需要补齐的能力

基于当前仓库代码核对：

| 能力 | 现状 | 实现工作 |
|---|---|---|
| 网页聊天 | Studio 已有 `useChat`、Composer、MessageList，Server 代理 Bot 流式接口 | 复用组件与请求生命周期，增加独立入口 |
| 网页历史 | Studio 当前读取 OpenViking Session 与归档 | 复用持久历史，避免另建重复会话 |
| Bot 历史 | Bot SessionManager 持久化并可列举；OpenAPI `/sessions` 使用运行时内存索引 | 新增持久化的统一会话索引和权限过滤 |
| @识别 | 当前基于 `bot_name` 匹配 mention 名称 | 改为机器人稳定身份匹配，兼容已配置名称 |
| 渠道生命周期 | 配置加载与启动已有；文档要求修改配置后重启 | 新增单渠道受控应用配置、替换、暂停、恢复与回滚 |
| 运行状态 | `_running` 与启动日志不能证明连接和消息收发正常 | 增加实际连接、入站、出站的独立状态与时间戳 |

## 6. 建议接口与数据契约

以下均为拟新增能力，不代表现有 API 已提供。Studio 统一访问 OpenViking Server，由 Server 进行鉴权并调用受管 Bot。

| 接口 | 用途 |
|---|---|
| `GET /bot/v1/capabilities` | 当前用户权限、Bot 状态、支持的渠道与管理能力 |
| `GET /bot/v1/conversations` | 按来源、关键词及游标列出有权限的持久会话 |
| `GET /bot/v1/conversations/{id}/messages` | 分页读取统一时间线 |
| 当前管理接口 | 以本文“接口范围与复用依据”的表格为准；不存在独立的 validate/apply/status HTTP 接口。 |

网页发送继续复用现有 chat/stream 接口；统一 conversation ID 必须能映射到原 Session ID。IM 会话不提供网页发送接口。

Conversation 索引保存：权限作用域、来源、连接、原始会话引用、群/话题显示信息、最近活动时间。原始身份标识仅服务端保存。历史正文沿用现有存储，索引不复制两份消息；同一 Bot 会话关联的 OpenViking 会话必须去重映射。

历史消息区分 generated、send_failed、sent 等状态；不能把模型输出视为已发送。旧历史缺少发送证据时标注“发送状态未知”。已有会话迁移时不能推测拥有者；无法确定权限归属的记录暂不对普通用户开放。

连接使用 draft、connecting、connected、degraded、paused、error 等运行状态；配置验证、群内测试另设独立结果。刷新页面和服务重启不丢失引导步骤，但运行状态须重新探测。

首期管理能力限定为 Server 受管 Bot。外置 Gateway 未实现管理协议时显示“当前部署暂不支持在 Studio 配置渠道”，仍可使用已授权的网页聊天，并提供配置文件说明；不显示注定失败的表单。

密钥只在写请求中提交，响应、日志及诊断导出均不回显。沿用服务端配置位置，采用严格文件权限、原子写入与版本校验，保留不相关配置。只读配置部署返回明确原因与管理员操作指引。

## 7. 实施顺序与验收

第一阶段：独立入口和网页闭环。复用聊天组件、完成可持久的会话索引与身份契约。验证首条发送失败可恢复、切换无串话、重启后历史可读、多身份隔离。

第二阶段：IM provider 向导和连接管理。完成配置草稿、凭证校验、单渠道应用、身份匹配、真实连接状态、群内验证码收发。验证错误密钥、未发布、未订阅、断网、重复事件、配置失败回滚与刷新续接。

第三阶段：IM 历史与完整验收。展示群名、成员名、话题、附件占位、回复结果；新增其他 IM 开发中卡片。通过真实 IM 群完成一次正常 @问答，核对 Studio 历史和平台回复一致。

首期发布必须同时满足：

1. 新用户能从服务未启用状态沿引导走到一次网页成功对话。
2. 有可用 provider 时，管理员可从零完成 IM 应用连接、入群和真实问答；中断后可继续。
3. 改名后的机器人仍可正确识别 @；普通群与不同话题不串上下文。
4. 页面重载及 Bot 重启后历史和配置仍可恢复；无内存索引依赖导致的历史消失。
5. 群消息发送失败不会显示成功；凭证正确不会直接显示“接入完成”。
6. 无权限用户无法通过接口枚举群历史或读取密钥；群问答无法读取管理员私人记忆。
7. 其他渠道清楚显示“Studio 接入管理开发中”，不提供虚假可用入口。

## 8. 依据

- 仓库：`web-studio/src/lib/sessions/api.ts`、`web-studio/src/routes/playground/-components/agent-panel.tsx`。
- 仓库：`bot/vikingbot/channels/openapi.py`、`bot/vikingbot/session/manager.py`、`openviking/server/routers/bot.py`。
- 仓库：`bot/vikingbot/channels/manager.py`、`bot/vikingbot/config/schema.py`、`bot/docs/zh/concepts/05-channel.md`。


## 多 IM 目录边界

- `bot/vikingbot/studio/service.py`：账号隔离、持久化、版本冲突和连接生命周期。
- `bot/vikingbot/studio/providers/registry.py`：按连接 `type` 选择平台适配器；未知类型拒绝接入。
- `web-studio/src/routes/vikingbot/-providers/registry.ts`：注册各平台的引导和凭证组件。
- 公共会话、历史记录和渠道列表保留在 `-components/`。

新增 Slack 等平台时，新增对应 provider 目录并注册，复用连接生命周期和历史存储。平台特有权限、扫码或 OAuth 状态不进入公共服务。每个 provider 目录负责平台凭证校验、引导动作、消息接收和连接协议。当前仅注册 Telegram provider，其他平台保持“开发中”。
