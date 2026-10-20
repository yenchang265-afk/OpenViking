---
description: 開啟 OpenViking 閘道器，簽發閘道器金鑰，傳送測試請求並確認記憶生效。
---

# OpenViking 閘道器快速上手

跟著本頁走完，你會從一套能正常工作的 OpenViking 服務出發，拿到一個[閘道器金鑰](../guides/15-gateway.md#key-terms)，經閘道器發出一次測試請求，並親眼確認記憶生效。開始前，`ov.conf` 中需要已經配好 embedding 和 VLM 模型（見[快速開始](../getting-started/02-quickstart.md)）。閘道器包含在核心包中，不需要另外安裝。

先按服務端的情況選一條路徑：

| 你的服務端 | 跟著做 |
| --- | --- |
| 繫結在 `127.0.0.1`，本地 dev 模式（未配置 `root_api_key`） | [本地服務](#local-server-no-api-key) |
| 通過網路訪問，使用 `api_key` 認證 | [遠端服務](#remote-server-api-keys) |
| 已有 OpenViking 服務，不想改它的配置 | 先按[獨立部署](../guides/22-gateway-operations.md#standalone-deployment)執行閘道器，再回到[傳送測試請求](#send-a-test-request) |

## 本地服務（不需要 API 金鑰） {#local-server-no-api-key}

本地 dev 模式的服務不需要 OpenViking API 金鑰：開啟 Studio 不用填金鑰，簽發的閘道器金鑰以本地 `default` 使用者的身份讀寫記憶。

1. **開啟閘道器。** 執行 `openviking-server init`，在 **Enable OpenViking Gateway on the same port?** 處回答 yes；已有配置時，在選單中選擇 **Update gateway**。也可以手動把 `{"gateway": {"enabled": true}}` 合併進 `ov.conf`。
2. **啟動或重啟 `openviking-server`。** 閘道器和 OpenViking 共用同一個埠，地址是 `http://127.0.0.1:1933/gateway`。
3. **在 Studio 中開啟閘道器。** 開啟 <http://127.0.0.1:1933/studio/>，在側邊欄選擇 **OpenViking 閘道器**。預設帳號還沒有[上游](../guides/15-gateway.md#key-terms)時，閘道器啟動時會把服務端的 VLM 配置匯入為上游，並建立一份上下文配置。此時“概覽”標籤頁的**快速開始**清單應該已經完成了前兩步（見[快速開始清單和快速模式](06-manage-in-studio.md#get-started-checklist)）。匯入的 Coding Plan 上游需要你確認後才能使用，見[匯入 OpenViking 模型配置](07-upstreams.md#import-openviking-model-settings)；沒有可匯入的配置時，按[上游](07-upstreams.md#upstreams)手動新增。
4. **簽發閘道器金鑰。** 在“概覽”標籤頁的**快速模式**卡片中點**一鍵生成金鑰**；也可以手動簽發：在“金鑰”標籤頁點**簽發金鑰**，填寫名稱，選擇上下文配置和上游，然後簽發。隨後會彈出**複製閘道器金鑰**對話方塊，顯示完整的 `ovgw_…` 金鑰。金鑰只顯示這一次，關閉對話方塊前務必複製。

閘道器地址是 `http://127.0.0.1:1933/gateway`。接下來[傳送測試請求](#send-a-test-request)。

## 遠端服務（使用 API 金鑰） {#remote-server-api-keys}

遠端服務指通過網路訪問、使用 `api_key` 認證的服務。每個人用自己的 OpenViking API 金鑰登入 Studio。

不想在服務端主機上執行 init 的話，可以用 root API 金鑰登入 Studio，在 OpenViking 閘道器頁面點**開啟閘道器**，代替第 1-3 步；確認對話方塊裡也能生成閘道器管理金鑰。見[在 Server 中啟用](../guides/22-gateway-operations.md#enable-it-in-the-server)。

1. **開啟閘道器。** 在服務端主機上執行 `openviking-server init`，繫結地址選擇 **Remote (0.0.0.0)**，在 **Enable OpenViking Gateway on the same port?** 處回答 yes。
2. **決定誰能修改上游。** 接下來的 **Allow users to configure their own gateway upstreams?** 決定誰能修改上游和上下文配置。回答 yes，每個登入的使用者都能配置本帳號的上游和上下文配置。回答 no，則改由[閘道器管理金鑰](../guides/22-gateway-operations.md#gateway-management-key)把關：init 生成一個以 `ovgm_` 開頭的金鑰，列印出來並寫入 `ov.conf` 的 `gateway.management_key`，只有帶著這個金鑰的請求才能修改上游和上下文配置。請儲存好列印出的金鑰，第 6 步要用。
3. **重啟服務。** 閘道器和 OpenViking 共用同一個埠，地址是 `https://ov.example.com/gateway`。
4. **準備 OpenViking API 金鑰。** 用你自己的使用者 API 金鑰，或者按[認證](../guides/04-authentication.md)用 root API 金鑰建立帳號和使用者。
5. **登入 Studio。** 開啟 `https://ov.example.com/studio/`，在**連線設定**中填入 API 金鑰，然後在側邊欄選擇 **OpenViking 閘道器**，應該能看到“概覽”標籤頁。
6. **新增上游。** 在“上游”標籤頁點**新增上游**，選擇服務商和客戶端使用的協議（下面的測試請求用 Chat Completions），貼上服務商的 API Key 後儲存。然後在上游列表裡點**測試**，看到**連線可用**或**模型可用**，就說明閘道器能連上服務商。如果標籤頁是隻讀的，說明設定了閘道器管理金鑰：點**輸入閘道器管理金鑰**解鎖編輯（見[解鎖編輯](06-manage-in-studio.md#unlock-editing)），或者聯絡部署閘道器的人。
7. **建立上下文配置。** 在“上下文配置”標籤頁點**使用推薦設定建立**，卡片列表裡應該出現這份新的上下文配置。
8. **簽發閘道器金鑰**，做法同本地路徑第 4 步，簽發給你自己。隨後會彈出**複製閘道器金鑰**對話方塊，金鑰只顯示這一次，請立即複製。要給其他使用者簽發，見[簽發金鑰](09-gateway-keys.md#issue-a-key)。

閘道器地址是 `https://ov.example.com/gateway`，其中 `ov.example.com` 換成你的服務端地址。

## 傳送測試請求 {#send-a-test-request}

> **提示**：[確認記憶生效](#confirm-that-memory-works)的第 3 步要等對話停頓 10 分鐘才會提取記憶。想更快試用，可以先建一份上下文配置，把**最新回覆等待時長**調短（例如 30 秒），用它簽發一個金鑰，下面的 `GATEWAY_KEY` 就用這個金鑰。上下文配置的修改只對之後開始的對話生效（見[修改何時生效](06-manage-in-studio.md#when-changes-take-effect)）。

用 curl 發兩個請求：第一個列出金鑰可用的模型，第二個經閘道器向模型提一個問題。把 `GATEWAY_URL` 設為你的閘道器地址（本地服務是 `http://127.0.0.1:1933/gateway`），並把 `<model>` 換成上游提供的模型：

```bash
export GATEWAY_URL=https://ov.example.com/gateway
export GATEWAY_KEY='ovgw_...'

curl -s "$GATEWAY_URL/v1/models" -H "Authorization: Bearer $GATEWAY_KEY"

curl -s "$GATEWAY_URL/v1/chat/completions" \
  -H "Authorization: Bearer $GATEWAY_KEY" \
  -H "Content-Type: application/json" \
  -H "X-OpenViking-Session: quickstart-1" \
  -d '{"model": "<model>", "messages": [{"role": "user", "content": "記住：我喜歡簡短的回答。"}]}'
```

| 命令 | 預期結果 |
| --- | --- |
| `GET /v1/models` | 金鑰繫結的已啟用上游裡配置的模型名和別名；金鑰限定了可用模型時，只列出允許的那些 |
| `POST /v1/chat/completions` | 服務商的一次正常回復 |

模型列表不全甚至為空，請求也可能照樣成功：模型列表留空的上游接受任意模型名，但不往這個列表里加任何名稱。`X-OpenViking-Session` 請求頭用來標識對話，帶同一個值的下一個請求會接著這段對話往下走，詳見[閘道器如何識別對話](03-connect-clients.md#how-conversations-are-recognized)。

## 確認記憶生效 {#confirm-that-memory-works}

依次確認三件事：請求經過了閘道器，對話已經儲存，新對話裡能召回記憶。

1. **請求經過了閘道器。** 開啟“請求日誌”標籤頁，剛才的請求應該顯示為**新訊息**，狀態 200。OpenViking 裡有相關內容時，**記憶**列會顯示補充的條數，例如 `+3`；全新帳號下這一列為空。
2. **對話已儲存。** 用同一個 `X-OpenViking-Session` 值再發一個請求，它的 `messages` 要包含整段對話：你的第一條訊息、收到的回覆和一條新訊息。聊天客戶端會自動帶上這些內容，用 curl 時要自己補上：

   ```bash
   curl -s "$GATEWAY_URL/v1/chat/completions" \
     -H "Authorization: Bearer $GATEWAY_KEY" \
     -H "Content-Type: application/json" \
     -H "X-OpenViking-Session: quickstart-1" \
     -d '{"model": "<model>", "messages": [
       {"role": "user", "content": "記住：我喜歡簡短的回答。"},
       {"role": "assistant", "content": "<收到的回覆>"},
       {"role": "user", "content": "謝謝。"}]}'
   ```

   這個請求一到，第一輪對話就會儲存（[為什麼儲存總是晚一輪](01-how-it-works.md#when-conversations-are-saved)）。開啟 Studio 的**會話**頁面，應該能看到一個 `gateway-…` 會話。會話屬於金鑰所屬的使用者：如果金鑰是為別人簽發的，需要在**連線設定**中填入該使用者的 OpenViking API 金鑰登入後才能看到。
3. **記憶已提取。** 對話停頓達到**最新回覆等待時長**（預設 10 分鐘）後，閘道器提交會話，OpenViking 在後臺提取記憶，需要稍等片刻。然後換一個會話值開始新對話，問一個依賴這條記憶的問題，例如“你的回答應該多長？”。**記憶**列應顯示召回的條數，回覆也應該用上了這條記憶。

如果**記憶**列一直為空，或者看不到會話，見[沒有補充記憶](12-troubleshooting.md#no-memory-is-added)和[OpenViking 中看不到對話](12-troubleshooting.md#conversations-do-not-appear-in-openviking)。

## 下一步 {#next-steps}

- [接入客戶端](03-connect-clients.md#connect-clients)：把 Claude Code、Codex CLI 或聊天應用指向閘道器。
- [簽發金鑰](09-gateway-keys.md#issue-a-key)：給其他使用者簽發各自的閘道器金鑰。
- [部署與運維](../guides/22-gateway-operations.md)：用 Docker Compose、Helm 或獨立部署為團隊執行閘道器。
