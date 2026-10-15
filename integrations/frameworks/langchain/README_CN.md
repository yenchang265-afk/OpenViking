# langchain-openviking

`langchain-openviking` 是 OpenViking 官方維護的 LangChain 和 LangGraph
整合包。框架適配邏輯不再依賴 OpenViking 服務端實現，遠端訪問統一通過輕量的
`openviking-sdk` 完成。

> **OpenViking Server 要求**：文件中的示例使用 `viking://~` Home 別名（例如 `viking://~/memories`），Server 會將其展開為當前呼叫方自己的使用者空間，因此需要一個支援 `viking://~` 的 Server。不帶 uid 的 `viking://user/memories` 舊寫法會被新版 Server 拒絕；要訪問其他使用者請顯式傳入 `viking://user/<uid>/...`。

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

## 匯入遷移

從 v0.5.0 之後的下一個服務端版本開始，舊的 `openviking.integrations.langchain`
名稱空間將移除，不提供相容轉發模組；v0.5.0 仍保留該路徑。
請安裝獨立包，並改用 `langchain_openviking` 匯入，
詳見[未釋出版本的遷移說明](https://github.com/volcengine/OpenViking/blob/main/docs/zh/about/02-changelog.md#未釋出)。

```python
from langchain_openviking import OpenVikingRetriever
```

參見[示例](https://github.com/volcengine/OpenViking/tree/main/integrations/frameworks/langchain/examples)和[框架適配指南](https://github.com/volcengine/OpenViking/blob/main/integrations/frameworks/README.md)。

## 驗證

在倉庫根目錄執行：

```bash
pip install -e 'integrations/frameworks/langchain[langgraph,test,dev]'
python -m pytest -q --noconftest -o addopts='' \
  integrations/frameworks/langchain/tests tests/unit/test_langchain_package_boundary.py
```

包後設資料和原始碼宣告 AGPL-3.0，詳見 [LICENSE](https://github.com/volcengine/OpenViking/blob/main/integrations/frameworks/langchain/LICENSE)。
可執行[示例](https://github.com/volcengine/OpenViking/blob/main/integrations/frameworks/langchain/examples/LICENSE)保留 Apache-2.0 許可。
