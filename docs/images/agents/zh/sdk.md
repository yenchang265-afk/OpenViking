## 步驟 1：安裝 Python SDK
在執行程式碼的 Python 環境中安裝獨立 SDK：

```bash
python -m pip install --upgrade openviking-sdk
```

## 步驟 2 初始化客戶端
使用當前服務地址和 API Key 建立客戶端，後續步驟複用該客戶端：

```python
from openviking_sdk import SyncHTTPClient, TextPart

url = "{{OPENVIKING_BASE_URL}}"
api_key = "{{OPENVIKING_API_KEY}}"

client = SyncHTTPClient(
    url=url,
    api_key=api_key,
    timeout=120.0,
)
client.initialize()
```


## 步驟 3：寫入資源
將本地檔案路徑和目標 URI 替換為實際值。`to` 是完整目標 URI，請使用尚未佔用的路徑：

```python
file_path = "[TODO]your-file-path"
resource_to = "[TODO]your-resource-path" # e.g. viking://resources/my-document
reason = "[TODO]your-reason" # e.g. External API documentation

# Reuse the initialized client.
result = client.add_resource(
    path=file_path,
    to=resource_to,
    options={"reason": reason},
)
```

## 步驟 4：寫入記憶
建立會話、寫入訊息，再提交記憶提取任務：

```python
text = "[TODO]your-message-text" # e.g. I am a developer

# Reuse the initialized client.
session = client.create_session()
session_id = session["session_id"]
client.add_message(
    session_id=session_id,
    role="user",
    parts=[TextPart(text=text)],
)
result = client.commit_session(session_id=session_id)
```

資源匯入和記憶提取都在後臺處理。響應包含 `task_id` 時，儲存它並用 `client.get_task(result["task_id"])` 查詢；無待處理內容的 commit 可能不返回任務。等待 `completed` 後再檢查結果，遇到 `failed` 或 `cancelled` 時先處理任務錯誤。用完後呼叫 `client.close()`。
