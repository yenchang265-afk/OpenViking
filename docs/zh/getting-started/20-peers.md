# Peer

Peer 是當前使用者空間中的穩定互動物件，可以代表一個人或另一個 Agent。為物件使用固定的 `peer_id`，可以把相關資料和記憶組織在一起，並在後續會話中繼續使用。

例如，Alice 的助手經常與 `review-agent` 協作評審。Alice 自己的偏好儲存在使用者記憶中，與 review-agent 有關的評審偏好則可以儲存在對應的 Peer 記憶中。

## 區分身份與物件

| 概念 | 本例中的含義 |
| --- | --- |
| Account：`acme` | Alice 所屬團隊 |
| User：`alice` | 資料所有者和訪問服務的身份 |
| Peer：`review-agent` | Alice 的穩定互動物件 |
| Session | Alice 與物件的一次對話 |

`review-agent` 的內容位於 `viking://user/alice/peers/review-agent/`。Peer ID 不會建立一個獨立 User，也不會為該物件簽發訪問憑據。即使把 Peer 命名為 `bob`，它也仍然是 Alice 空間中的物件，與真實使用者 Bob 的個人空間分別管理。

## 準備工作

先完成[認證](17-authentication.md)，使用 `acme-alice` 連線。以下例子先驗證 Peer 資料範圍，再演示記憶提取；寫入資料和提取記憶需要可用的服務端模型，會產生模型呼叫。

為同一個物件保持穩定 ID，例如 `review-agent`；使用單段標識，避免在 ID 中使用 `/`。重複體驗時更換會話 ID，保留同一個 Peer ID 即可延續該物件的上下文。

## 儲存物件資料

Alice 為兩個協作物件分別建立資料目錄：

```bash
ov config switch acme-alice
ov mkdir viking://~/peers/review-agent/resources
ov mkdir viking://~/peers/research-agent/resources
```

為 review-agent 寫入一份協作說明：

```bash
ov write viking://~/peers/review-agent/resources/brief.md \
  --mode create --content "review-agent 負責評審，評審建議按問題、影響、建議三列組織。" --wait
```

處理完成後，讀取原文，確認內容：

```bash
ov read viking://~/peers/review-agent/resources/brief.md
```

如果寫入等待超時，儲存返回的任務 ID，用 `ov task status <task_id>` 查詢狀態；完成後再繼續。

## 限定 Peer 範圍

在 Alice 的同一連線上，使用 `actor_peer_id` 將一次請求的 Peer 集合限制到 review-agent：

```bash
ov --actor-peer-id review-agent ls viking://~/peers
ov --actor-peer-id review-agent read viking://~/peers/review-agent/resources/brief.md
```

列表只應包含允許的 Peer，讀取說明檔案應成功。再嘗試訪問另一個 Peer：

```bash
ov --actor-peer-id review-agent ls viking://~/peers/research-agent/resources
```

這次訪問應被拒絕。需要按問題查詢 review-agent 的資料時，可以限定具體目錄：

```bash
ov --actor-peer-id review-agent find "評審建議使用什麼格式？" \
  --uri viking://~/peers/review-agent/resources
```

Actor Peer 只限制當前使用者下的 Peer 集合。使用者自身的記憶、資料和可訪問的團隊共享資料仍按原許可權可見，會話也仍屬於 Alice。應用面向外部參與者時，應由可信入口決定 Peer 範圍；持有 Alice 完整 Key 的客戶端可以改變或省略這個範圍。獨立使用者許可權使用不同 User 身份。

## 儲存 Peer 記憶

訊息中的 `peer_id` 用來標識互動物件，`actor_peer_id` 用於請求的訪問範圍，兩者分別設定。本例只提取該物件的偏好，通過 HTTP 建立會話並顯式配置記憶策略。

在 Alice 的終端設定服務地址，通過隱藏輸入提供她自己的 User Key：

```bash
export OV_URL="http://127.0.0.1:1933"
read -r -s ALICE_KEY
export ALICE_KEY
```

建立會話，開啟 Peer 記憶、關閉本次會話的 Self 記憶提取，並使用手動提交：

```bash
curl -sS -X POST "$OV_URL/api/v1/sessions" \
  -H "X-API-Key: $ALICE_KEY" \
  -H "Content-Type: application/json" \
  -d '{"session_id":"peer-review-a","auto_commit_policy":null,"memory_policy":{"self":{"enabled":false},"peer":{"enabled":true},"memory_types":["preferences"]}}'
```

檢查響應成功後，仍使用 Alice 的 CLI 連線記錄訊息並提交：

```bash
ov session add-message peer-review-a --role user --peer-id review-agent \
  --content "我是 review-agent。我偏好將評審建議整理為問題、影響、建議三列的表格；後續與我協作評審時請沿用這個格式。"
ov session commit peer-review-a
```

記錄返回的 `task_id` 和 `archive_uri`。每隔 5 秒查詢一次任務，先觀察最多 2 分鐘；仍在執行時保留任務 ID，稍後繼續。狀態為 `failed` 或 `cancelled` 時檢視原因：

```bash
ov task status <task_id>
```

狀態為 `completed` 後讀取變更記錄：

```bash
ov read "<archive_uri>/memory_diff.json"
```

在 `operations.adds` 或 `operations.updates` 中查詢對應記憶 URI，再用 `ov read` 讀取。預期記錄位於 `viking://user/alice/peers/review-agent/memories/` 下，正文保留三列表格的偏好。檔名由提取結果決定；若沒有新增記錄，檢查是否更新了已有記憶，以及當前模板是否支援 Peer 和 preferences 型別。

## 在後續任務中使用

在新的對話中，讓使用 Alice 連線的 Agent 先檢索該 Peer 的記憶：

```bash
ov --actor-peer-id review-agent find "review-agent 的評審格式偏好" \
  --uri viking://~/peers/review-agent/memories
```

讀取命中的記憶，再讓 Agent 按該偏好生成評審表格並引用記憶 URI。新會話繼續使用 `review-agent` 標記相關訊息，後續提交可持續積累該物件的記憶。

## 下一步

Peer 內容屬於當前使用者。需要讓團隊其他使用者使用選定知識時，繼續[知識共享](22-sharing.md)；完整過濾規則見[多租戶](../concepts/11-multi-tenant.md#peer-restricted-view)。
