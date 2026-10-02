# Business Data Platform 解析器兩層架構重構

> 本文是 Accessor / Parser 兩層拆分的歷史重構記錄。當前 `add_resource` 的完整入口分流、Understanding、Connector 與非同步執行規則，見 [新增資源後的解析路由](./resource-ingestion-routing.md)。

| 專案 | 資訊 |
|-----|------|
| 狀態 | `已完成` |
| 建立日期 | 2026-04-13 |
| 完成日期 | 2026-04-14 |

---

## 概述

將原有的單一層 Parser 架構拆分為 **Accessor（資料訪問層）** 和 **Parser（資料解析層）** 兩層，實現職責分離和程式碼複用。

---

## 目錄

- [背景與問題](#背景與問題)
- [架構設計](#架構設計)
- [核心抽象](#核心抽象)
- [實現進度](#實現進度)
- [檔案結構](#檔案結構)

---

## 背景與問題

### 當前架構的問題

| 問題 | 說明 |
|-----|------|
| 平鋪式註冊 | 所有 Parser 在同一層級，職責不清晰 |
| 字尾衝突 | `.zip` 可被 `CodeRepositoryParser` 和 `ZipParser` 同時處理 |
| URL 處理邏輯分散 | `UnifiedResourceProcessor._process_url()` 和 `ParserRegistry.parse()` 都有 URL 檢測 |
| 職責混合 | 部分 Parser 既負責下載又負責解析 |

### 重構目標

1. **職責分離**：資料獲取 ≠ 資料解析
2. **程式碼複用**：HTTP/Git 下載邏輯可被多個 Parser 複用
3. **易於擴充**：新增資料來源只需新增 Accessor
4. **解決衝突**：通過優先順序機制解決 `.zip` 等字尾衝突

---

## 架構設計

### 兩層架構

| 層級 | 抽象介面 | 職責 | 示例 |
|-----|---------|------|------|
| **L1: Accessor** | `DataAccessor` | 獲取資料：遠端 URL / 特殊路徑 → 本地檔案/目錄 | `GitAccessor`, `HTTPAccessor`, `LocalAccessor` |
| **L2: Parser** | `BaseParser` | 解析資料：本地檔案/目錄 → `ParseResult` | `MarkdownParser`, `PDFParser`, `ZipParser` |

### 呼叫流程

```
add_resource(path)
    ↓
ResourceProcessor.process_resource()
    ↓
UnifiedResourceProcessor.process()
    ↓
┌─────────────────────────────────────────┐
│  第一階段：資料訪問 (Accessor Layer)     │
├─────────────────────────────────────────┤
│  AccessorRegistry.route(source)         │
│    ├─→ GitAccessor    (priority: 80)   │
│    ├─→ HTTPAccessor   (priority: 50)   │
│    └─→ LocalAccessor  (priority: 10)   │
│         ↓                                │
│  返回: LocalResource                     │
│         (本地路徑 + 後設資料)              │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│  第二階段：資料解析 (Parser Layer)       │
├─────────────────────────────────────────┤
│  ParserRegistry.route(local_resource)   │
│    ├─→ 是目錄? → DirectoryParser        │
│    ├─→ 是檔案? → 按副檔名匹配           │
│    │     ├─→ .md  → MarkdownParser     │
│    │     ├─→ .pdf → PDFParser          │
│    │     ├─→ .zip → ZipParser          │
│    │     └─→ ...                        │
│    └─→ 返回: ParseResult                │
└─────────────────────────────────────────┘
                    ↓
TreeBuilder + SemanticQueue (保持不變)
```

---

## 核心抽象

### 1. LocalResource（資料類）

位置：`openviking/parse/accessors/base.py`

表示一個可在本地訪問的資源，是 Accessor 層的輸出。

```python
@dataclass
class LocalResource:
    path: Path                    # 本地檔案/目錄路徑
    source_type: str              # 原始來源型別 (SourceType.GIT/HTTP/LOCAL)
    original_source: str           # 原始 source 字符串
    meta: Dict[str, Any]          # 後設資料（repo_name, branch, content_type 等）
    is_temporary: bool = True      # 是否為臨時檔案，解析後可清理

    def cleanup(self) -> None     # 清理臨時資源
    def __enter__/__exit__         # 支持上下文管理器
```

### 2. DataAccessor（抽象基類）

位置：`openviking/parse/accessors/base.py`

```python
class DataAccessor(ABC):
    @abstractmethod
    def can_handle(self, source: Union[str, Path]) -> bool
        """判斷是否能處理該來源"""

    @abstractmethod
    async def access(self, source: Union[str, Path], **kwargs) -> LocalResource
        """獲取資料到本地，返回 LocalResource"""

    @property
    @abstractmethod
    def priority(self) -> int
        """優先順序：數字越大優先順序越高
           - 80: 版本控制 (Git)
           - 50: 通用協議 (HTTP)
           - 10: 兜底 (Local)
        """

    def cleanup(self, resource: LocalResource) -> None
        """清理資源（預設呼叫 resource.cleanup()）"""
```

### 3. AccessorRegistry

位置：`openviking/parse/accessors/registry.py`

```python
class AccessorRegistry:
    def __init__(self, register_default: bool = True)
        """初始化登錄檔，可選是否註冊預設 Accessor"""

    def register(self, accessor: DataAccessor) -> None
        """註冊 Accessor（按優先順序降序插入）"""

    def unregister(self, accessor_name: str) -> bool
        """登出 Accessor"""

    def get_accessor(self, source) -> Optional[DataAccessor]
        """獲取能處理該 source 的最高優先順序 Accessor"""

    async def access(self, source, **kwargs) -> LocalResource
        """路由到合適的 Accessor 獲取資料"""
```

預設註冊的 Accessor（按優先順序）：
1. `GitAccessor` (80) - 處理 Git 倉庫
2. `HTTPAccessor` (50) - 處理 HTTP/HTTPS URL
3. `LocalAccessor` (10) - 處理本地檔案（兜底）

---

## 實現進度

### ✅ 已完成

- [x] 建立 `openviking/parse/accessors/` 目錄結構
- [x] 實現 `DataAccessor` 抽象基類和 `LocalResource` 資料類
- [x] 實現 `AccessorRegistry`（含優先順序機制）
- [x] 實現 `GitAccessor` - 處理 Git 倉庫
- [x] 實現 `HTTPAccessor` - 處理 HTTP URL
- [x] 實現 `LocalAccessor` - 處理本地檔案
- [x] 全域登錄檔 `get_accessor_registry()`
- [x] 更新 `PDFParser`、`resources.py`、`local_input_guard.py` 使用新架構

---

## 檔案結構

```
openviking/parse/
├── accessors/                    # ✅ 新增：資料訪問層
│   ├── __init__.py
│   ├── base.py                  # DataAccessor, LocalResource, SourceType
│   ├── registry.py              # AccessorRegistry
│   ├── git_accessor.py          # GitAccessor
│   ├── http_accessor.py         # HTTPAccessor
│   └── local_accessor.py        # LocalAccessor
├── parsers/                      # 資料解析層（保持不變）
│   ├── base_parser.py
│   ├── markdown.py
│   ├── pdf.py
│   ├── zip_parser.py
│   └── ...
└── registry.py                   # ParserRegistry（保持不變）
```

---

## 使用示例

### 使用 AccessorRegistry

```python
from openviking.parse.accessors import get_accessor_registry

# 獲取全域登錄檔
registry = get_accessor_registry()

# 訪問資源（自動路由）
async with await registry.access("https://github.com/user/repo") as resource:
    print(f"本地路徑: {resource.path}")
    print(f"來源型別: {resource.source_type}")
    # 使用 resource.path 進行解析...
    # 退出 with 塊時自動清理臨時資源
```

### 自定義 Accessor

```python
import tempfile
from pathlib import Path

from openviking.parse.accessors import DataAccessor, LocalResource

class MyAccessor(DataAccessor):
    @property
    def priority(self) -> int:
        return 90

    def can_handle(self, source: str) -> bool:
        return source.startswith("myprotocol://")

    async def access(self, source: str, **kwargs) -> LocalResource:
        # 獲取資料到本地...
        temp_path = Path(tempfile.mkdtemp(prefix="openviking_"))
        # ... 下載邏輯 ...
        return LocalResource(
            path=temp_path,
            source_type="myprotocol",
            original_source=source,
            meta={},
            is_temporary=True
        )

# 註冊
registry = get_accessor_registry()
registry.register(MyAccessor())
```

---

## 相關文件

- [解析系統 README](https://github.com/volcengine/OpenViking/blob/main/openviking/parse/parsers/README.md)
- [Business Data Platform 整體架構](../zh/concepts/01-architecture.md)
