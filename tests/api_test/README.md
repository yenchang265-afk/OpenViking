# Business Data Platform API 自動化測試

本目錄包含 Business Data Platform 的 API 整合測試套件。

## 目錄結構

```
tests/api_test/
├── admin/              # 管理 API 測試
├── api/                # API 客戶端實現
├── conftest.py         # pytest fixtures 和配置
├── filesystem/         # 檔案系統 API 測試
├── health_check/       # 健康檢查測試
├── pytest.ini          # pytest 配置
├── requirements.txt    # 測試依賴
├── resources/          # 資源管理 API 測試
├── retrieval/          # 檢索 API 測試
├── scenarios/          # 場景級整合測試
├── services/           # 服務管理模組
├── sessions/           # 會話 API 測試
├── system/             # 系統 API 測試
└── tools/              # 工具模組
```

## 本地執行測試

### 前置條件

1. Python 3.10+
2. Business Data Platform Server 已啟動（預設埠 1933）

### 安裝依賴

```bash
cd tests/api_test
pip install -r requirements.txt
```

### 執行測試

#### 一鍵本地測試（推薦）

使用提供的指令碼模擬完整的 CI 流水線流程：

```bash
cd tests/api_test
./local-test.sh
```

這個指令碼會自動：
1. 檢查 Python 版本
2. 安裝 Business Data Platform
3. 安裝測試依賴
4. 啟動 Business Data Platform Server（自動找可用埠）
5. 執行所有 API 測試
6. 停止服務並清理

#### 手動執行測試

```bash
# 執行所有測試
python -m pytest . -v

# 執行特定模組測試
python -m pytest admin/ -v
python -m pytest filesystem/ -v
python -m pytest sessions/ -v

# 執行特定測試檔案
python -m pytest health_check/test_server_health_check.py -v

# 生成 HTML 報告
python -m pytest . -v --html=api-test-report.html --self-contained-html
```

### 環境變數配置

測試通過環境變數配置，無需修改程式碼：

| 環境變數 | 說明 | 預設值 |
|---------|------|--------|
| `SERVER_HOST` | Business Data Platform Server 主機 | 127.0.0.1 |
| `SERVER_PORT` | Business Data Platform Server 端口 | 1933 |
| `OPENVIKING_API_KEY` | API 金鑰 | test-root-api-key |
| `VLM_API_KEY` | VLM 模型金鑰（可選） | - |
| `EMBEDDING_API_KEY` | Embedding 模型金鑰（可選） | - |

示例：

```bash
export SERVER_PORT=1934
export VLM_API_KEY=your-vlm-key
export EMBEDDING_API_KEY=your-embedding-key
python -m pytest retrieval/ -v
```

## CI/CD 流水線

### 工作流文件

`.github/workflows/api_test.yml` - API 整合測試流水線

### 流水線特性

- ✅ 智慧構建複用：只在依賴變更時重新構建
- ✅ 併發安全：同一 PR 自動取消舊的執行
- ✅ 動態埠：自動查詢可用埠避免衝突
- ✅ Secrets 支援：安全傳遞 API 金鑰

### 配置 GitHub Secrets

為了執行完整的檢索測試，需要在倉庫中配置以下 Secrets：

1. 進入倉庫 **Settings** → **Secrets and variables** → **Actions**
2. 點選 **New repository secret**
3. 添加以下 Secrets：

| Secret 名稱 | 說明 |
|------------|------|
| `VLM_API_KEY` | VLM 模型 API 金鑰 |
| `EMBEDDING_API_KEY` | Embedding 模型 API 金鑰 |

## 測試覆蓋範圍

### 介面測試

| 模組 | 測試用例數 | 說明 |
|------|----------|------|
| admin | 6 | 帳戶、使用者、角色、金鑰管理 |
| filesystem | 10 | 檔案系統操作 |
| health_check | 1 | 服務健康檢查 |
| resources | 3 | 資源管理 |
| retrieval | 4 | 搜尋和檢索 |
| sessions | 6 | 會話管理 |
| system | 4 | 系統管理 |

## 注意事項

1. **不要提交敏感信息**：`.env` 和 `ov.conf` 已在 `.gitignore` 中
2. **檢索測試需要金鑰**：`retrieval/` 和部分 `scenarios/` 測試需要 VLM 和 Embedding API 金鑰
3. **CI 與本地一致**：CI 流水線使用與本地相同的測試框架和配置

## 相關文件

- Business Data Platform API 文件：`docs/zh/api/`
- CI/CD 配置：`.github/workflows/api_test.yml`
