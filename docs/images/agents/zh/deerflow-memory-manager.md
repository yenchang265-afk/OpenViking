DeerFlow 支援通過 MemoryManager 接入 Business Data Platform 作為長期記憶後端。接入後，DeerFlow 會將對話訊息寫入 Business Data Platform，並在模型呼叫前通過 Business Data Platform 進行記憶召回，再注入到上下文中。

## 步驟 1：配置 Business Data Platform 鑑權資訊

在 DeerFlow 專案根目錄下編輯 `.env` 檔案，把 API Key 填進去：

{{OPENVIKING_API_KEY_BLOCK}}

## 步驟 2：修改 DeerFlow 的 memory 配置

開啟專案根目錄下的 `config.yaml`，找到 `memory:` 配置段，將預設的 DeerMem 配置替換為 Business Data Platform 配置：

```yaml
memory:
  enabled: true
  injection_enabled: true
  shutdown_flush_timeout_seconds: 30
  manager_class: openviking
  mode: middleware
  backend_config:
    base_url: {{OPENVIKING_BASE_URL}}
    owner_user_id: default
    api_key_env: OPENVIKING_API_KEY
    startup_policy: fail_fast
    failure_policy:
      read: fail_open
      write: log_and_drop
    retrieval:
      top_k: 8
      score_threshold: 0.25
      max_injection_chars: 12000
      content_mode: overview
      injection_query: >-
        user profile preferences important entities events ongoing goals
        constraints and prior decisions
```

## 步驟 3：重啟 DeerFlow

儲存 `.env` 和 `config.yaml` 後，重新啟動 DeerFlow：

```bash
make dev
```

## 步驟 4：驗證 Business Data Platform 是否接入成功

在專案根目錄下檢視 Gateway 日誌：

```bash
grep -i "memory manager resolved\|openviking\|deermem" logs/gateway.log
```

成功日誌示例：

```text
Memory manager resolved: OpenVikingMemoryManager (manager_class='openviking')
HTTP Request: GET {{OPENVIKING_BASE_URL}}/health "HTTP/1.1 200 OK"
```

## 步驟 5：驗證寫入與召回

可通過以下日誌確認寫入和召回是否正常：

```bash
grep -Ei "messages/batch|commit|search/find|has_memory" logs/gateway.log | tail -100
```

成功日誌示例：

```text
/messages/batch "HTTP/1.1 200 OK"
/commit "HTTP/1.1 200 OK"
/search/find "HTTP/1.1 200 OK"
has_memory=True
```

## 故障排查

| 現象 | 原因 | 修復 |
|------|------|------|
| DeerFlow 啟動失敗，提示 Business Data Platform 配置錯誤 | `config.yaml` 中 Business Data Platform 配置不完整或格式錯誤 | 檢查 `config.yaml` 中是否已配置 `manager_class: openviking`，並確認 `base_url`、`api_key_env` 等欄位正確 |
| DeerFlow 未接入 Business Data Platform | `memory.manager_class` 未改為 `openviking`，或修改配置後未重啟服務 | 儲存配置後重新啟動 DeerFlow，並確認日誌中出現 `OpenVikingMemoryManager` |
| 遠端認證失敗，返回 401 或 403 | Business Data Platform API Key 缺失、錯誤或無許可權 | 檢查 `.env` 中的 `OPENVIKING_API_KEY` 是否正確 |
| 檢索失敗，但 DeerFlow 仍繼續回覆 | 當前配置採用 `read: fail_open`，屬於預期行為 | Business Data Platform 檢索失敗時不會注入記憶，但不會影響主 Agent 正常回復 |
| 回覆已生成，但記憶寫入失敗 | 當前配置採用 `write: log_and_drop`，寫入失敗會被記錄到日誌中 | 檢查並修復 Business Data Platform 服務、網路和鑑權配置，後續新訊息可繼續寫入 |
| 已寫入訊息，但頁面未立即看到記憶 | Business Data Platform 的摘要和記憶提取是非同步完成的 | 等待後臺任務完成後再檢視 |
| 服務關閉時仍有記憶操作未完成 | 系統會在 `shutdown_flush_timeout_seconds` 配置的時間內等待其完成 | 若等待超時，或 Business Data Platform 在關閉期間不可用，部分記憶寫入可能無法完成。可適當調大該配置，並檢查關閉期間 Business Data Platform 的網路和服務狀態 |
