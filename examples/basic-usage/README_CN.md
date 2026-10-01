# 基礎使用示例：OpenViking Python SDK

這個示例的目標很明確：用最短路徑帶你理解 OpenViking Python SDK 的核心工作流。
你會從初始化客戶端開始，完成資源匯入、`viking://` 檔案系統瀏覽、上下文檢索，
以及建立一個後續可以提交為長期記憶的會話。

它是一個典型的 SDK 入門示例。如果你要做生產部署、共享服務或者 MCP 整合，
請把它當作基礎，然後繼續看下方連結到的服務端和 MCP 文件。

## 這個示例覆蓋什麼

- HTTP SDK 用法
- 從遠端 URL 匯入資源
- 使用 `ls`、`tree`、`read` 瀏覽 `viking://` 檔案系統
- 使用 `find`、`abstract`、`overview`、`grep` 做檢索和載入
- 建立 session 並追加訊息，為後續記憶提取做準備

## 先選對接入方式

目前 OpenViking 常見有兩種接入路徑：

| 模式 | 適合場景 | 是否推薦 |
|------|----------|----------|
| HTTP 服務端 + SDK/CLI | 共享服務、多會話、多 Agent | 是，正式使用優先 |
| MCP | Claude Code、Cursor、Claude Desktop、OpenClaw 等 MCP 宿主 | 是，工具化整合優先 |

如果你是給 Claude Code、Cursor 這類客戶端接入，請直接看 [MCP 整合指南](../../docs/zh/guides/06-mcp-integration.md)。

## 前置條件

1. Python 3.10+
2. 安裝 OpenViking：

```bash
pip install openviking-sdk --upgrade
```

3. 啟動 OpenViking Server

## 快速開始

### 1. 執行示例指令碼

```bash
git clone https://github.com/volcengine/OpenViking.git
cd OpenViking/examples/basic-usage
python basic_usage.py
```

指令碼預設連線本地 OpenViking Server：

```python
from openviking_sdk import SyncHTTPClient

client = SyncHTTPClient(url="http://localhost:1933")
client.initialize()
```

服務端的推薦啟動方式見 [快速開始：服務端模式](../../docs/zh/getting-started/03-quickstart-server.md)。

### 2. 指令碼演示了什麼

`basic_usage.py` 基本覆蓋了大多數應用的第一條鏈路：

1. 初始化客戶端並檢查健康狀態。
2. 從 URL 新增一個資源。
3. 檢視生成的 `viking://resources/...` 樹。
4. 等待語義處理完成。
5. 用 `abstract`、`overview`、`read` 載入 L0/L1/L2 上下文。
6. 用 `find` 做語義檢索。
7. 用 `grep` 做字面內容檢索。
8. 建立 session 並追加訊息，為記憶提取做準備。

## 程式碼說明

### 初始化

使用 HTTP 客戶端連線 OpenViking Server：

```python
from openviking_sdk import SyncHTTPClient

client = SyncHTTPClient(url="http://localhost:1933")
client.initialize()
```

如果服務端啟用了認證，普通資料訪問請優先使用 `user_key`：

```python
client = SyncHTTPClient(
    url="http://localhost:1933",
    api_key="<user-key>",
)
```

`root_key` 主要用於管理操作。它不能直接呼叫 `add_resource`、`find`、`ls` 這類租戶級 API，
除非同時顯式傳入 `account` 和 `user`。詳見
[認證文件](../../docs/zh/guides/04-authentication.md) 和
[快速開始：服務端模式](../../docs/zh/getting-started/03-quickstart-server.md)。

### 新增資源

你可以新增 URL、本地檔案、目錄：

```python
result = client.add_resource(
    path="https://example.com/docs",
)

result = client.add_resource(path="/path/to/manual.pdf")

result = client.add_resource(
    path="/path/to/repo",
    options={"instruction": "這是一個 Python Web 應用"},
)
```

匯入預設返回 `task_id`。通過 `client.get_task(result["task_id"])` 查詢狀態，只有任務為 `completed` 時才讀取摘要或檢索本次匯入的內容。輪詢示例見 [後臺任務](../../docs/zh/api/17-tasks.md)。

### 檔案系統訪問

OpenViking 的上下文統一組織在虛擬檔案系統裡：

```python
files = client.ls(uri="viking://resources/")
tree = client.tree(uri="viking://resources/my-project", level_limit=3)
content = client.read(uri="viking://resources/my-project/README.md")
```

同樣的 URI 模型也適用於記憶和技能：

- `viking://resources/`
- `viking://~/memories/`
- `viking://~/skills/`

### 檢索

`find` 適合快速語義檢索，`search` 適合更復雜的進階檢索：

```python
results = client.find(
    query="認證邏輯是怎麼做的",
    options={"target_uri": "viking://resources/my-project", "limit": 5},
)

results = client.search(
    query="資料庫配置和故障處理",
    options={"target_uri": "viking://resources/", "limit": 10},
)
```

檢索命中後，再按需做分層載入：

```python
uri = "viking://resources/my-project/docs/api.md"

abstract = client.abstract(uri=uri)
overview = client.overview(uri=uri)
content = client.read(uri=uri)
```

如果你要的是字面匹配而不是語義檢索，用 `grep`：

```python
result = client.grep(
    uri="viking://resources/my-project",
    pattern="Agent",
    case_insensitive=True,
)
matches = result.get("matches", [])
```

### Session 與長期記憶

示例指令碼會建立一個 session 並追加訊息：

```python
session_info = client.create_session()
session_id = session_info["session_id"]

client.add_message(
    session_id=session_id,
    role="user",
    content="我更喜歡 TypeScript 而不是 JavaScript",
)
client.add_message(
    session_id=session_id,
    role="assistant",
    content="明白了，在合適場景下我會優先使用 TypeScript。",
)
```

如果要把這段對話真正提取成長期記憶，需要提交 session：

```python
client.commit_session(session_id=session_id)
```

提交後，記憶可以通過正常檢索介面再次找回：

```python
memories = client.find(
    query="使用者程式設計偏好",
    target_uri="viking://~/memories/",
)
```

## 配置說明

建立 `~/.openviking/ov.conf`，至少需要儲存、Embedding、VLM 配置。一個最小本地配置示例如下：

```json
{
  "server": { "host": "127.0.0.1", "port": 1933 },
  "storage": {
    "workspace": "~/.openviking/data"
  },
  "embedding": {
    "dense": {
      "provider": "openai",
      "api_key": "your-api-key",
      "model": "text-embedding-3-large",
      "dimension": 3072
    }
  },
  "vlm": {
    "provider": "openai",
    "api_key": "your-api-key",
    "model": "gpt-4o"
  }
}
```

你也可以使用火山引擎、Azure OpenAI 等提供商。當前配置示例請以主 [README](../../README_CN.md) 和 [配置指南](../../docs/zh/guides/01-configuration.md) 為準。

## 推薦下一步

- [配置指南](../../docs/zh/guides/01-configuration.md)：先確認當前配置模型，再過渡到共享部署。
- [快速開始：服務端模式](../../docs/zh/getting-started/03-quickstart-server.md)：正確啟動 `openviking-server`。
- [MCP 集成指南](../../docs/zh/guides/06-mcp-integration.md)：接入 Claude Code、Cursor、Claude Desktop、OpenClaw 等 MCP 宿主。
- [Claude Code 記憶外掛](../claude-code-memory-plugin/README.md)：在 Claude Code 中使用 OpenViking 長期記憶。
- [OpenCode 外掛](../opencode-plugin/INSTALL-ZH.md)：在 OpenCode 中使用 OpenViking 倉庫上下文與記憶工具。
- [OpenClaw 外掛](../openclaw-plugin/README_CN.md)：與 OpenClaw 整合。

## 常見問題

| 問題 | 排查方向 |
|------|----------|
| `ImportError` 或本地擴充問題 | 重新安裝 `openviking`；如果是原始碼開發，確認本地構建依賴齊全。 |
| HTTP 模式下 `Connection refused` | 啟動 `openviking-server`，並檢查 `http://localhost:1933/health`。 |
| 租戶或認證報錯 | 普通資料介面優先使用 `user_key`；`root_key` 僅在顯式傳入租戶資訊時使用。 |
| 剛匯入後檢索慢或搜不到 | 查詢本次匯入的 `task_id`，確認任務狀態為 `completed` 後再檢索。 |
| 多個客戶端或會話爭用本地儲存 | 不要反覆起獨立本地程序，改用 HTTP 服務端模式。 |

## 許可證

Apache License 2.0
