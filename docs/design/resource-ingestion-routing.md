# 添加资源后的解析路由

本文描述当前 `add_resource` 从收到资源到落盘、建索引的真实执行链。重点回答四个问题：入口在哪里分流、资源类型在哪里确定、Understanding 与 Connector 分别做什么，以及 `wait` 到底等待什么。

## 先记住五条规则

1. 对外只有一个资源添加入口：`ResourceService.add_resource`。SDK、HTTP API、MCP 最终都应调用它；Worker 不再拿后台任务冒充一次新的资源添加请求。
2. Connector 是一条独立的端到端导入链；Understanding 只是标准链里的一个 Parser 后端。
3. 普通文件只做一次 Parser 选择。选择依据是 Accessor 获取资源后冻结的 `resolved_extension`，不是临时文件名，也不会在队列消费者里重新猜；Understanding 可直接接收的原始 URL 是一个显式例外，可在 Accessor 前按配置直达 Understanding。
4. 目录、网站目录以及内部 Parser 遍历出的子文件不逐个调用 Understanding，统一留在内置 Parser 链内处理。
5. Watch 是一次新的来源刷新，会重新走提交分流，但不会创建、取消或覆盖自身的 Watch 任务。

## 总流程

```text
SDK / HTTP API / MCP
        |
        v
ResourceService.add_resource                  对外入口
        |
        v
ResourceService._submit_resource_ingestion    阶段一：对新请求选择执行方式
        |
        +-- Connector 命中且参数受支持 ------> Connector doc/add
        |                                         |
        |                                         +--> 轮询 Connector task/info
        |                                         +--> Connector 自己解析并写入资源
        |
        +-- Git && wait=false ----------------> 预检 + AddResource 队列 --> 返回 task_id
        |
        +-- HTTP 服务远程资源 && wait=false && Understanding 已启用
        |       |
        |       +-- 原始 URL 可直达 -----------> 提交 Understanding --> ExternalParse 队列
        |       |                                                        |
        |       |                                                        +--> 返回 task_id --> Worker
        |       |
        |       +-- 需要先确定本地类型 --------> Accessor 下载并识别
        |               |
        |               +-- 命中 Understanding --> 上传同一文件 --> ExternalParse 队列
        |               |                                             |
        |               |                                             +--> 返回 task_id --> Worker
        |               |
        |               +-- 未命中 ------------> 复用 LocalResource，进入当前请求标准链
        |
        +-- 其余场景（包括所有 wait=true） -----> _execute_resource_ingestion

_execute_resource_ingestion                    阶段二：执行标准链
        |
        v
ResourceProcessor.process_resource
        |
        v
UnifiedResourceProcessor
        |
        +-- 已有 understanding_response_id ----> ParserRouter --> Understanding 恢复任务
        |
        +-- 原始 URL 可直达 Understanding -----> ParserRouter --> Understanding 提交并等待
        |
        +-- 原始文本 --------------------------> 内置 ParserRegistry
        |
        +-- 路径 / URL --> AccessorRegistry.access（选择数据访问器）
                                  |
                                  v
                              LocalResource
                                  |
                                  +-- 目录 --> DirectoryParser（内置）
                                  |
                                  +-- 文件 --> ParserRouter.parse（选择 Parser，只选一次）
                                                  |
                                                  +-- 内置 ParserRegistry
                                                  +-- Understanding 上传并等待
        |
        v
     ParseResult --> TreeBuilder 落盘
        |
        v
阶段三：返回策略
        |
        +-- wait=true  --> 继续等待摘要 / 语义队列 / 向量索引后返回
        |
        +-- wait=false --> 普通标准链落盘后进入 AddResource 队列并返回

后台队列 Worker
        |
        +-- source job -----------------------> _execute_resource_ingestion(wait=true)
        |                                      使用消息中冻结的 backend / response_id / extension
        |
        +-- prepared job ---------------------> finish_prepared_resource
        |
        +-- 不再调用 add_resource，也不再重做 Connector / Git 顶层分类

WatchScheduler
        |
        +-- refresh_resource -----------------> _submit_resource_ingestion(manage_watch=false)
                                               重新获取和解析来源，但不修改 Watch 任务
```

Understanding 不受 `wait=false` 限制。`wait=true` 在当前请求内完成 Understanding 提交、轮询、解析和 TreeBuilder，并继续等待后续队列；`wait=false` 的远程服务路径会先提交 Understanding、将 `response_id` 入队，再由 Worker 恢复任务。

分类发生的位置：

| 分类内容 | 代码位置 | 输出 |
|---|---|---|
| Connector、异步 Git、标准执行链 | `ResourceService._submit_resource_ingestion` | 选定新请求的顶层执行方式 |
| 异步 Understanding 或当前请求内执行 | `ResourceService._execute_resource_ingestion` | 根据 `wait`、配置和已识别类型决定提交还是同步执行 |
| Git、Feed、HTTP、本地文件 | `AccessorRegistry.access` | `LocalResource` |
| Understanding 能否直接接收原始 URL | `ParserRouter.should_use_understanding_directly` | 直达 Understanding 或继续 Accessor |
| Understanding 与内置 Parser | `ParserRouter.parse` | `ParseResult` |

后台资源任务统一使用可恢复的 `AddResourceMsg`，但按工作类型进入两个独立队列：Understanding 使用受外部解析并发限制的 `ExternalParse`；Git 和已落盘的本地后处理使用 `AddResource`。两个队列都由 `AddResourceProcessor` 消费，锁接管失败时仍回到原队列。消息已经冻结了生产端做出的选择，例如 `parser_backend`、`understanding_response_id` 和 `resolved_extension`。Worker 直接执行该选择，不再把任务送回公开 `add_resource` 重新分类。

## 顶层路由表

| 输入或场景 | 获取数据 | 解析者 | 是否走标准 `ParseResult -> TreeBuilder` | 返回时机 |
|---|---|---|---|---|
| Connector 配置允许的 TOS 或 Git，提供精确 `to` 且参数受支持 | Connector 服务 | Connector 服务 | 否 | 提交成功立即返回 `task_id`，后台轮询状态 |
| `tos://` 但 Connector 不可用或参数不支持 | 不降级 | 不执行 | 否 | 直接报清晰的参数或配置错误 |
| Git 未命中 Connector 或无凭证回退，`wait=false` | GitAccessor 在后台 clone | 内置目录/代码仓库 Parser | 是 | 预检仓库并预占 URI 后返回 |
| Git，`wait=true` | GitAccessor | 内置目录/代码仓库 Parser | 是 | 解析、落盘及语义队列完成后返回 |
| HTTP 服务请求，`wait=false`，命中 Understanding | HTTPAccessor 识别类型并上传同一份本地文件 | Understanding | 是 | 类型识别、Understanding 提交、URI 预占和入队后返回 |
| 其他 URL、文件、目录、原始文本 | 对应 Accessor；原始文本无需 Accessor | 内置 Parser 或同步 Understanding | 是 | 至少完成解析和落盘后返回 |

Git 是 Connector 与标准链共享的来源：未命中 Connector 或参数不受支持时可回退到标准链；一旦请求带有 Connector 专用凭证则禁止回退，避免凭证进入持久化队列。`tos://` 没有标准 Accessor，不能回退，否则只会在更深处得到误导性的解析错误。

## Accessor：先把“数据在哪”变成“本地是什么”

`AccessorRegistry` 按优先级选择数据访问器，当前内置顺序是：

```text
GitAccessor (80)
WebFeedAccessor (60)
HTTPAccessor (50)
LocalAccessor (1)
```

Accessor 的产物统一是 `LocalResource`，包含本地文件或目录路径、`source_type`、原始来源、是否需要清理，以及检测元数据。标准 Parser 不再负责 clone 或下载；只有 Understanding 可直接接收的原始 URL 会在 Accessor 前被消费。

`UnifiedResourceProcessor.prepare` 随后冻结两个字段：

- `resolved_extension`：本次 Parser 路由唯一使用的扩展名。
- `resolved_name`：用于展示、默认资源命名和 Understanding 上传文件名，不参与 HTTP 资源的类型覆盖。

HTTP 资源以 HTTPAccessor 检出的 `meta.extension` 为准；本地文件或上传的临时文件可优先使用显式 `source_name` 的扩展名。这样既不会拿随机临时文件名选 Parser，也不会让用户提供的 URL 名称覆盖实际下载内容类型。

本地文件进入 Understanding 时，ParserRouter 将冻结的 `resolved_name` 和 `resolved_extension` 一起传给上传层。上传层使用来源名称的 basename；如果末尾没有已识别的扩展名（忽略大小写），则追加该扩展名，保留名称中的编号和版本信息。例如无后缀 URL `/export?id=123` 返回 `Content-Type: application/pdf` 时，上传文件名为 `export.pdf`；`2601.00014` 会补成 `2601.00014.pdf`，`report.PDF` 保持原样。内部的 MPEG-TS 路由标记转换为真实的 `.ts` 后缀。

普通上传、分片上传和 MIME 类型推断统一使用补全后的上传文件名，本地路径用于读取文件。同步解析、提前提交解析和仅上传获取 `file_id` 使用相同规则。`resource_name` 只控制外层资源目录，例如 `README.md` 下载为 `/tmp/tmpABC.md` 后，上传文件名仍为 `README.md`。

## 无后缀 URL 怎么判断类型

HTTPAccessor 按以下顺序收集和修正类型：

1. URL path 中受支持的显式扩展名。
2. HEAD 响应的 `Content-Disposition` 文件名。
3. HEAD 响应的 `Content-Type`。
4. GET 响应的 `Content-Disposition` 和 `Content-Type`，用于修正之前的模糊网页判断。
5. GET 内容的 magic bytes，例如 PDF、图片、音视频、Office/EPUB/ZIP 签名。
6. 仍无法识别时按网页处理。

最终扩展名写入 `LocalResource.meta.extension`，然后冻结为 `resolved_extension`。`ParserRouter` 只读取这个结果。URL 上已有明确扩展名时，不用 magic bytes 擅自覆盖它。

因此，`wait=false` 不等于“完全不碰源站就返回”。HTTP 服务收到无后缀远程 URL、且 Understanding 已启用时，必须先下载或探测一次，才能知道应进入外部解析队列还是内置 Parser。命中 Understanding 后，生产端直接上传这份已检测的本地文件并取得 `response_id`，然后才清理临时文件；Worker 只恢复该 response，不会重新下载可能已过期或内容已变化的 URL。

## Parser：只回答“本地内容怎么解析”

标准执行链分四类：

- 原始文本：直接进入内置 `ParserRegistry`。
- 可由 Understanding 直接接收的原始 URL：在 Accessor 前进入 `ParserRouter`。
- 本地目录：直接进入 `DirectoryParser`；Git 仓库由目录链委派给代码仓库 Parser。
- 本地文件：进入 `ParserRouter`，根据 `resolved_extension` 在内置 `ParserRegistry` 与 Understanding 之间选一次。

ParserRegistry 只注册项目内置 Parser，不再提供自定义 Parser 类、回调注册或可选模块注册入口。新增数据源优先实现 Accessor；新增文件格式则直接增加内置 Parser 和对应测试。

目录、网站和由内置 ZipParser 展开的压缩包，其“子文件遍历”仍属于当前内置
Parser 的内部实现，不回到顶层 `ResourceService`。`DirectoryParser` 会递归扫描
每个叶子文件，并通过 `ParserRouter` 重新检查 `parser_api.extensions`：命中的文件
交给 Understanding，未命中的文件继续使用内置 Parser 或直接写入。该过程在当前
目录任务内执行，不会把每个子文件拆成独立的 `ExternalParse` 队列任务。顶层压缩
文件本身是否直接进入 Understanding，仍由其冻结扩展名和
`parser_api.extensions` 决定。

启用 Understanding 目录路由后，每次 `DirectoryParser` 扫描在发起该层远程请求前执行
预检，默认限制为 1000 个入选文件和 10 层目录深度；关闭 Understanding 时，
OpenViking 原生目录解析不应用这两个限制。内置 `ZipParser` 递归展开压缩包时会创建新的
目录扫描，嵌套 ZIP 不与外层共享文件数量和深度预算。
客户端导入本地目录时，会先将整个目录压缩为 ZIP，再由
`/resources/temp_upload` 对整个 ZIP 执行上传大小限制。ZIP 解压后的叶子文件不再由
`DirectoryParser` 设置统一大小限制，而是交给对应内置 Parser 或 Understanding，遵循
各自的格式和上传限制。这些文件使用固定 worker 池，默认并发为 4；远程解析可以并发，
但向目录临时树的合并始终按扫描顺序串行执行。目录限制可通过
`parsers.directory` 配置调整。目录内部分文件失败时仍提交成功文件并通过
`meta.failed_files` 返回失败详情；嵌套 ZIP 的叶子失败使用 `bundle.zip/path/to/file`
形式的路径并保留远端任务 ID。如果没有任何文件成功，则在 TreeBuilder 持久化前
终止任务，并清理本次请求新预占的空目标目录。

## Understanding 链路

Understanding 是“外部解析器”，不是“外部落盘器”：

```text
LocalResource / 远程源
        |
        v
Understanding API
        |
        v
解析结果 ZIP
        |
        v
解压到临时 Viking 目录
        |
        v
ParseResult
        |
        v
TreeBuilder + 标准摘要/索引链
```

同步路径中，Accessor 已下载的本地文件会直接上传给 Understanding，`original_source` 只保留作来源元数据。普通 HTTP 文件的异步路径也先上传已检测文件，再通过统一的 `AddResourceMsg` 持久化 `understanding_response_id`、冻结的 `resolved_extension` 和 `parser_backend="understanding"`；Worker 直接恢复 response，既不重新下载源 URL，也不因配置变化重新选择后端。这些冻结字段是内部任务字段，公共 `args` 不能指定，避免调用方绕过外部解析开关和扩展名白名单。

Understanding 返回 ZIP 时，本地适配器会安全解压，并根据 Markdown 的相对图片引用生成受控的图片映射 sidecar。TreeBuilder 后续仍使用统一的图片 URI 改写链。

这条链的关键特征是：Understanding 只替代 Parser，后面的 `ParseResult`、URI 规划、TreeBuilder 落盘、摘要和索引仍属于 OpenViking。

## Connector 链路

Connector 是另一套端到端导入服务：

```text
ResourceService
    |
    +--> Connector doc/add
              |
              +--> Connector 获取源数据
              +--> Connector 解析
              +--> Connector 写入目标资源树
    |
    +--> 后台轮询 Connector task/info
              |
              +--> 更新 OpenViking TaskRecord
```

Connector 不返回本地 `ParseResult`，也不调用当前进程的 `TreeBuilder`。OpenViking 只负责校验这次请求能否无损委派、提交任务、返回 OpenViking `task_id`，再把 Connector 的终态同步到任务记录。

Connector 当前要求提供精确 `to`，不接受 `parent`；也不支持 `wait=true`、watch、instruction、关闭建索引、摘要、strict、include/exclude 等。无凭证的 Git 请求可回退到标准链；带 Connector 专用凭证的 Git 和 Connector-only 来源会立即报错，避免凭证落入本地持久化任务。

## `wait` 的准确含义

| 路径 | `wait=false` | `wait=true` |
|---|---|---|
| Connector | 提交外部任务后返回 | 不支持；不会假装同步等待 |
| Git | 预检并预占 URI 后启动后台标准链 | 当前请求内完成标准链并等待队列 |
| HTTP 服务 + 异步 Understanding | 先识别类型，再预占 URI、入 `ExternalParse` 后返回 | 当前请求内调用 Understanding，再等待后续队列 |
| 普通标准链 | 解析和落盘完成后返回；摘要/语义处理由任务监控 | 解析和落盘完成后继续等待语义队列 |

所以普通 `wait=false` 不是“所有工作后台化”，而是“资源树已落盘，但不阻塞等待后续语义任务”。Git 与异步 Understanding 是两个明确的例外分支。

## 目标 URI、锁和失败边界

- 需要后台执行的 Git 与普通文件 Understanding 任务会先规划并预占目标 URI，避免返回的 URI 随后台竞态变化。
- 锁通过 handoff 交给后台任务或队列 Worker；入队失败时立即释放，并把任务标为失败。
- 临时 `LocalResource` 由拥有它的调用层清理；交给标准处理器后，清理责任随之转移。
- Parser 产生 `ParseResult` 后才进入 TreeBuilder。没有临时解析产物时标准链返回解析错误；目录允许带 warnings 的部分成功，`strict` 决定是否暴露这些警告。
- Connector 的失败边界在外部任务终态，OpenViking 不对其内部文件逐个回滚。

## 代码定位

| 职责 | 入口 |
|---|---|
| 公开入口、新请求分流与内部执行 | `openviking/service/resource_service.py`：`ResourceService.add_resource`、`_submit_resource_ingestion`、`_execute_resource_ingestion` |
| Watch 刷新入口 | `openviking/service/resource_service.py`：`ResourceService.refresh_resource`；`openviking/resource/watch_scheduler.py` |
| 标准解析与落盘编排 | `openviking/utils/resource_processor.py`：`ResourceProcessor.process_resource` |
| Accessor 与 Parser 两层衔接 | `openviking/utils/media_processor.py`：`UnifiedResourceProcessor` |
| 文件 Parser 单次选择 | `openviking/parse/parser_router.py`：`ParserRouter` |
| 内置 Parser 注册 | `openviking/parse/registry.py`：`ParserRegistry` |
| HTTP 类型识别 | `openviking/parse/accessors/http_accessor.py`：`HTTPAccessor`、`URLTypeDetector` |
| Understanding 同步适配 | `openviking/parse/understanding_api.py`：`UnderstandingAPI` |
| 可恢复的后台资源消息与双队列 Worker | `openviking/storage/queuefs/add_resource_msg.py`、`add_resource_processor.py`、`queue_manager.py` |
| Connector 客户端 | `openviking/connector/client.py`：`ConnectorClient` |

## 快速自检

- 无后缀 PDF URL：HTTPAccessor 从响应头或 PDF 签名得到 `.pdf`，ParserRouter 再决定是否使用 Understanding。
- Understanding 返回结果：先转成 `ParseResult`，仍由本地 TreeBuilder 落盘。
- Connector 返回结果：只返回任务标识，不经过本地 `ParseResult`。
- 普通 Markdown 且 `wait=false`：返回前 Markdown 已解析并落盘，只是不等待后续语义队列。
- 网站抓取出的目录：进入 DirectoryParser，页面子文件不会逐个调用 Understanding。
