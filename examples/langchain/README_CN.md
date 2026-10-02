# langchain-openviking

`langchain-openviking` 是 Business Data Platform 官方維護的 LangChain 和 LangGraph
整合包。框架適配邏輯不再依賴 Business Data Platform 服務端實現，遠端訪問統一通過輕量的
`openviking-sdk` 完成。

> **Business Data Platform Server 要求**：文件中的示例使用 `viking://~` Home 別名（例如 `viking://~/memories`），Server 會將其展開為當前呼叫方自己的使用者空間，因此需要一個支援 `viking://~` 的 Server。不帶 uid 的 `viking://user/memories` 舊寫法會被新版 Server 拒絕；要訪問其他使用者請顯式傳入 `viking://user/<uid>/...`。

## 安裝

LangChain Retriever、Tools、Message History 和 Context Wrapper：

```bash
pip install langchain-openviking
```

LangGraph Store 和 Middleware：

```bash
pip install "langchain-openviking[langgraph]"
```

## 快速開始

```python
from langchain_openviking import OpenVikingRetriever
from openviking_sdk import SyncHTTPClient

client = SyncHTTPClient(
    url="http://127.0.0.1:1933",
    api_key="your-user-api-key",
)
client.initialize()
retriever = OpenVikingRetriever(
    client=client,
    target_uri="viking://~/memories",
)

try:
    documents = retriever.invoke("需要記住哪些部署偏好？")
finally:
    client.close()
```

外部傳入的 client 仍由呼叫方管理。通過 `url=` 建立的 client 由介面卡管理。

完整 `openviking` 包會繼續保留原有的
`openviking.integrations.langchain` 匯入路徑，並轉發到本包，方便現有應用平滑遷移。
