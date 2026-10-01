# OpenClaw - OpenViking 端到端自動化測試

OpenClaw 和 OpenViking 端到端自動化測試框架，用於驗證記憶讀寫、增刪改查等場景。

## 📋 前置條件

在使用本專案之前，請確保已完成以下準備工作：

### 1. 安裝 OpenClaw

確保已在本地安裝 OpenClaw：

```bash
# 驗證 OpenClaw 安裝
openclaw --version
```

### 2. 安裝 OpenViking 外掛

確保已安裝 OpenViking 外掛並正確配置：

```bash
# 檢查已安裝的外掛
openclaw plugins list
```

### 3. （可選）配置 OpenClaw HTTP 通訊

**注意：本專案推薦使用 OpenClaw CLI 方式（預設），更加穩定可靠。**

如果需要使用 HTTP API 方式，請在 OpenClaw 的配置檔案 `~/.openclaw/openclaw.json` 中新增或修改以下配置：

```json
{
  "gateway": {
    "http": {
      "endpoints": {
        "responses": {
          "enabled": true
        }
      }
    }
  }
}
```

配置後重啟 OpenClaw Gateway：

```bash
openclaw gateway restart
```

### 4. 啟動 OpenClaw 服務

確保 OpenClaw Gateway 正在執行：

```bash
# 檢查服務狀態
openclaw gateway status

# 如果未執行，啟動服務
openclaw gateway
```

## 🚀 快速開始（推薦：使用 CLI 方式）

### 方法一：使用快速指令碼（推薦）

```bash
# 1. 設定環境（自動建立虛擬環境並安裝依賴）
./setup.sh

# 2. 執行測試（帶報告生成，使用 CLI 方式）
./run.sh -r
```

### 方法二：手動設定

```bash
# 1. 建立虛擬環境
python -m venv venv

# 2. 啟用虛擬環境
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate     # Windows

# 3. 安裝依賴
pip install -r requirements.txt
pip install pytest-html

# 4. 執行測試（使用 CLI 方式，推薦）
pytest test_cli_pytest.py -v --html=reports/test_report.html --self-contained-html
```

## 📁 專案結構

```
oc2ov_test/
├── config/                 # 配置檔案目錄
│   ├── __init__.py
│   └── settings.py         # 專案配置
├── tests/                  # 測試用例目錄
│   ├── __init__.py
│   ├── base_test.py        # 測試基類（HTTP 方式）
│   ├── base_cli_test.py    # 測試基類（CLI 方式，推薦）
│   ├── p0/                 # P0 質量保障類測試
│   ├── crud/               # CRUD 操作測試
│   └── complex/            # 複雜場景測試
├── utils/                  # 工具函式目錄
│   ├── __init__.py
│   ├── openclaw_client.py  # OpenClaw HTTP 客戶端封裝
│   ├── openclaw_cli_client.py  # OpenClaw CLI 客戶端封裝（推薦）
│   ├── logger.py           # 日誌工具
│   └── assertions.py       # 斷言工具（關鍵詞匹配、文本相似度）
├── logs/                   # 日誌目錄
├── reports/                # 測試報告目錄
├── venv/                   # Python 虛擬環境（自動建立）
├── conftest.py             # Pytest 配置（報告美化）
├── test_cli_pytest.py      # Pytest 測試入口（CLI 方式，推薦）
├── test_pytest.py          # Pytest 測試入口（HTTP 方式）
├── test_cli_single.py      # 單個 CLI 請求測試
├── quick_test.py           # 快速測試指令碼
├── run_tests.py            # 測試執行入口
├── setup.sh                # 快速環境設定指令碼
├── run.sh                  # 快速測試執行指令碼
├── requirements.txt        # Python 依賴
├── pyproject.toml          # 專案配置檔案
├── README.md               # 專案說明
└── ASSERTIONS_GUIDE.md     # 斷言使用詳細指南
```

## ⚙️ 配置說明

配置檔案位於 `config/settings.py`，主要配置項：

```python
OPENCLAW_CONFIG = {
    "url": "http://127.0.0.1:18789/v1/responses",
    "auth_token": "Bearer YOUR_AUTH_TOKEN_HERE",  # 請替換為您自己的認證token
    "agent_id": "main",
    "model": "YOUR_MODEL_NAME_HERE",  # 請替換為您自己的模型名稱
    "timeout": 120
}

TEST_CONFIG = {
    "wait_time": 10,  # 等待記憶同步的時間（秒）
    "log_dir": os.path.join(BASE_DIR, "logs"),
    "report_dir": os.path.join(BASE_DIR, "reports")
}
```


## 🧪 執行測試

### 推薦：使用 CLI 方式（更穩定）

```bash
# 執行全部 CLI 測試（帶報告）
pytest test_cli_pytest.py -v --html=reports/test_report_cli.html --self-contained-html

# 執行單個 CLI 測試
pytest test_cli_pytest.py::TestMemoryWriteGroupA::test_memory_write_basic_info -v

# 快速測試單個 CLI 請求
python test_cli_single.py
```

### 使用 HTTP 方式

```bash
# 執行全部 HTTP 測試
pytest test_pytest.py -v --html=reports/test_report.html --self-contained-html
```

### 使用快速指令碼

```bash
# 檢視幫助
./run.sh -h

# 執行全部測試（帶報告）
./run.sh -r

# 僅執行 P0 級測試
./run.sh -p

# 僅執行 CRUD 操作測試
./run.sh -c

# 僅運行復雜場景測試
./run.sh -x

# 詳細輸出模式
./run.sh -v

# 組合使用：詳細輸出 + 生成報告
./run.sh -v -r
```

## 📊 檢視測試報告

測試報告生成在 `reports/` 目錄下，可以直接在瀏覽器中開啟：

```bash
# macOS
open reports/test_report_cli.html

# Linux
xdg-open reports/test_report_cli.html

# Windows
start reports/test_report_cli.html
```

報告包含：
- 📊 環境資訊（OpenClaw 版本、OpenViking 狀態等）
- 📝 詳細的中文測試描述
- 📈 測試執行結果和日誌
- ✅ 通過/失敗的測試用例統計

## ✅ 斷言功能

專案提供了多種斷言方式來驗證 OpenClaw 的響應：

### 1. 關鍵詞斷言

```python
# 驗證響應中包含所有關鍵詞
self.assertKeywordsInResponse(
    response,
    ["小明", "30歲", "測試開發"],
    require_all=True
)
```

### 2. 任意關鍵片語斷言

```python
# 驗證響應中包含任意一組中的任意一個關鍵詞
self.assertAnyKeywordInResponse(
    response,
    [["小明", "小紅"], ["30", "25"]]
)
```

### 3. 文本相似度斷言

```python
# 驗證響應文本與期望文本的相似度
self.assertSimilarity(
    response,
    "你叫小明，今年30歲",
    min_similarity=0.7
)
```

**詳細使用指南請檢視：[ASSERTIONS_GUIDE.md](./ASSERTIONS_GUIDE.md)**

## 📝 測試用例說明

### P0 質量保障類測試

- `TestMemoryWriteGroupA` - 測試組A（小明）：基本記憶結構化寫入驗證
- `TestMemoryWriteGroupB` - 測試組B（小紅）：多維度豐富資訊寫入

### CRUD 操作測試

- `TestMemoryRead` - 記憶讀取驗證
- `TestMemoryUpdate` - 記憶更新驗證
- `TestMemoryDelete` - 記憶刪除驗證

### 複雜場景測試

- `TestComplexScenarioMultiUsers` - 多使用者切換場景
- `TestComplexScenarioIncrementalInfo` - 增量信息添加
- `TestComplexScenarioSpecialCharacters` - 特殊字元和邊界情況

## 🔧 擴充新測試用例

1. 在 `tests/` 相應目錄下建立新的測試檔案
2. 繼承 `BaseOpenClawCLITest` 基類（推薦使用 CLI 方式）
3. 使用 `self.send_and_log()` 傳送訊息
4. 使用 `self.wait_for_sync()` 等待記憶同步
5. 使用斷言方法驗證響應
6. 在 `test_cli_pytest.py` 中新增到測試套件中

示例：

```python
from tests.base_cli_test import BaseOpenClawCLITest

class TestMyNewFeature(BaseOpenClawCLITest):
    """
    測試目標：我的新功能驗證
    測試場景：描述測試場景
    """
    
    def test_something(self):
        """測試場景：具體場景描述"""
        self.logger.info("開始測試")
        self.send_and_log("我叫測試使用者")
        self.wait_for_sync()
        
        # 驗證響應
        response = self.send_and_log("我是誰")
        self.assertKeywordsInResponse(response, ["測試使用者"])
```

## 📋 日誌

測試執行日誌儲存在 `logs/test_run.log`

## ⚠️ 注意事項

1. **會話管理**：使用 CLI 方式時，每個測試類會使用獨立的 `session-id`，避免會話衝突
2. **等待時間**：根據實際情況調整 `config/settings.py` 中的 `wait_time`，確保記憶同步完成
3. **超時設定**：CLI 客戶端預設超時為 300 秒，可根據需要調整
4. **服務狀態**：確保 OpenClaw Gateway 正常執行，測試前可使用 `openclaw gateway status` 檢查
5. **會話鎖定**：如果遇到 "session file locked" 錯誤，請檢查是否有其他程序在使用相同的 session-id

## 🐛 故障排查

### 問題：每次傳送訊息後需要重啟服務

**解決方案**：使用 CLI 方式代替 HTTP API 方式，CLI 方式支援 `--session-id` 引數，可以保持會話連續性。

### 問題：測試超時

**解決方案**：
1. 增加 `config/settings.py` 中的 `timeout` 值
2. 增加 `wait_time` 等待時間
3. 檢查 OpenClaw 服務是否正常執行

### 問題：會話檔案鎖定

**解決方案**：
1. 檢查是否有其他測試程序在執行
2. 嘗試使用不同的 session-id
3. 重啟 OpenClaw Gateway

## 🐍 虛擬環境說明

專案使用 Python 虛擬環境來隔離依賴：

- `venv/` - 虛擬環境目錄（已新增到 .gitignore）
- `setup.sh` - 一鍵設定環境指令碼
- `run.sh` - 一鍵執行測試指令碼

建議始終在虛擬環境中執行測試，避免依賴衝突。
