---
description: 把 Claude Code、Codex、聊天應用、SDK 等客戶端接入 OpenViking 閘道器，並檢查接入是否生效。
---

# 把客戶端接入 OpenViking 閘道器

本頁按客戶端給出具體配置，以及驗證配置是否生效的方法。每個客戶端都需要三樣東西：閘道器地址、閘道器金鑰（部署方開啟 `openviking_keys` 時，也可以用使用者的 OpenViking API 金鑰，見[直接使用 OpenViking API 金鑰](09-gateway-keys.md#openviking-keys)），以及這把金鑰繫結的一個已啟用上游——它要支援客戶端使用的協議，並提供客戶端請求的模型。還沒有閘道器金鑰？先看[快速上手](02-quickstart.md)。

以下兩條限制對所有客戶端都適用：

- 客戶端不能用訂閱帳號登入閘道器。上游需要配置服務商的 API Key，或者接一個訂閱反代：Codex 可以通過 CLIProxyAPI 上游使用 ChatGPT 訂閱（見[使用 ChatGPT 訂閱](#codex-chatgpt-subscription)）。其他訂閱服務請自行確認其使用條款（另見[使用須知](01-how-it-works.md#what-to-expect)）。
- 使用 Responses 的客戶端，每個請求都必須帶上完整的對話歷史（見[客戶端要求](04-openviking-tools.md#client-requirements)）。

## 客戶端設定一覽 {#connect-clients}

閘道器地址是服務地址加上 `/gateway`。在 Studio 中，OpenViking 閘道器頁面頂部和**接入**標籤頁都會顯示它。下面的示例用 `https://ov.example.com/gateway`，請換成你自己的地址。Anthropic 客戶端直接使用閘道器地址，OpenAI 相容客戶端在後面加 `/v1`，方舟 SDK 加 `/api/v3`。

| 客戶端 | 上游協議 | Base URL | 對話識別方式 |
| --- | --- | --- | --- |
| [Claude Code](#claude-code) | Anthropic Messages | `https://ov.example.com/gateway` | Claude Code 的會話請求頭 |
| [Codex CLI](#codex-cli) | Responses | `https://ov.example.com/gateway/v1` | Codex 的會話請求頭 |
| [聊天客戶端和 SDK](#chat-clients-and-sdks) | Chat Completions（或 SDK 使用的 API） | `https://ov.example.com/gateway/v1` | `X-OpenViking-Session`，需要自己傳送 |
| [Open WebUI](#open-webui) | Chat Completions | `https://ov.example.com/gateway/v1` | 在連線上配置 `X-OpenViking-Session` 請求頭 |
| [OpenCode](#opencode) | Chat Completions、Anthropic Messages 或 Responses | `https://ov.example.com/gateway/v1` | OpenCode 的會話請求頭 |
| [pi](#pi) | Chat Completions、Anthropic Messages 或 Responses | `https://ov.example.com/gateway/v1`（Anthropic Messages 用 `https://ov.example.com/gateway`） | 通常根據對話歷史匹配 |
| [DSH](#dsh) | Chat Completions、Anthropic Messages 或 Responses | `https://ov.example.com/gateway/v1`（Anthropic Messages 用 `https://ov.example.com/gateway`） | 通常根據對話歷史匹配 |
| [火山方舟與 BytePlus 方舟 SDK](#volcano-engine-ark-and-byteplus-modelark-sdks) | 三種均可 | `https://ov.example.com/gateway/api/v3` 或 `https://ov.example.com/gateway/api/compatible` | 取決於客戶端傳送的請求頭 |

最後一列的含義見[閘道器如何識別對話](#how-conversations-are-recognized)。

## 客戶端自帶服務商 API Key 時 {#bring-your-own-provider-key}

預設情況下，服務商的 API Key 由閘道器保管，客戶端只需傳送閘道器金鑰。[上游](07-upstreams.md#upstreams)也可以把 **API Key 由誰提供**設為**每個客戶端自帶 API Key**（見[憑證](07-upstreams.md#credentials)）。這時客戶端仍把閘道器金鑰填在原來填 API Key 的地方，同時在每個請求裡用 `X-OpenViking-Upstream-Key` 請求頭帶上自己的服務商 API Key。在 Studio 中，**接入**標籤頁的**客戶端自帶服務商 API Key**卡片會列出哪些上游需要它。

缺了這個請求頭，所有請求都會返回 401 `Upstream API key is missing`。各客戶端的新增方式見[在客戶端裡新增請求頭](#add-a-header)。

## 覆蓋上下文配置 {#override-profile-settings}

客戶端可以用 `X-OpenViking-Context` 請求頭，為新對話修改金鑰所用上下文配置的設定。它的值是一個 JSON 物件，列出要修改的欄位，例如 `{"recall":false}` 表示不召回，`{"disabled_tools":[]}` 表示提供全部 OpenViking 工具，包括會修改資料的工具。配置需要開啟**允許客戶端覆蓋設定**（預設開啟）；請求頭能包含什麼、可能返回哪些錯誤，見[允許客戶端覆蓋設定](08-context-profiles.md#client-overrides)。各客戶端的新增方式見[在客戶端裡新增請求頭](#add-a-header)。

對話會沿用開始時的設定，所以修改後的請求頭從下一段新對話起生效，例如換一個新的 `X-OpenViking-Session` 值。與所有 `X-OpenViking-*` 請求頭一樣，它不會轉發給服務商。

## 在客戶端裡新增請求頭 {#add-a-header}

上面兩個請求頭都要隨每個請求傳送。各客戶端的新增方式：

| 客戶端 | 如何新增請求頭 |
| --- | --- |
| Claude Code | `export ANTHROPIC_CUSTOM_HEADERS='<Name>: <value>'`。有多個請求頭時每行一個，例如 `export ANTHROPIC_CUSTOM_HEADERS=$'X-OpenViking-Upstream-Key: <provider-key>\nX-OpenViking-Context: {"recall":false}'` |
| Codex CLI | 在服務商配置裡，固定值用 `http_headers`，例如 `http_headers = { "X-OpenViking-Context" = '{"recall":false}' }`；從環境變數讀取用 `env_http_headers`，例如 `env_http_headers = { "X-OpenViking-Upstream-Key" = "PROVIDER_API_KEY" }`，並把服務商 API Key 匯出為 `PROVIDER_API_KEY` |
| OpenAI 和 Anthropic SDK | 在客戶端上設定 `default_headers`，或在每個請求裡傳 `extra_headers` |
| Open WebUI | 加到連線的自定義請求頭裡，與會話請求頭放在一起 |

## Claude Code {#claude-code}

Claude Code 使用 Anthropic Messages，Base URL 為 `https://ov.example.com/gateway`。啟動前設定三個環境變數：

```bash
export ANTHROPIC_BASE_URL=https://ov.example.com/gateway
export ANTHROPIC_AUTH_TOKEN='<gateway-key>'
export CLAUDE_CODE_GATEWAY_HINT_HEADERS=1
```

- 地址不要帶 `/v1`，Claude Code 會自己補全路徑。
- `CLAUDE_CODE_GATEWAY_HINT_HEADERS=1` 讓 Claude Code 給子 Agent、上下文壓縮和後臺請求加上標記，閘道器就不會為它們召回記憶，也不會把它們當作對話輪次儲存。
- Claude Code 傳送自己的會話 ID，閘道器據此識別對話，`--resume` 之後也一樣。
- 上游必須接受 Claude Code 請求的模型名：模型列表留空、列出這些名稱，或者用模型別名對映到服務商的模型（見[模型](07-upstreams.md#models)）。
- Claude 訂閱登入不能通過閘道器使用，帶訂閱令牌的請求會被拒絕。請為上游配置服務商的 API Key。
- 同時裝了 OpenViking 外掛時，閘道器會讓出這些對話（見[兩者同時使用時](../guides/15-gateway.md#when-both-are-in-use)）。只接了 OpenViking MCP 伺服器時，閘道器照常補充記憶，OpenViking 工具交給 MCP 伺服器。

配好後，[檢查接入是否生效](#check-the-connection)。

## Codex CLI {#codex-cli}

Codex 使用 Responses API，Base URL 為 `https://ov.example.com/gateway/v1`。它每個請求都帶完整歷史，正好滿足閘道器的要求。在 `~/.codex/config.toml` 中新增一個服務商，兩個頂層設定必須寫在所有 `[section]` 之前：

```toml
model_provider = "openviking"
model = "<model>"

[model_providers.openviking]
name = "OpenViking Gateway"
base_url = "https://ov.example.com/gateway/v1"
wire_api = "responses"
env_key = "OPENVIKING_GATEWAY_KEY"
```

然後在執行 Codex 的環境裡設定閘道器金鑰：

```bash
export OPENVIKING_GATEWAY_KEY='<gateway-key>'
```

- 金鑰繫結的上游必須使用 Responses，並提供 `<model>`。
- Codex 會先嚐試 WebSocket 連線，被閘道器拒絕後自動改用 HTTP。
- Codex 傳送自己的會話 ID，閘道器據此識別對話，`codex resume` 之後也一樣。
- 遇到不認識的模型名，Codex 可能提示缺少模型後設資料，不影響請求。
- 想用 ChatGPT 訂閱代替 API Key，見下一節。

### 使用 ChatGPT 訂閱 {#codex-chatgpt-subscription}

Codex 可以經閘道器使用你的 ChatGPT 訂閱。Codex 不會把 ChatGPT 登入資訊發給閘道器，而是由 [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI)（CPA）作為上游接在閘道器後面：CPA 用你的 ChatGPT 帳號登入，再以 Responses API 的形式提供服務。這種用法得到了 OpenAI 的認可：OpenAI Codex 負責人 Tibo 曾[公開介紹](https://x.com/thsottiaux/status/2076119366647894371)過用 CLIProxyAPI 接入 Codex 訂閱的做法。

1. 按 CPA 的 README 執行 CPA，並用你的 ChatGPT 帳號登入。
2. 在 Studio 中把 CPA 新增為上游：服務商選*通用*，協議選 Responses，**Base URL** 填 CPA 的地址，API Key 填 CPA 的某個 API 金鑰。見[自定義上游](07-upstreams.md#custom-upstreams)。
3. 簽發繫結該上游的閘道器金鑰，再按上文配置 Codex。Codex 仍用閘道器金鑰連線閘道器，訂閱只儲存在 CPA 裡。

配好後，[檢查接入是否生效](#check-the-connection)。

## 聊天客戶端和 SDK {#chat-clients-and-sdks}

支援 OpenAI Chat Completions API 的客戶端和 SDK 都能接入，Base URL 為 `https://ov.example.com/gateway/v1`。在客戶端填寫 OpenAI 相容服務商的地方填入：

```text
Base URL: https://ov.example.com/gateway/v1
API key: <gateway-key>
Model: <model>
X-OpenViking-Session: <conversation-id>
```

`X-OpenViking-Session` 請求頭可選，但建議傳送，它告訴閘道器請求屬於哪段對話。取值在同一段對話內保持不變、不同對話之間互不相同，例如應用裡的聊天 ID。不傳送時，閘道器根據歷史匹配對話，見[閘道器如何識別對話](#how-conversations-are-recognized)。

用 OpenAI Python SDK：

```python
from openai import OpenAI

client = OpenAI(base_url="https://ov.example.com/gateway/v1", api_key="<gateway-key>")

reply = client.chat.completions.create(
    model="<model>",
    messages=[{"role": "user", "content": "釋出日期最後定在哪天？"}],
    extra_headers={"X-OpenViking-Session": "chat-42"},
)
print(reply.choices[0].message.content)
```

流式呼叫 Chat Completions 時，請同時請求返回用量（`"stream_options": {"include_usage": true}`）。否則服務商不報告流式回覆的 token 數，Studio 顯示不了用量，閘道器也只能估算上下文視窗用了多少。

另外兩種 API 的 SDK 用法相同，前提是上游使用的 API 和 SDK 一致：

- Anthropic SDK 指向 `https://ov.example.com/gateway`。
- Responses API 使用 `https://ov.example.com/gateway/v1`，每個請求都要帶完整歷史並設定 `store: false`；其他 Responses 請求直接轉發，不補充記憶。

配好後，[檢查接入是否生效](#check-the-connection)。

## Open WebUI {#open-webui}

Open WebUI 通過 Chat Completions 接入，Base URL 為 `https://ov.example.com/gateway/v1`。分三步配置：

1. 在 Open WebUI 中開啟 Admin Panel → Settings → Connections，新增一個 OpenAI 相容連線，Base URL 填 `https://ov.example.com/gateway/v1`，金鑰填閘道器金鑰。
2. 給這個連線加上下面的自定義請求頭，讓每個聊天成為一段獨立的對話，並讓閘道器認出 Open WebUI 的後臺任務：

   ```json
   {
     "X-OpenViking-Session": "{{CHAT_ID}}",
     "X-OpenViking-Task": "{{TASK}}"
   }
   ```

3. 在 Open WebUI 的環境變數中設定 `RAG_SYSTEM_CONTEXT=true`。這樣 Open WebUI 會把附件檢索結果放進 system 訊息，而不是臨時改寫你這一輪的訊息，請求之間的對話歷史才能保持穩定。

另外需要注意兩點：

- **一個連線金鑰只對應一位記憶歸屬者。** 通過這個連線聊天的所有 Open WebUI 使用者，讀寫的都是金鑰背後那位 OpenViking 使用者的記憶。要麼只讓一個人用這個連線，要麼接受這些使用者共享記憶（見[每人一把金鑰](09-gateway-keys.md#one-key-per-person)）。
- Open WebUI 還會通過同一個連線傳送後臺請求（生成標題、標籤和追問建議）。閘道器能識別標題和摘要請求；如果請求日誌裡有其他後臺任務被標成**新訊息**，就把 Open WebUI 的任務模型改成一個不經過閘道器的連線。

配好後，[檢查接入是否生效](#check-the-connection)。

## OpenCode {#opencode}

OpenCode 可以使用 Chat Completions、Anthropic Messages 或 Responses，Base URL 都是 `https://ov.example.com/gateway/v1`。在 `~/.config/opencode/opencode.json` 中新增一個服務商，與已有設定合併：

```json
{
  "provider": {
    "openviking": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "OpenViking",
      "options": {
        "baseURL": "https://ov.example.com/gateway/v1",
        "apiKey": "{env:OPENVIKING_GATEWAY_KEY}"
      },
      "models": {
        "<model>": {}
      }
    }
  }
}
```

示例用的是 Chat Completions。換用其他協議時改 `npm`，`baseURL` 不變。金鑰繫結的上游必須使用你選的協議；Studio 的**接入**標籤頁會自動填好對應的包：

| 上游協議 | `npm` |
| --- | --- |
| Chat Completions | `@ai-sdk/openai-compatible` |
| Responses | `@ai-sdk/openai` |
| Anthropic Messages | `@ai-sdk/anthropic` |

把閘道器金鑰匯出為 `OPENVIKING_GATEWAY_KEY`，然後在 OpenCode 中選擇 `openviking/<model>`。同時裝了 OpenViking 的 OpenCode 外掛時，閘道器會讓出這些對話。

配好後，[檢查接入是否生效](#check-the-connection)。

## pi {#pi}

pi 可以使用 Chat Completions、Anthropic Messages 或 Responses，Base URL 為 `https://ov.example.com/gateway/v1`（Anthropic Messages 用 `https://ov.example.com/gateway`）。在 pi 的模型配置 `~/.pi/agent/models.json` 中新增一個服務商：

```json
{
  "providers": {
    "openviking": {
      "baseUrl": "https://ov.example.com/gateway/v1",
      "apiKey": "$OPENVIKING_GATEWAY_KEY",
      "api": "openai-completions",
      "models": [
        {
          "id": "<model>"
        }
      ]
    }
  }
}
```

示例用的是 Chat Completions。換用其他協議時，按下表設定 `api` 和 `baseUrl`，金鑰繫結的上游也必須使用這種協議。Anthropic Messages 的地址不帶 `/v1`，因為 Anthropic SDK 會自己補上：

| 上游協議 | `api` | `baseUrl` |
| --- | --- | --- |
| Chat Completions | `openai-completions` | `https://ov.example.com/gateway/v1` |
| Responses | `openai-responses` | `https://ov.example.com/gateway/v1` |
| Anthropic Messages | `anthropic-messages` | `https://ov.example.com/gateway` |

- `apiKey` 從環境變數 `OPENVIKING_GATEWAY_KEY` 讀取閘道器金鑰，啟動 pi 前先匯出它。開頭的 `$` 不能省，否則 pi 會把這個字串本身當作金鑰傳送。
- pi 通常不傳送會話請求頭，閘道器根據歷史匹配它的對話（見[閘道器如何識別對話](#how-conversations-are-recognized)）。
- pi 自己的 OpenViking 擴充啟用時，閘道器會讓出這些對話，兩者選一個即可。

配好後，[檢查接入是否生效](#check-the-connection)。

## DSH {#dsh}

[DeepSeek Harness](https://www.npmjs.com/package/@deepseek-ai/dsh)（`dsh`）的模型層基於 pi，`api` 和 Base URL 的取值與 pi 相同：`https://ov.example.com/gateway/v1`，Anthropic Messages 用 `https://ov.example.com/gateway`。在 profile 配置中新增一個服務商；`dsh web` 使用的 profile 是 `web`，所以檔案是 `~/.dsh/profiles/web/cordis.patch.yml`；DeepSeek Harness Desktop 桌面應用用的是 `~/.dsh/profiles/desktop/cordis.patch.yml`：

```yaml
- id: llm-pi-ai
  config:
    providers:
      openviking:
        api: openai-completions
        baseURL: "https://ov.example.com/gateway/v1"
        apiKeyEnv: OPENVIKING_GATEWAY_KEY
        models:
          - id: "<model>"
```

如果檔案裡已經有 `llm-pi-ai` 條目，就把 `openviking` 加到它的 `providers` 下，不要再寫第二個條目。使用 Responses 或 Anthropic Messages 時，按 [pi 一節的表格](#pi)設定 `api` 和 `baseURL`。

把閘道器金鑰匯出為 `OPENVIKING_GATEWAY_KEY`（也就是 `apiKeyEnv` 填的變數名），然後啟動 `dsh web`，在模型選擇器中選擇 `openviking` 服務商下的 `<model>`。

- 也可以在 Web UI 的 Settings → Models → Add model provider → Custom model API 中新增，寫入的是同一個檔案。
- Desktop 看不到在終端裡 export 的變數。macOS 上把 `OPENVIKING_GATEWAY_KEY` 寫進 shell 啟動檔案（`~/.zprofile` 或 `~/.zshrc`）；Windows 上用 `setx` 設定。然後用 ⌘Q 或托盤選單退出 Desktop，再重新開啟。Desktop 的恢復對話方塊會把 `cordis.patch.yml` 挪成 `.bak-<時間戳>` 檔案，執行過恢復後需要重新新增服務商。
- DSH 的一個服務商只使用一種協議。要通過多種協議使用閘道器，就為每種協議各宣告一個服務商。
- 除非 DSH 傳送了某個會話請求頭，否則閘道器根據歷史匹配它的對話（見[閘道器如何識別對話](#how-conversations-are-recognized)）。
- 同一個 profile 裡裝了 [OpenViking 的 DSH 外掛](../agent-integrations/17-dsh.md)時，閘道器會讓出這些對話，兩者選一個即可。

配好後，[檢查接入是否生效](#check-the-connection)。

## 火山方舟與 BytePlus 方舟 SDK {#volcano-engine-ark-and-byteplus-modelark-sdks}

已經接入火山方舟或其海外站 BytePlus 方舟的客戶端和 SDK，三種 API 都可以用，只需替換地址，通常換成 `https://ov.example.com/gateway/api/v3`。在 `/gateway` 下，閘道器既接受方舟自己的路徑（`/api/v3/chat/completions`、`/api/v3/responses`、`/api/v3/models` 和 `/api/compatible/v1/messages`），也接受標準的 `/v1` 路徑：

| 原地址 | 閘道器地址 |
| --- | --- |
| `https://ark.cn-beijing.volces.com/api/v3` | `https://ov.example.com/gateway/api/v3` |
| `https://ark.ap-southeast.bytepluses.com/api/v3` | `https://ov.example.com/gateway/api/v3` |
| `https://ark.cn-beijing.volces.com/api/compatible`（Anthropic 相容） | `https://ov.example.com/gateway/api/compatible` |

用閘道器金鑰代替方舟的 API Key。以火山方舟 Python SDK 為例：

```python
from volcenginesdkarkruntime import Ark

client = Ark(base_url="https://ov.example.com/gateway/api/v3", api_key="<gateway-key>")
```

客戶端用哪個路徑，只決定它使用哪種 API。請求仍然發往金鑰繫結的、使用這種 API 並提供該模型的上游，通常是服務商選為“火山方舟”或“BytePlus 方舟（海外站）”的上游（見[上游](07-upstreams.md#upstreams)）。和其他聊天客戶端一樣，請用 `X-OpenViking-Session` 為每段對話傳送一個固定的值。

配好後，[檢查接入是否生效](#check-the-connection)。

## 檢查接入是否生效 {#check-the-connection}

每配好一個新客戶端，都用一段簡短的對話驗證一次。Open WebUI、OpenCode、pi 和 DSH 尤其需要：它們的配置是依據各自文件中的服務商設定編寫的，請當作起點。

1. 在客戶端的同一段對話（同一個聊天或同一個 Agent 會話）裡發兩條訊息。應該能正常收到回覆。
2. 在 Studio 中開啟**請求日誌**標籤頁。兩個請求都應顯示為**新訊息**，狀態碼為 200。
3. 展開這兩個請求。它們的**對話**應該相同，**儲存**一欄應顯示**正常**，表示儲存已開啟且執行正常。第二條訊息到達後第一輪就會儲存；要看到它，請以金鑰所屬使用者的身份登入 Studio，在**會話**頁面找到 `gateway-…` 會話（見[確認記憶生效](02-quickstart.md#confirm-that-memory-works)）。

如果結果不對：

- **看不到任何請求。** 只有到達模型服務商的請求才會記錄，說明客戶端直接收到了閘道器返回的錯誤，見[客戶端收到閘道器返回的錯誤](12-troubleshooting.md#clients-get-an-error-from-the-gateway)。
- **兩個請求屬於不同的對話。** 客戶端沒有傳送會話請求頭，且歷史也沒有匹配上，見[閘道器如何識別對話](#how-conversations-are-recognized)。
- **記憶一欄一直是空的。** 全新帳號本來就是這樣。要完整驗證記憶是否生效，按[確認記憶生效](02-quickstart.md#confirm-that-memory-works)操作。

請求日誌每一列和每個標籤的含義見[請求日誌](10-overview-and-requests.md#requests)。

## 閘道器如何識別對話 {#how-conversations-are-recognized}

對話是閘道器當作同一次聊天處理的一系列請求：一段對話固定使用同一份上下文配置和同一個上游，並儲存到一個 OpenViking 會話，某些情況下改存到新會話，例如客戶端改寫歷史時（見[儲存狀態](10-overview-and-requests.md#saving-status)）。為了判斷請求屬於哪段對話，閘道器按以下順序取第一個出現的請求頭：

1. `X-OpenViking-Session`
2. `thread-id`
3. `x-claude-code-session-id`（Claude Code）
4. `x-opencode-session-id`（OpenCode）
5. `x-session-id`
6. `session-id`（Codex CLI）

這些請求頭都沒有時，閘道器檢視歷史中最近一條助手回覆：如果恰好有一段之前的對話產生過這條回覆，請求就併入那段對話，否則開始一段新對話。開場訊息相同的兩段對話不會因此被合併。普通的一問一答這樣就能識別，但重試、重新生成和內容完全相同的對話存在歧義，可能被當成新對話。所以只要客戶端允許設定請求頭，就傳送 `X-OpenViking-Session`。

對話歸屬於金鑰背後的 OpenViking 使用者，並按 API 區分。同一使用者的兩個閘道器金鑰傳送相同的會話值，會共享同一段對話；同一個會話值用在另一種 API 上，則是另一段對話。閘道器轉發前會去掉所有 `X-OpenViking-*` 請求頭，服務商看不到它們。

請求沒有歸入已有對話時，記憶照樣工作：新訊息照常召回，之前補充的記憶也照常原樣放回，因為閘道器是根據訊息本身找到這些記憶的。區別在於這個請求會開始一段新對話：它的輪次儲存到新的 OpenViking 會話，記憶預算從頭計算，並使用金鑰當前的上下文配置。

## 下一步 {#next-steps}

- [使用須知](01-how-it-works.md#what-to-expect)：客戶端改走閘道器後，哪些行為會變化。
- [上下文配置](08-context-profiles.md)：調整召回多少記憶、是否儲存對話。
- [OpenViking 閘道器排障](12-troubleshooting.md)：處理報錯、記憶缺失或對話沒有儲存等問題。
