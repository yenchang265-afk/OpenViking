# OpenViking 健康檢查工具

`ov-healthcheck.py` 端到端驗證 OpenClaw + OpenViking 外掛鏈路。通過一次真實 Gateway 會話，再從 OpenViking 側檢查結果。

## 快速開始

```bash
python examples/openclaw-plugin/ov-healthcheck.py
```

只依賴 Python 標準庫。地址和 token 會從 `openclaw.json` 自動讀取。

## 前置要求

### 必須啟用 Gateway HTTP 端點

Phase 1 對話注入依賴 Gateway 的 `/v1/responses` 介面，該介面**預設關閉**，需要在 `openclaw.json` 中啟用：

```json
{
  "gateway": {
    "http": {
      "endpoints": {
        "chatCompletions": {
          "enabled": true
        },
        "responses": {
          "enabled": true
        }
      }
    }
  }
}
```

啟用後重啟 Gateway 使配置生效：

```bash
openclaw gateway restart
```

若未啟用，Phase 1 會失敗並報錯：

```
[FAIL] Chat turn 1 failed (POST http://127.0.0.1:18789/v1/responses failed with HTTP 404: Not Found)
```

## 期望輸出

正常執行結果如下：

```
OpenViking Plugin Healthcheck
Gateway: http://127.0.0.1:18789
OpenViking: http://127.0.0.1:1933
...

[PASS] OpenClaw config discovered (...)
[PASS] plugins.slots.contextEngine is openviking
[PASS] Gateway health check succeeded
[PASS] OpenViking health check succeeded

Phase 1: real conversation
[PASS] Chat turn 1 succeeded (reply_len=151)
[PASS] Chat turn 2 succeeded (reply_len=131)
[PASS] Chat turn 3 succeeded (reply_len=115)
[PASS] Chat turn 4 succeeded (reply_len=77)

Phase 2: OpenViking session inspection
[PASS] Probe session located in OpenViking (...)
[PASS] Captured session context contains the probe marker
[PASS] Captured session context contains seeded facts (go,postgresql,redis,70)

Phase 3: commit, context, and memory checks
[PASS] OpenViking commit accepted (accepted)
Waiting up to 300s for commit, archive, and memory extraction...
[PASS] Session commit_count is greater than zero (1)
[PASS] Memory extraction produced results (total=1)
[PASS] Context endpoint returned latest_archive_overview

Phase 4: follow-up through Gateway
[PASS] Same-session follow-up recalled earlier facts (go,postgresql,redis,70)
[PASS] Fresh-session recall returned seeded stack facts (...)

Phase 5: cleanup
[PASS] Deleted synthetic session (...)
[PASS] Deleted synthetic memory (viking://user/default/memories/...)

Summary
PASS=20 WARN=0 FAIL=0 SKIP=0

Healthcheck passed.
```

Phase 3 會等待非同步 commit 完成（預設最多 300 秒）。這是正常的——commit 涉及 LLM 呼叫來做歸檔和記憶抽取。

所有測試訊息都帶有 `[OPENVIKING-HEALTHCHECK]` 字首和唯一 probe 標記，但正文會盡量寫成正常的可記憶對話內容。Kafka topic、callback host 和 debug tag 也會從 probe 派生出唯一值，確保這次執行留下的 artifacts 可以被精確識別。指令碼預設會在結束時刪除本次執行產生的 synthetic session，以及只屬於當前 run 的 probe 專屬 leaf memory。像 `profile.md`、preferences、`.abstract.md` 這類共享摘要檔案，即使包含了 synthetic 內容也不會刪除，以避免誤刪混有真實使用者資訊的共享 memory；只有顯式傳入 `--keep-artifacts` 時才會保留這些現場用於排查。

## 工作原理

指令碼通過注入一組受控對話，再追蹤其在系統中的流轉來驗證外掛鏈路。

**Probe 標記** — 每次執行生成一個唯一隨機標記（如 `probe-a1b2c3d4`），嵌入第一條訊息中。後續通過這個標記在 OpenViking 中精確定位本次測試的 session，不會和使用者真實對話混淆。

**Phase 1：對話注入** — 指令碼通過 Gateway `/v1/responses` 介面傳送 4 條帶 probe 標記的訊息，模擬一次真實使用者對話。訊息中包含已知事實（技術棧、Kafka topic、服務地址等），作為後續驗證的錨點。`[OPENVIKING-HEALTHCHECK]` 字首和 probe 標記用於識別本次檢查，而正文保持正常對話內容，以便真實驗證記憶抽取鏈路。

**Phase 2：捕獲驗證** — 等待一小段時間（`--capture-wait`）後，指令碼查詢 OpenViking sessions API，逐個掃描 session 的 context 尋找 probe 標記。找到標記說明外掛的 `afterTurn` 鉤子成功將 Gateway 對話寫入了 OpenViking。

**Phase 3：Commit 和記憶驗證** — 指令碼通過 OpenViking API 觸發 commit，然後輪詢（最多 `--commit-wait` 秒）直到三個條件同時滿足：
- `commit_count > 0` — commit 已完成
- `latest_archive_overview` 存在 — 對話已歸檔
- `memories_extracted > 0` — 記憶抽取產生了結果

這確認了完整的非同步流水線：對話歸檔、概要生成、記憶抽取。

**Phase 4：召回驗證** — 通過 Gateway 再發兩個問題：
1. 同 session 追問，詢問之前對話中的事實。檢查回復是否包含關鍵詞（`go`、`postgresql`、`redis`、`70`）。驗證 session 內的上下文連續性。
2. 新 session 追問（使用新 user ID），詢問只有通過記憶召回才能獲得的事實。檢查回復是否包含由 probe 派生出來的本次執行專屬 Kafka topic 和 callback host。驗證 `autoRecall` 是否在新 session 中注入了儲存的記憶。

**Phase 5：清理** — 預設情況下，指令碼會刪除本次執行建立的 synthetic OpenViking session，並且只在當前 user space 下、命中本次 run 的 probe 派生事即時才刪除 synthetic memory。memory root 會按當前執行時 user space 解析。這樣連續跑 healthcheck 時，不會把共享 memory 空間越堆越髒，也不會誤刪無關記憶。

**關鍵詞匹配** — 指令碼不要求精確複述。它將模型回覆轉為小寫，檢查目標關鍵詞中是否至少命中 2 個。這容忍了模型的改寫，同時能捕捉到完全的召回失敗。

## 輸出含義

- `PASS` — 確認正常
- `INFO` — 補充資訊，不代表異常
- `WARN` — 主鏈路可用，但該項未穩定確認
- `FAIL` — 明確故障，指令碼返回非 0

## 引數

| 引數 | 預設值 | 說明 |
|------|--------|------|
| `--gateway <url>` | 自動 | Gateway 地址 |
| `--openviking <url>` | 自動 | OpenViking 地址 |
| `--token <token>` | 自動 | Gateway bearer token |
| `--openviking-api-key <key>` | 自動 | OpenViking API key |
| `--actor-peer <id>` | `main` | OpenViking 直連檢查請求使用的 actor peer |
| `--user-id <id>` | 隨機 | 測試會話的 user id |
| `--openclaw-config <path>` | 自動 | `openclaw.json` 路徑 |
| `--chat-timeout <秒>` | `120` | 每次 Gateway 聊天請求的超時 |
| `--commit-wait <秒>` | `300` | 等待 commit、歸檔、記憶抽取完成的最大時間 |
| `--capture-wait <秒>` | `4` | 聊天結束後等待 OpenViking 捕獲的時間 |
| `--delay <秒>` | `1` | 聊天輪次間隔 |
| `--session-scan-limit <n>` | `0`（全部） | 掃描 session 的上限（0 = 掃描全部） |
| `--insecure` | 關 | 跳過 SSL 證書驗證（自簽證書場景） |
| `--keep-artifacts` | 關 | 保留本次執行產生的 synthetic session 和 memory，便於除錯 |
| `--strict-warnings` | 關 | 有 WARN 時也返回非 0 |
| `--json-out <path>` | — | 輸出 JSON 報告 |
| `--verbose` / `-v` | 關 | 列印除錯資訊 |

## 故障處理

### `Gateway health check failed`

```bash
openclaw gateway status
curl http://127.0.0.1:<端口>/health
openclaw logs --follow
```

### `OpenViking health check failed`

```bash
curl http://127.0.0.1:<端口>/health
cat ~/.openviking/ov.conf
```

檢查 `storage.workspace/log/openviking.log`。

### `Chat turn 1 failed (POST /v1/responses failed with HTTP 404: Not Found)`

這是最常見的 Phase 1 失敗原因。Gateway 的 `/v1/responses` 和 `/v1/chat/completions` 介面**預設關閉**，需要在 `openclaw.json` 的 `gateway.http.endpoints` 下啟用：

```json
{
  "gateway": {
    "http": {
      "endpoints": {
        "chatCompletions": { "enabled": true },
        "responses": { "enabled": true }
      }
    }
  }
}
```

重啟 Gateway：

```bash
openclaw gateway restart
```

### `Probe session not found in OpenViking`

會話已發出但外掛未寫入 OpenViking。

```bash
openclaw config get plugins.slots.contextEngine
openclaw config get plugins.entries.openviking.config
openclaw logs --follow
```

常見原因：外掛未載入、`autoCapture` 關閉、路由或寫入失敗。

### `Session commit_count is still zero after waiting`

Commit 是非同步的，涉及 LLM 呼叫。如果超時：

1. 檢查 commit 任務是否還在執行：`curl http://127.0.0.1:<埠>/api/v1/tasks`
2. 如果還在執行，用 `--commit-wait 600` 重跑
3. 如果卡住，檢查 `storage.workspace/log/openviking.log`
4. 確認 LLM 後端可達且正常響應

### `Context endpoint has no archive overview after waiting`

歸檔概要在 commit 過程中生成。如果 commit 成功但概要缺失：

```bash
curl "http://127.0.0.1:<端口>/api/v1/sessions/<session_id>/context?token_budget=128000"
```

如果手動請求也為空，問題在 OpenViking 側；如果手動正常，檢查指令碼是否指向了錯誤例項。

### `Fresh-session recall was inconclusive`

通常不是完全故障。常見原因：`autoRecall` 關閉、記憶抽取未完成、模型本輪未命中。先重跑一次。

### `Direct backend memory search returned no results`

這是 `INFO`，不是失敗。只要 fresh-session recall 能答對，外掛鏈路就是正常的。

## 建議排查順序

1. 確認已按前置要求啟用 `gateway.http.endpoints`
2. 檢查 `plugins.slots.contextEngine` 是否為 `openviking`
3. 檢查 Gateway `/health`
4. 檢查 OpenViking `/health`
5. 看 `openclaw logs --follow`
6. 看 OpenViking 日誌
7. 看指令碼輸出裡失敗的具體階段
