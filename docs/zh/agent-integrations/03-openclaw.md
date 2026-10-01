# OpenClaw 插件

為 [OpenClaw](https://github.com/openclaw/openclaw) 新增長效記憶。安裝完成後，OpenClaw 會自動記住對話中的重要資訊，並在每次回覆前召回相關上下文。

原始碼：[examples/openclaw-plugin](https://github.com/volcengine/OpenViking/tree/main/examples/openclaw-plugin)

## 前置條件

| 元件 | 版本要求 |
| --- | --- |
| Node.js | >= 22 |
| OpenClaw | >= 2026.5.27 |

外掛需要連線到一個正在執行的 OpenViking 服務——參見 [部署指南](../guides/03-deployment.md)。

<details>
<summary><b>從舊版 <code>memory-openviking</code> 升級？</b></summary>

舊外掛不相容，請先清理：

```bash
curl -fsSL https://raw.githubusercontent.com/volcengine/OpenViking/main/examples/openclaw-plugin/upgrade_scripts/cleanup-memory-openviking.sh -o cleanup-memory-openviking.sh
bash cleanup-memory-openviking.sh
```

</details>

## 安裝

```bash
openclaw plugins install clawhub:@openviking/openclaw-plugin
openclaw openviking setup --base-url http://your-server:1933 --api-key sk-xxx --json
openclaw gateway restart
```

`setup` 嚮導寫入配置並激活外掛。安裝完成後開始對話——OpenClaw 會自動記憶和召回。

<details>
<summary><b>備用方案：通過 <code>ov-install</code> 安裝</b></summary>

當 ClawHub 不可用時：

```bash
npm install -g openclaw-openviking-setup-helper
ov-install --base-url http://your-server:1933
```

常用引數：

| 引數 | 含義 |
| --- | --- |
| `--workdir PATH` | OpenClaw 資料目錄（預設 `~/.openclaw`） |
| `--plugin-version=VER` | 插件版本：npm 版本、dist-tag 或 Git ref |
| `--base-url URL` | OpenViking 服務地址 |
| `--api-key KEY` | OpenViking API Key |
| `--peer-role ROLE` | 記憶歸屬：`none`、`assistant` 或 `sender`（`person` 是舊別名） |
| `--uninstall` | 解除安裝外掛 |

完整引數列表見 [安裝指南](https://github.com/volcengine/OpenViking/blob/main/examples/openclaw-plugin/INSTALL.md)。

</details>

## 選擇記憶歸屬

`peer_role` 決定長期記憶是在 OpenViking user 層共享，還是歸屬到具體 peer：

| 值 | 記憶路徑 | 適用場景 |
| --- | --- | --- |
| `none`（預設） | 共享記憶位於 `viking://user/<user_id>/memories/...`；不使用具體 peer 的記憶子樹 | 通用場景：該 OpenViking 使用者下的所有對話共享 user-level 記憶 |
| `assistant` | assistant 歸因的 peer 記憶位於 `viking://user/<user_id>/peers/<assistant_id>/memories/...` | **人是 OpenViking user**：讓 `main`、`research` 等不同助手的 peer 記憶分開 |
| `sender` | sender 歸因的 peer 記憶位於 `viking://user/<user_id>/peers/<sender_id>/memories/...` | **Agent 是 OpenViking user**：讓 `customer-42`、`customer-99` 等不同傳送者的 peer 記憶分開 |

例如：

```bash
# Alice 是 OpenViking user；按 OpenClaw 助手分開 peer 記憶。
openclaw openviking setup --base-url http://your-server:1933 --api-key sk-xxx --peer-role assistant --json

# support-agent 是 OpenViking user；按給它發訊息的人分開 peer 記憶。
openclaw openviking setup --base-url http://your-server:1933 --api-key sk-xxx --peer-role sender --json
```

新配置請使用 `sender`；已有的 `peer_role=person` 配置仍相容，並按 `sender` 處理。OpenViking 會為每個使用者初始化受管的 `peers/` 容器，因此 `none` 的含義是不使用具體的 `peers/<peer_id>/memories` 子樹。Actor-peer 召回同時包含使用者共享記憶和當前 peer 記憶；切換 scope 不會搬遷已有記憶。

## assemble 如何組裝上下文

外掛佔用 OpenClaw 的 `contextEngine` 槽位。會話歷史、長期記憶召回和本輪新輸入分別處理；`assemble()` 返回供本次模型請求使用的上下文，不把組裝出的摘要或召回內容持久化到 OpenClaw 的 session transcript，也不通過該呼叫向 OV session 追加訊息。宿主可以用返回的 messages 更新本輪記憶體狀態，這與寫入持久化對話記錄不同。

主 assemble 在每輪新輸入開始執行時準備歷史上下文。外掛通過引數中是否包含 `prompt`、`availableTools`、`citationsMode` 中任一欄位識別該呼叫。

### 主 assemble：歷史和當前輸入分開

主分支呼叫 `getSessionContext(tokenBudget)`，用返回的內容構造：

```text
summaryMessage = { role: "user", content: "[Session History Summary]\n" + latest_archive_overview }
messages = [summaryMessage] + OV active messages
systemPromptAddition = Session Context Guide（有歸檔時）+ 本輪召回結果（有命中時）
```

`latest_archive_overview` 是服務端返回的摘要正文，`[Session History Summary]` 是外掛加在正文前的固定文本標題。僅在 overview 非空時插入這條合成 user 訊息；active messages 保留近期未壓縮對話。當前 `prompt` 由宿主加入本輪；外掛只用它查詢記憶，不把它重複追加到返回的歷史中。召回結果屬於本次請求的上下文，不直接作為新對話寫回 OV。

overview 由 OV 服務端的工作記憶流程生成，外掛讀取結果。服務端先為 active messages 分配預算，剩餘空間不足時不返回 overview；`pre_archive_abstracts` 當前為空陣列。因此返回結果不是完整歸檔索引，需要原始細節時通過 `ov_archive_search` 查詢歸檔。

外掛為模型輸出預留 token 空間，扣除使用指南和摘要的實際估算量，再從 active messages 頭部裁掉超預算內容，並整理工具呼叫/結果等 provider 訊息格式。摘要不會按外掛計算出的 archive 預算硬截斷，因此這些預算不能當作各層的嚴格配額；新增召回塊若使總估算量超過 `tokenBudget`，該塊會被省略。

OV 無資料、無歸檔且訊息數少於宿主輸入、轉換後為空或讀取失敗時，歷史分支回退到宿主 messages。即使歷史透傳，只要有合法 `prompt` 且啟用了 `autoRecall`，主分支仍可嘗試召回。召回無命中或失敗不會阻止對話。

### transformContext

`transformContext` 在每次 LLM 呼叫前執行，無論最後一條訊息是 user message 還是 tool response。該 hook 在 OV 整合中的最佳使用方式暫未明確。

### 捕獲和壓縮

- `ingest()` / `ingestBatch()` 不寫入訊息。常規捕獲通過 `afterTurn`；外掛對 OpenClaw 2026.9.3 及之後的穩定版本支援由 `commitTurn` 接收宿主交付的已結束輪次，舊版和獨立 runner 使用 `afterTurn`。無法識別版本時，`commitTurn` 拒絕確認，避免確認未捕獲的資料。
- 捕獲邏輯清洗注入內容、轉換文本和工具訊息，再寫入 OV session。達到 `pending_tokens >= tokenBudget × commitTokenThresholdRatio` 時，發起非同步 session commit；預設比例為 `0.5`，預設保留最近 `10` 條訊息，也可選 `turn_budget` 保留策略。`pending_tokens` 是服務端按保留策略計算的待歸檔訊息 token 數，不是整個模型請求的 token 數。
- `ownsCompaction: true` 表示外掛負責壓縮。正常 `compact()` 提交 OV session（`wait=true`、保留數為 `0`），讀取 overview 作為壓縮摘要；下一次主 assemble 用摘要和 active messages 重建歷史。被 bypass 的會話嘗試委託宿主壓縮器，宿主 bridge 不可用時返回跳過。

這裡的 **session commit** 負責會話歸檔和記憶處理，與儲存資源檔案版本的 [snapshot commit](../guides/15-snapshot.md) 是不同操作。

## 驗證

```bash
openclaw openviking status
```

一鍵檢查外掛註冊、服務端連通性和版本相容性。追加 `--json` 獲取機器可讀結果。

<details>
<summary><b>手動驗證</b></summary>

確認外掛佔用了 `contextEngine` 槽位：

```bash
openclaw config get plugins.slots.contextEngine
# 期望輸出：openviking
```

全鏈路健康檢查：

```bash
python examples/openclaw-plugin/health_check_tools/ov-healthcheck.py
```

詳見 [HEALTHCHECK.md](https://github.com/volcengine/OpenViking/blob/main/examples/openclaw-plugin/health_check_tools/HEALTHCHECK.md)。

</details>

<details>
<summary><b>配置</b></summary>

外掛配置位於 `plugins.entries.openviking.config`，通常 setup 已經寫好。

| 引數 | 預設值 | 含義 |
| --- | --- | --- |
| `baseUrl` | `http://127.0.0.1:1933` | OpenViking 服務端點 |
| `apiKey` | 空 | OpenViking API Key |
| `peer_role` | `none` | `none`、`assistant` 或 `sender`；舊值 `person` 作為 `sender` 的別名相容 |
| `peer_prefix` | 空 | `peer_role=assistant` 時 assistant peer 身份的可選字首 |
| `autoRecallTimeoutMs` | `5000` | 整個 auto-recall 流程的外層超時（毫秒）；本地嵌入硬體較慢時可調大（取值範圍 1000–300000） |

```bash
openclaw config set plugins.entries.openviking.config.baseUrl http://your-server:1933
openclaw config set plugins.entries.openviking.config.apiKey your-api-key
```

</details>

## 解除安裝

```bash
curl -fsSL https://raw.githubusercontent.com/volcengine/OpenViking/main/examples/openclaw-plugin/upgrade_scripts/uninstall-openclaw-plugin.sh -o uninstall-openviking.sh
bash uninstall-openviking.sh
```

## 參見

- [整合能力參考](./16-capability-reference.md)
- [完整安裝指南](https://github.com/volcengine/OpenViking/blob/main/examples/openclaw-plugin/INSTALL.md) — 所有安裝路徑與引數
- [外掛設計說明](https://github.com/volcengine/OpenViking/blob/main/examples/openclaw-plugin/README.md) — 架構、身份與路由、hook 生命週期
- [Agent 操作指南](https://github.com/volcengine/OpenViking/blob/main/examples/openclaw-plugin/INSTALL-AGENT.md) — 給代使用者執行安裝的 agent 看
