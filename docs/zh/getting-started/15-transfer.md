# 匯入匯出

將一份資料目錄匯出為 OVPack，再匯入到新的父目錄或另一套 OpenViking 服務，核對檔案、後設資料和檢索結果。

<a id="連線實驗帳號"></a>

## 連線服務

使用管理員提供的使用者或管理員 API Key 配置 CLI，連線 OpenViking 服務。OVPack 匯入匯出要求服務端啟用 API Key 認證，並配置 `server.root_api_key`。

如需在本機搭建服務，可使用獨立的配置檔案和儲存目錄，配置模型，將 `server.auth_mode` 設為 `api_key`，並設定 `server.root_api_key`。啟動服務並建立帳號後，將返回的 `user_key` 填入 CLI 連線配置。具體步驟見[API Key 配置](../guides/04-authentication.md#方案一-api-key)和 [CLI 入門](05-cli-setup.md)。使用新帳號時，先在該帳號下匯入下方樣例資料。

## 準備來源

連線服務後，先完成[資料檢索](08-resources.md#準備資料)中的匯入步驟。本例來源為 `viking://resources/onboarding-zh-v1`，需要來源讀許可權和目標父目錄寫許可權。

```bash
ov tree viking://resources/onboarding-zh-v1
ov export viking://resources/onboarding-zh-v1 ./lighthouse.ovpack
```

`lighthouse.ovpack` 是所選目錄的內容包，包含原始檔、語義側邊檔案和可遷移索引標量。本頁使用預設匯出方式，匯入時重新生成向量，會呼叫目標服務的 Embedding 模型。全帳號備份與恢復見 [OVPack 參考](../api/14-ovpack.md)。

## 匯入新位置

```bash
ov mkdir viking://resources/onboarding-transfer-v1
ov import ./lighthouse.ovpack viking://resources/onboarding-transfer-v1 --vector-mode recompute
```

第二個引數是**目標父目錄**。儲存返回的實際 root URI，並用它執行下一步。本例通常得到 `viking://resources/onboarding-transfer-v1/onboarding-zh-v1`。

預設衝突策略為 `fail`。若目標 root 已存在，可以選擇新的演示父目錄；`overwrite` 會替換已有 root，`skip` 會保留已有 root。使用重複演示時的新目錄，便於比較前後結果。

## 核對內容和索引

```bash
ov tree viking://resources/onboarding-transfer-v1/onboarding-zh-v1
ov read viking://resources/onboarding-transfer-v1/onboarding-zh-v1/project/project.md
ov read viking://resources/onboarding-transfer-v1/onboarding-zh-v1/meeting/meeting.md
ov wait
```

核對四份原始檔的相對路徑、正文，以及包內保留的摘要和概覽。匯入返回後向量處理可能仍在進行，使用 `ov wait` 等待佇列處理。它也可能等待服務中的其他排隊工作；如果請求超時，可用 `ov status` 檢查狀態後稍後再試。確認處理完成且無相關錯誤後，再檢索資料。

```bash
ov find "燈塔試點開始前要準備什麼？" --uri viking://resources/onboarding-transfer-v1/onboarding-zh-v1
```

完成標誌是檔案內容一致、必要後設資料可讀取，並能在新目錄檢索到相關資料。檢索排名與分數會受目標模型及索引配置影響，核對重點是返回內容能否支援問題。

<a id="從-a-服務遷移到-b-服務"></a>

## 資料服務間遷移

例如，將開發環境 A 中的燈塔資料遷移到測試環境 B。資料通過執行 CLI 的電腦中轉：從 A 下載 `.ovpack` 檔案，再將該檔案上傳到 B，兩套服務之間無需直接連通。

本例遷移選定的資料目錄，A 中的原資料會保留。B 的模型、帳號和訪問憑據需要單獨配置；整帳號備份與恢復見 [OVPack 參考](../api/14-ovpack.md)。

### 配置兩個連線

準備兩套支援 OVPack 的服務，認證要求與上文一致。A 的帳號需要來源讀許可權，B 的帳號需要目標父目錄寫許可權，B 還需配置可用的 Embedding 模型。遷移前確認 B 支援 A 匯出的包格式；匯出期間暫停對該樣例目錄的修改，便於核對內容。

在本機同一個工作目錄中建立兩個 CLI 配置檔案，分別填寫實際服務地址和對應帳號的 API Key。下面的地址僅作示例：

`ov-a.conf`：

```json
{
  "url": "https://openviking-a.example.com",
  "api_key": "your-service-a-user-key"
}
```

`ov-b.conf`：

```json
{
  "url": "https://openviking-b.example.com",
  "api_key": "your-service-b-user-key"
}
```

在 macOS / Linux 終端中，通過 `OPENVIKING_CLI_CONFIG_FILE` 為每條命令指定連線。先限制配置檔案的讀取許可權，再檢查兩套服務是否可訪問：

```bash
chmod 600 ./ov-a.conf ./ov-b.conf
OPENVIKING_CLI_CONFIG_FILE=./ov-a.conf ov health
OPENVIKING_CLI_CONFIG_FILE=./ov-b.conf ov health
```

後續命令都在這個工作目錄中執行。配置檔案包含訪問憑據，請儲存在本機受控位置。

### 從 A 匯出

確認 A 中已匯入[燈塔資料](08-resources.md#準備資料)，然後將目錄下載到本機：

```bash
OPENVIKING_CLI_CONFIG_FILE=./ov-a.conf ov tree viking://resources/onboarding-zh-v1
OPENVIKING_CLI_CONFIG_FILE=./ov-a.conf ov export viking://resources/onboarding-zh-v1 ./lighthouse-a-to-b.ovpack
```

命令成功後，當前目錄中會生成 `lighthouse-a-to-b.ovpack`。如果改用另一臺電腦連線 B，將這個檔案傳到該電腦即可；A 的連線憑據留在原電腦上。

### 匯入到 B

在 B 中建立一個新的遷移父目錄，再匯入本地包：

```bash
OPENVIKING_CLI_CONFIG_FILE=./ov-b.conf ov mkdir viking://resources/from-a-v1
OPENVIKING_CLI_CONFIG_FILE=./ov-b.conf ov import ./lighthouse-a-to-b.ovpack viking://resources/from-a-v1 --on-conflict fail --vector-mode recompute
```

這裡使用 `recompute`，由 B 的 Embedding 模型重新生成向量，適用於兩套環境模型配置不同的情況。匯入會呼叫 B 的模型併產生相應開銷。若目標 root 已存在，選擇新的父目錄後重試。

記錄返回的實際 root URI；本例通常為 `viking://resources/from-a-v1/onboarding-zh-v1`。下方命令以這個 URI 為例。

### 在 B 核對結果

先檢查目錄與正文，再等待 B 的後臺向量處理：

```bash
OPENVIKING_CLI_CONFIG_FILE=./ov-b.conf ov tree viking://resources/from-a-v1/onboarding-zh-v1
OPENVIKING_CLI_CONFIG_FILE=./ov-b.conf ov read viking://resources/from-a-v1/onboarding-zh-v1/project/project.md
OPENVIKING_CLI_CONFIG_FILE=./ov-b.conf ov wait
```

`ov wait` 等待佇列處理，也可能受 B 中其他排隊工作的影響。如果請求超時，檢視 B 的狀態：

```bash
OPENVIKING_CLI_CONFIG_FILE=./ov-b.conf ov status
```

仍在處理時稍後再次等待；出現錯誤時檢查 B 的模型與儲存配置及服務端日誌。確認處理完成且無相關錯誤後，在 B 中檢索：

```bash
OPENVIKING_CLI_CONFIG_FILE=./ov-b.conf ov find "燈塔試點開始前要準備什麼？" --uri viking://resources/from-a-v1/onboarding-zh-v1
```

| 核對項 | 通過條件 |
| --- | --- |
| 檔案與正文 | B 中四份原始檔的相對路徑和正文與 A 一致 |
| 摘要與概覽 | 包內保留的語義側邊檔案在 B 中可讀取 |
| 檢索結果 | 能找到試點準備相關資料，並讀取結果 URI 對應的原文 |
| 引用與接入 | 正文中的絕對 URI、服務地址及 Agent 的檢索範圍已按 B 的實際位置核對 |

核對完成後，將應用或 Agent 的服務地址、憑據和資料檢索範圍改為 B 的配置，再用同一個問題驗證回答及來源。這樣可以確認應用已經使用 B 中的資料。A 的原目錄可繼續保留，用於比對和後續切換安排。

## 包與衝突檢查

OVPack 的 manifest 記錄檔案集合、大小和校驗資訊。缺失檔案、校驗不符或不支援的格式版本會使匯入失敗，此時可以重新匯出並核對包的傳輸過程。向量相容性、`auto`/`require` 模式及歸檔校驗規則見 [OVPack 參考](../api/14-ovpack.md)。

實驗完成後，可保留包作比對；清理時在 Studio 中確認新父目錄下的匯入 root，再刪除演示內容，原來源目錄繼續可用。
