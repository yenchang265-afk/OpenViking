# LangChain 和 LangGraph

把 Business Data Platform 接入你的 LangChain 或 LangGraph Agent 作為上下文後端。獨立整合包提供
retriever、chat history、context wrapper、agent tools、LangGraph store 和 middleware，
統一連線 Business Data Platform HTTP 服務。

## 安裝

```bash
pip install langchain-openviking                 # LangChain 介面卡
pip install "langchain-openviking[langgraph]"    # LangGraph middleware
```

該整合獨立於 Business Data Platform server 釋出。為相容現有應用，完整包仍會把舊的
`openviking.integrations.langchain` 匯入路徑轉發到 `langchain-openviking`。

## 連線

```python
from langchain_openviking import create_openviking_tools

tools = create_openviking_tools(
    url="http://localhost:1933",
    api_key="...",
    profile="agent",
)
```

省略 `url` 時，介面卡會使用 Business Data Platform CLI 配置中的 HTTP 連線資訊。Embedding 和 VLM
在 Business Data Platform 側配置，不在你的應用中。

### 非同步應用

Retriever、context wrapper、chat history、session recorder 和 LangGraph
middleware 都支援原生非同步路徑。通過 URL 配置時，介面卡會自動建立非同步 Business Data Platform HTTP
client：

```python
docs = await retriever.ainvoke("使用者之前做了什麼決定？")
result = await chain.ainvoke(
    {"messages": [...]},
    config={"configurable": {"session_id": "support-thread-1"}},
)
```

非同步介面卡支援兩種 client 模式：

| 配置 | 非同步介面 | 所有權 |
|------|----------|--------|
| `client=` 或 `async_client=` | 原樣返回注入的 client | 呼叫方 |
| `url=`，或省略 | 每個 event loop 一個支援恢復的 HTTP handle | Adapter |

長期執行的應用可以初始化一個由呼叫方管理的非同步 client，並在同一 event loop
內的多個介面卡之間複用：

```python
from openviking_sdk import AsyncHTTPClient
from langchain_openviking import OpenVikingRetriever

client = AsyncHTTPClient(url="http://localhost:1933", api_key="...")
await client.initialize()
try:
    retriever = OpenVikingRetriever(async_client=client)
    docs = await retriever.ainvoke("部署決定")
finally:
    await client.close()
```

注入的非同步 client 會繫結到初始化它的 event loop。不要跨 event loop 共享同一個
注入非同步 client；應為每個 loop 分別建立並管理 client。注入的同步 client 仍可安全地
用於非同步 adapter 方法，因為呼叫會在 worker thread 中執行。

`OpenVikingChatMessageHistory` 提供 `aget_messages()`、`aadd_messages()` 和
`aclear()`；`OpenVikingSessionRecorder` 提供 `arecord()`、`aflush()` 和
`aclose()`。非同步 LangGraph 執行會自動選擇 `awrap_model_call()` 和
`aafter_agent()`。同一 adapter 首次被併發呼叫時，每個 event loop 只會建立一個內部
HTTP client。通過 `with_openviking_context()` 執行的每次 runnable 呼叫都獨立持有
本次寫入所需的 history 快照、peer 身份和召回上下文引用。因此，同一 session 的呼叫
可以併發執行，不會因為
退出時再次讀取即時 history 而丟失訊息；未消費完的 stream 也不會佔用 session 級
lifecycle lock。只有最終的 append-and-commit 步驟會被序列化：async 寫入在每個
event loop 內按 session 序列執行，sync 寫入則會跨執行緒按 session 序列執行。

如果 recorder 已確認部分寫入後任務被取消，`arecord()` 會重新丟擲原始
`asyncio.CancelledError`。可將該異常或外層的 `asyncio.TimeoutError` 傳給
`get_openviking_cancellation_progress()`，在重試前讀取已確認寫入的訊息字首或待
commit 狀態，避免重複寫入。保留原始取消異常也會保留 `asyncio.wait_for()` 和
`asyncio.timeout()` 的標準超時行為。

Adapter 不會關閉呼叫方注入的 client。對於 adapter 自行建立的 client，應按實際使用的元件呼叫
`await retriever.aclose()`、`await assembler.aclose()`、
`await middleware.aclose()`、`await history.aclose()` 或
`await recorder.aclose()`。如果 async 操作完成後誤呼叫同步
`recorder.close()`，該方法會丟擲異常並保持 recorder 可用，以便後續
`await recorder.aclose()` 仍能釋放全部資源。
如果條件允許，應在關閉 event loop 前關閉 HTTP-backed adapter；原始 loop 已結束後的
清理屬於 best-effort。

`with_openviking_context()` 返回 `OpenVikingContextRunnable`。它兼容 LangChain 的
`RunnableWithMessageHistory`，並負責管理其建立的 context 和 recording adapter。
它會在多次呼叫之間複用按 event loop 隔離的 client，同時繼續隔離每次呼叫的 history、
peer 身份和召回引用。推薦使用託管生命週期：

```python
async with with_openviking_context(runnable, url="http://localhost:1933") as chain:
    result = await chain.ainvoke(
        {"messages": [...]},
        config={"configurable": {"session_id": "support-thread-1"}},
    )
```

同步呼叫使用 `with ...`，也可以顯式呼叫 `close()` 或 `await aclose()`。不要在正在執行的
event loop 中呼叫 `close()`，此時應使用 `aclose()`。注入的 client 仍由呼叫方管理。

LCEL 組合會返回普通的 `RunnableSequence`，不會暴露 Business Data Platform 的 close 方法。應保留
託管 wrapper，並在其生命週期內完成組合：

```python
async with with_openviking_context(runnable, url="http://localhost:1933") as managed:
    chain = managed | another_step
    result = await chain.ainvoke(...)
```

## Peer 身份

傳入 `actor_peer_id` 可以在檔案系統和檢索操作中過濾當前使用者的 peer 集合。session message capture 仍可使用 `peer_id` 表達每條訊息的說話人歸屬。

```python
retriever = OpenVikingRetriever(
    url="http://localhost:1933",
    actor_peer_id="assistant-a",
)

chain = with_openviking_context(
    runnable,
    session_id="support-thread-1",
    actor_peer_id="assistant-a",
)
```

動態執行時，`with_openviking_context()` 預設仍會讀取 `config["configurable"]["peer_id"]`，用於 captured message 的歸屬：

```python
chain.invoke(
    {"messages": [...]},
    config={"configurable": {"session_id": "support-thread-1", "peer_id": "assistant-a"}},
)
```

### 併發 Agent 的執行時 Actor Peer

`OpenVikingContextMiddleware` 可以在複用繫結憑證的 HTTP client 時，從每次
LangGraph 執行中解析當前 actor peer：

```python
from langchain_openviking import OpenVikingContextMiddleware


def resolve_actor_peer(_state, runtime):
    context = runtime.context or {}
    return context.get("actor_peer_id")


middleware = OpenVikingContextMiddleware(
    url="http://localhost:1933",
    api_key="user-api-key",
    actor_peer_resolver=resolve_actor_peer,
)
```

解析出的 actor peer 會作用於召回和捕獲期間發出的 Business Data Platform HTTP 請求。併發執行
互相隔離，middleware 的捕獲進度也會按 actor peer、session 和 message peer 共同
隔離。Business Data Platform 的 Session 介面仍然以 user 為作用域，不會使用 actor-peer header
標記訊息歸屬；如果捕獲的訊息也需要歸屬於同一個邏輯 peer，應同時設定
`peer_id_resolver`。擁有獨立歷史的不同 peer 也應解析為不同的 session ID。未傳入
`actor_peer_resolver` 時，現有固定 client 行為保持不變。

該 resolver 不能改變 Business Data Platform account 或 user；這些身份繼續由 API Key 或 OAuth
憑證決定。因此，多使用者應用必須先選擇繫結對應使用者憑證的 client，再呼叫 middleware。
Actor peer 只能從已經認證、由服務端控制的 runtime 欄位中解析；不要信任 model state
或客戶端可控的 configurable 值。執行時 actor-peer 解析僅支援 HTTP-backed
middleware。注入的自定義 client 必須設定
`supports_request_actor_peer = True`，並遵循 `openviking_sdk` 的 actor-peer
作用域。在已有環境中啟用該能力前，應同時升級 `openviking-sdk` 和 `openviking`。

## 選哪個介面卡？

| 我想… | 用這個 |
|-------|--------|
| 為 RAG 檢索相關上下文 | `OpenVikingRetriever` |
| 包裝 runnable，自動召回 + 捕獲 + 按策略 commit | `with_openviking_context()` |
| 給 agent 暴露顯式記憶工具 | `create_openviking_tools()` |
| 儲存跨執行緒的持久化狀態 | `OpenVikingStore` |
| 在 LangGraph 中以 middleware 注入上下文 | `OpenVikingContextMiddleware` |
| 用 Business Data Platform 儲存 LangChain 聊天記錄 | `OpenVikingChatMessageHistory` |
| 在自定義生命週期中記錄呼叫方選定的 LangChain 訊息 | `OpenVikingSessionRecorder` |

## 快速示例

### Retriever

```python
from langchain_openviking import OpenVikingRetriever

retriever = OpenVikingRetriever(url="http://localhost:1933", api_key="...")
docs = retriever.invoke("使用者之前對部署方案做了什麼決定？")
```

### Context backend

```python
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from langchain_openviking import with_openviking_context

with with_openviking_context(
    RunnableLambda(lambda msgs: AIMessage(content="...")),
    url="http://localhost:1933",
    api_key="...",
) as chain:
    result = chain.invoke(...)
```

### Agent tools

```python
from langchain_openviking import create_openviking_tools

tools = create_openviking_tools(url="http://localhost:1933", profile="agent")
# 包括：viking_find, viking_search, viking_browse, viking_read,
#       viking_grep, viking_store, viking_add_resource 等
```

### LangGraph store

```python
from langchain_openviking import OpenVikingStore

store = OpenVikingStore(url="http://localhost:1933", api_key="...")
store.put(("users", "ada"), "preferences", {"color": "azure"})
items = store.search(("users",), query="azure", limit=3)
```

### LangGraph middleware

```python
from langchain_openviking import OpenVikingContextMiddleware

middleware = OpenVikingContextMiddleware(
    url="http://localhost:1933",
    api_key="...",
    capture_on_after_agent=True,
)
```

### Session recorder

當應用已經自行管理會話生命週期，只需要複用 Business Data Platform 持久化能力時，可使用 recorder：

```python
from langchain_openviking import (
    OpenVikingPartialWriteError,
    OpenVikingSessionRecorder,
)

recorder = OpenVikingSessionRecorder(url="http://localhost:1933", api_key="...")
try:
    recorder.record("support-thread-1", messages, peer_id="assistant-a")
except OpenVikingPartialWriteError as exc:
    recorder.record(
        "support-thread-1",
        messages[exc.input_messages_consumed :],
        peer_id="assistant-a",
    )
recorder.flush("support-thread-1")
recorder.close()
```

`record()` 只寫入呼叫方傳入的訊息；它會過濾框架控制訊息、按服務端限制分批寫入，並應用已配置的
commit 策略。如果後續批次或寫入後的 commit 失敗，`OpenVikingPartialWriteError` 會報告已經
確認寫入的輸入字首，呼叫方可僅重試尚未寫入的字尾；空字尾會安全地重試待完成的 commit。
傳入 `context_parts` 時，僅在 `exc.context_attached` 為 false 時重傳。`flush()` 僅在 session
存在待提交內容時強制 commit。`close()` 後 recorder 不可複用；由呼叫方注入的 client
仍歸呼叫方管理。

非同步生命週期使用對應的 `await recorder.arecord(...)`、
`await recorder.aflush(...)` 和 `await recorder.aclose()`。不要用
`recorder.close()` 結束非同步生命週期。

## 執行示例

倉庫內提供了可直接執行的最小示例，使用記憶體測試客戶端，無需模型憑證：

```bash
uv run --project examples/langchain --extra langgraph python examples/langchain-langgraph/langchain/rag/quick_app.py
uv run --project examples/langchain --extra langgraph python examples/langchain-langgraph/langchain/context-backend/quick_app.py
uv run --project examples/langchain --extra langgraph python examples/langchain-langgraph/langchain/message-history/quick_app.py
uv run --project examples/langchain --extra langgraph python examples/langchain-langgraph/langgraph/agent/quick_app.py
uv run --project examples/langchain --extra langgraph python examples/langchain-langgraph/langgraph/middleware/quick_app.py
```

連線真實 Business Data Platform 服務和 OpenAI 相容模型的示例見 [live LangGraph app](https://github.com/volcengine/OpenViking/blob/main/examples/langchain-langgraph/langgraph/agent/live_app.py)。

## 參見

- [整合能力參考](./16-capability-reference.md)
- [examples/langchain-langgraph/](https://github.com/volcengine/OpenViking/tree/main/examples/langchain-langgraph) — 上面所有示例的完整原始碼
- [MCP 客戶端](./06-mcp-clients.md) — 非 SDK 方式的 MCP 整合
