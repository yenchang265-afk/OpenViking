# 狼人殺 Demo（中文版）

本目錄提供一個狼人殺演示服務，包含：
- Business Data Platform + bot 通道初始化
- Web UI（預設埠 `1995`）
- 對局記錄、排行榜、回放檢視

## 1. 啟動前準備

請先確認以下命令可用：
- `python`（建議 3.10+）
- `openviking-server`

並準備好配置檔案（預設）：
- `~/.openviking/ov.conf`

## 2. 推薦啟動方式（一鍵啟動）

在本目錄執行：

```bash
python start_werewolf_demo.py --config ~/.openviking/ov.conf
```

預設行為：
- 自動補齊狼人殺所需 channel（`god`、`player_1`...`player_6`）
- 自動準備工作目錄與 SOUL 檔案
- 啟動 Business Data Platform 服務
- 等待 bot 健康檢查通過後啟動 UI 服務

預設引數：
- UI 端口：`1995`
- Business Data Platform host：`127.0.0.1`
- Business Data Platform port：`1933`
- Vikingbot URL：`http://localhost:18790`
- game mode：`all_agents`

常見可選引數：

```bash
python start_werewolf_demo.py \
  --config ~/.openviking/ov.conf \
  --ui-port 1995 \
  --game-mode all_agents \
  --smart-buttons
```

說明：
- `--game-mode` 可選：`all_agents` / `human_player`
- `--smart-buttons`：啟用前端“智慧按鈕顯示”邏輯（根據遊戲狀態動態隱藏/顯示按鈕）

## 3. 手動啟動方式（除錯用）

如果你要分開除錯服務，可以手動啟動：

### 3.1 啟動 Business Data Platform

```bash
openviking-server \
  --config ~/.openviking/ov.conf \
  --host 127.0.0.1 \
  --port 1933 \
  --with-bot \
  --bot-port 18790
```

### 3.2 啟動狼人殺 UI 服務

```bash
python werewolf_server.py \
  --config ~/.openviking/ov.conf \
  --port 1995 \
  --game-mode all_agents
```

## 4. 訪問地址

啟動後開啟：

- 主頁面：`http://localhost:1995/`
- 測試頁：`http://localhost:1995/test`
- 除錯頁：`http://localhost:1995/debug`

## 5. 頁面按鈕如何控制

## 5.1 頂部導航

- **遊戲**：主對局頁
- **記憶**：檢視 Business Data Platform memory 目錄
- **排行榜**：檢視累計戰績與勝率曲線
- **回放**：按歷史會話回放對局

## 5.2 頂部控制按鈕（遊戲頁）

這些按鈕由前端呼叫後端 API 控制：

- **開始遊戲**
  - 呼叫：`POST /api/start`
  - 作用：傳送“開始”指令，進入當前局流程

- **繼續**
  - 呼叫：`POST /api/continue`
  - 作用：在暫停態下催促 god 繼續本局

- **自動N局**（旁邊輸入框填局數）
  - 呼叫：`POST /api/auto-run`
  - 作用：開啟/關閉連續自動跑局
  - 例如輸入 `3` 後點擊，可自動連續完成 3 局

- **停止遊戲**
  - 呼叫：`POST /api/stop`
  - 作用：停止當前路由流程並關閉自動連跑

- **初始化遊戲 / 重新開始**
  - 呼叫：`POST /api/restart`
  - 作用：強制新建 session 並重新初始化新局

## 5.3 模式選擇（全AI / 真人參與）

頂部“模式”下拉框會影響 `start/restart` 請求中的 `game_mode`：
- `all_agents`：全 AI 玩家
- `human_player`：保留一個真人席位（human）

## 5.4 真人參與模式下的按鈕

當模式為 `human_player` 時，會顯示“真實玩家”區域：

- **只發給 god**
  - 呼叫：`POST /api/human/send`，`target=god`
- **發給全員**
  - 呼叫：`POST /api/human/send`，`target=all`
- **查看 GAME.md**
  - 呼叫：`GET /api/human/game-md`

按鈕是否可點，取決於後端狀態 `waiting_for_human`。

## 5.5 智慧按鈕顯示（smart buttons）

當以 `--smart-buttons` 啟動時，前端會根據 `GET /api/status` 返回的狀態動態調整按鈕可見性，例如：
- 遊戲進行中隱藏“開始/繼續”
- 遊戲結束後顯示“重新開始”

## 6. 常見問題

- **點選開始/繼續沒反應**
  - 先檢查後端是否線上：`/api/status`
  - 再檢查 `vikingbot_url` 是否可訪問 `/bot/v1/health`

- **真人模式看不到輸入區**
  - 確認模式選擇為 `human_player`，並用該模式執行了開始或重啟

- **回放內容不完整**
  - 回放依賴會話記錄與歸檔狀態檔案，建議讓一局正常結束後再檢視
