# openviking-sdk

OpenViking 的輕量級 Python HTTP SDK。

`openviking-sdk` 面向只需要通過 HTTP 呼叫現有 OpenViking 服務的使用者。它避免了主包 `openviking` 中較重的本地執行時、服務端和 CLI 依賴。

## 安裝

```bash
pip install openviking-sdk
```

要求：

- Python 3.8+
- 一個可訪問的 OpenViking HTTP 服務，例如 `http://127.0.0.1:1933`

## 包名與匯入名

- PyPI 包名：`openviking-sdk`
- Python 匯入名：`openviking_sdk`

```python
from openviking_sdk import AsyncHTTPClient, SyncHTTPClient
```

## 配置來源

SDK 支援三種配置方式，優先順序從高到低如下：

1. 顯式構造引數
2. 環境變數，例如 `OPENVIKING_URL`、`OPENVIKING_API_KEY`、`OPENVIKING_ACCOUNT`、`OPENVIKING_USER`、`OPENVIKING_ACTOR_PEER_ID` 和 `OPENVIKING_TIMEOUT`
3. `ovcli.conf`，來源可以是 `OPENVIKING_CLI_CONFIG_FILE` 指定的路徑，或者預設路徑 `~/.openviking/ovcli.conf`

這意味著之前依賴 `ovcli.conf` 的配置方式，在 SDK 拆分之後仍然可以繼續使用。

## 認證模型

大多數部署場景使用 API Key 認證。

常見客戶端欄位：

- `url`：OpenViking 服務的基礎 URL
- `api_key`：root key 或 user key
- `account`：可選的 account 覆蓋，通常只在使用 root key 時需要
- `user`：可選的 user 覆蓋，通常只在使用 root key 時需要
- `user_id`：`user` 的相容舊別名
- `actor_peer_id`：可選的 actor peer 覆蓋
- `agent_id`：`actor_peer_id` 的相容舊別名
- `event_hooks`：可選的 `httpx.AsyncClient` 事件鉤子，例如非同步 request 或 response hook

相容性說明：

- 舊呼叫方仍然可以使用 `user_id` 和 `agent_id`
- `actor_peer_id` 和 `agent_id` 不能同時傳入

示例：

```python
from openviking_sdk import SyncHTTPClient

client = SyncHTTPClient(
    url="http://127.0.0.1:1933",
    api_key="your-user-or-root-key",
)
```

如果你使用的是 root key，並且希望以某個租戶使用者身份執行：

```python
from openviking_sdk import SyncHTTPClient

client = SyncHTTPClient(
    url="http://127.0.0.1:1933",
    api_key="your-root-key",
    account="demo-account",
    user="demo-user",
)
```

## 請求級 Actor Peer

應用可以複用一個已經繫結憑證並完成初始化的 client，同時為每個請求選擇當前的
actor peer：

```python
from openviking_sdk import (
    SyncHTTPClient,
    use_actor_peer,
)

client = SyncHTTPClient(
    url="http://127.0.0.1:1933",
    api_key="your-user-key",
)
client.initialize()

with use_actor_peer("assistant-a"):
    memories = client.find(query="部署偏好")
```

該作用域通過 Python `ContextVar` 隔離，因此併發 async task 以及由 SDK worker loop
執行的同步呼叫不會互相覆蓋。巢狀作用域會自動恢復之前的 actor peer。

該作用域不會改變認證或租戶歸屬。Account 和 user 身份仍然由 API Key 或 OAuth
憑證決定。每個 OpenViking user 應使用各自繫結憑證的 client，actor peer 只能從應用
已經認證的狀態中解析。服務端只會在支援 actor-peer view 的介面上應用該值；Session
介面仍然以 user 為作用域。

## 快速開始：同步客戶端

```python
from openviking_sdk import SyncHTTPClient

client = SyncHTTPClient(
    url="http://127.0.0.1:1933",
    api_key="your-user-key",
)
client.initialize()

healthy = client.health()
print("health:", healthy)

session = client.create_session(session_id="demo-session")
print("session:", session)

client.session(session_id="demo-session").add_message(
    role="user",
    content="hello from sdk",
)
client.session(session_id="demo-session").add_message(
    role="assistant",
    content="hello from a specific peer",
    peer_id="peer-alice",
)
context = client.session(session_id="demo-session").get_session_context(token_budget=4096)
print("context:", context)

client.close()
```

## 快速開始：非同步客戶端

```python
import asyncio

from openviking_sdk import AsyncHTTPClient


async def main() -> None:
    client = AsyncHTTPClient(
        url="http://127.0.0.1:1933",
        api_key="your-user-key",
    )
    await client.initialize()

    healthy = await client.health()
    print("health:", healthy)

    session = await client.create_session(session_id="demo-session-async")
    print("session:", session)

    session_client = client.session(session_id="demo-session-async")
    await session_client.add_message(
        role="user",
        content="hello from async sdk",
    )
    context = await session_client.get_session_context(token_budget=4096)
    print("context:", context)

    await client.close()


asyncio.run(main())
```

## 常見操作

### 建立 Session

```python
from openviking_sdk import SyncHTTPClient

client = SyncHTTPClient(url="http://127.0.0.1:1933", api_key="your-user-key")
client.initialize()
event_config = {
    "events": {
        "tags": ["team=search", "channel=web"],
    }
}
result = client.create_session(
    session_id="demo-session",
    options={
        "memory_extraction_config": event_config,
    },
)
# 建立時顯式傳 None，可覆蓋服務端預設並停用自動提交。
client.create_session(
    session_id="manual-session",
    options={"auto_commit_policy": None},
)
client.update_session_config(
    session_id="demo-session",
    options={
        "auto_commit_policy": {"message_count_threshold": 25},
        "memory_extraction_config": {
            "events": {"tags": ["team=search", "channel=app"]}
        },
    },
)
# 顯式傳 None 會停用自動 commit；省略引數則保持不變。
client.update_session_config(
    session_id="demo-session",
    options={"auto_commit_policy": None},
)
client.session(session_id="demo-session").commit(
    options={"event_tags": ["team=search", "channel=web"]}
)
# 單次 commit 傳 event_tags=[] 可顯式跳過 session 預設 tags。
print(result)
```

### 從本地檔案新增資源

`add_resource` 預設返回 `task_id`。通過 `client.get_task(result["task_id"])` 查詢狀態，任務為 `completed` 後再使用處理結果。

`add_resource` 會自動處理本地路徑對應的檔案上傳。

```python
from openviking_sdk import SyncHTTPClient

client = SyncHTTPClient(url="http://127.0.0.1:1933", api_key="your-user-key")
client.initialize()

result = client.add_resource(
    path="/path/to/notes.md",
    to="viking://resources/demo-notes",
    options={
        "reason": "knowledge import",
    },
)
print(result)
```

如果只希望入庫並生成向量、不走 VLM 語義理解，可以傳 `processing_mode="vectors_only"`。
該模式會寫入/同步資源樹並向量化當前檔案，但不會生成或重新整理 `.abstract.md` / `.overview.md`。

```python
result = client.add_resource(
    path="/path/to/notes.md",
    to="viking://resources/demo-notes",
    options={
        "processing_mode": "vectors_only",
    },
)
```

### 檔案系統操作

```python
from openviking_sdk import SyncHTTPClient

client = SyncHTTPClient(url="http://127.0.0.1:1933", api_key="your-user-key")
client.initialize()

client.mkdir(uri="viking://resources/demo-dir")
print(client.ls(uri="viking://resources"))
print(client.read(uri="viking://resources/demo-dir/example.md"))
```

### 檢索

```python
from openviking_sdk import SyncHTTPClient

client = SyncHTTPClient(url="http://127.0.0.1:1933", api_key="your-user-key")
client.initialize()

result = client.find(query="hello", limit=5)
print(result)
```

### 高頻引數與 Options

高頻欄位使用顯式引數。為保證可讀性，推薦使用引數名，例如 `add_resource` 的
`to`、`wait`，檢索的 `target_uri`、`limit`，以及 `add_message` 的
`role`、`content`、`parts`、`peer_id`；位置引數呼叫仍然支援。批次寫入時，
請在每條訊息字典中傳入 `peer_id`。

進階欄位統一放入帶型別提示的 `options` 字典，例如 `processing_mode`、檢索
過濾條件、Session 提取配置和 `telemetry`。不要把進階欄位作為裸關鍵字引數傳入。同一個欄位
只能通過一個入口傳遞；`options` 或 `extra` 中的 SDK 已定義欄位不能覆蓋顯式引數。

圖片搜尋也使用同一組方法。通過顯式的 `image` 引數傳入本地路徑、bytes、data URI、HTTP URL 或 `viking://` URI；服務端需要使用 multimodal embedding 模型。

```python
result = client.find(query="", limit=5, image="/path/to/photo.png")
result = client.search(
    query="similar poster",
    image="viking://resources/poster.png",
)
```

複雜請求統一使用帶型別提示的 Options 字典。只有服務端已經增加、當前 SDK
版本尚未正式暴露的欄位才通過 `extra` 臨時傳遞：

```python
result = client.find(
    query="authentication",
    limit=10,
    options={"extra": {"future_server_field": False}},
)
```

## 管理員操作

如果你使用 root key 連線，SDK 也暴露了管理員 API，例如：

- `admin_create_account`
- `admin_register_user`
- `admin_list_accounts`
- `admin_list_users`
- `admin_regenerate_key`
- `admin_delete_account`

示例：

```python
from openviking_sdk import SyncHTTPClient

root_client = SyncHTTPClient(
    url="http://127.0.0.1:1933",
    api_key="your-root-key",
)
root_client.initialize()

result = root_client.admin_create_account(
    account_id="demo-account",
    admin_user_id="demo-admin",
    seed="demo-admin-seed",
)
print(result)

root_client.admin_register_user(
    account_id="demo-account",
    user_id="alice",
    role="user",
    seed="alice-seed",
    user_config={
        "add_targets": {
            "resource_uri": "viking://~/resources/project-a",
            "skill_uri": "viking://~/skills",
        }
    },
)

root_client.admin_regenerate_key(
    account_id="demo-account",
    user_id="alice",
    seed="alice-new-seed",
)
```

`admin_create_account` 也接受同樣結構的 `user_config`。這些欄位用於初始化服務端使用者配置；普通新增呼叫仍然只需省略 `to` / `parent` / `target_uri`，由服務端解析預設值。
傳入 `seed` 時，返回的 API Key 會基於 `sha256(user_id + "\0" + seed)` 生成；省略時仍使用隨機生成邏輯。

## 錯誤處理

SDK 會把服務端錯誤碼對映為 Python 異常。

```python
from openviking_sdk import OpenVikingError, SyncHTTPClient

client = SyncHTTPClient(url="http://127.0.0.1:1933", api_key="your-user-key")
client.initialize()

try:
    print(client.read(uri="viking://resources/not-exists.md"))
except OpenVikingError as exc:
    print(type(exc).__name__, exc)
```

## 與 `openviking` 的關係

在以下場景中使用 `openviking-sdk`：

- 只需要 HTTP 客戶端
- 希望依賴體積儘可能小
- 作為業務應用側整合包使用

在以下場景中使用 `openviking`：

- 需要完整 Python 主包
- 需要本地執行時整合
- 需要服務端入口
- 需要重新匯出 HTTP client 的相容匯入路徑

## 開發

從原始碼安裝：

```bash
cd sdk/python
pip install -e .
```

構建發行包：

```bash
cd sdk/python
python -m build
```

SDK 版本號來自以下格式的 git tag：

```text
python-sdk@0.1.3
```

這個 tag 名稱空間獨立於主包的釋出 tag，例如：

```text
v0.3.26
```

## 釋出

倉庫已經配置為支援通過 SDK 專用 tag 觸發 SDK 釋出。

典型流程：

1. 合併 SDK 相關改動
2. 建立並推送類似 `python-sdk@0.1.3` 的 tag
3. GitHub Actions 構建 `sdk/python`
4. GitHub Actions 將 `openviking-sdk` 釋出到 PyPI
