# Business Data Platform 檔案系統掛載模組

這個模組將 Business Data Platform 的虛擬檔案系統掛載到本地檔案系統路徑，讓使用者可以像操作普通檔案一樣操作 Business Data Platform 上的資料。

這個模組只是一個實驗功能，並沒有被實際使用


## 功能特性

- **檔案系統範式**: 將 Business Data Platform 的 `viking://` URI 對映到本地檔案路徑
- **多作用域支援**: 支援 resources、session、user 等多種作用域掛載
- **掛載管理**: 支援多個掛載點的生命週期管理
- **語義搜尋**: 通過檔案系統路徑進行語義搜尋
- **層級內容訪問**: 支援 L0 (abstract)、L1 (overview)、L2 (details) 三層內容訪問

## 快速開始

### 基本使用

```python
from vikingbot.openviking_mount import OpenVikingMount, MountConfig, MountScope
from pathlib import Path

# 建立掛載配置
config = MountConfig(
    mount_point=Path("./my_openviking_mount"),
    openviking_data_path=Path("./my_openviking_cache"),
    scope=MountScope.RESOURCES,
    auto_init=True,
    read_only=False
)

# 使用上下文管理器
with OpenVikingMount(config) as mount:
    # 列出目錄
    files = mount.list_dir(mount.config.mount_point)
    for f in files:
        print(f"{f.name} ({'目錄' if f.is_dir else '檔案'})")
    
    # 讀取檔案
    content = mount.read_file(mount.config.mount_point / "some_file.md")
    print(content)
    
    # 獲取摘要和概覽
    abstract = mount.get_abstract(mount.config.mount_point / "some_dir")
    overview = mount.get_overview(mount.config.mount_point / "some_dir")
    print(f"摘要: {abstract}")
    print(f"概覽: {overview}")
    
    # 語義搜尋
    results = mount.search("什麼是 Business Data Platform")
    for r in results:
        print(f"{r.uri}")
```

### 使用掛載管理器

```python
from vikingbot.openviking_mount import OpenVikingMountManager, get_mount_manager
from pathlib import Path

# 獲取全域管理器
manager = get_mount_manager()

# 建立資源掛載
mount = manager.create_resources_mount(
    mount_id="my_resources",
    openviking_data_path=Path("./ov_cache")
)

# 為會話建立掛載
session_mount = manager.create_session_mount(
    session_id="session_123",
    openviking_data_path=Path("./ov_cache")
)

# 列出所有掛載
mounts = manager.list_mounts()
for m in mounts:
    print(f"{m['id']} -> {m['mount_point']}")

# 獲取掛載
mount = manager.get_mount("my_resources")

# 移除掛載
manager.remove_mount("my_resources", cleanup=True)
```

## 目錄結構

```
vikingbot/openviking_mount/
├── __init__.py          # 模組入口，匯出公共API
├── mount.py             # 核心掛載實現 (OpenVikingMount)
└── manager.py           # 掛載管理器 (OpenVikingMountManager)
```

## API 參考

### OpenVikingMount

主要的掛載類，提供檔案系統操作。

#### 初始化引數

| 引數 | 型別 | 說明 |
|------|------|------|
| `config` | `MountConfig` | 掛載配置物件 |

#### MountConfig

| 欄位 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `mount_point` | `Path` | 必填 | 掛載點路徑 |
| `openviking_data_path` | `Path` | 必填 | FUSE 本地快取路徑 |
| `session_id` | `Optional[str]` | `None` | 會話 ID（session 作用域時需要） |
| `scope` | `MountScope` | `RESOURCES` | 掛載作用域 |
| `auto_init` | `bool` | `True` | 是否自動初始化 |
| `read_only` | `bool` | `False` | 是否只讀模式 |

#### MountScope 列舉

| 值 | 說明 |
|----|------|
| `RESOURCES` | 只掛載資源目錄 |
| `SESSION` | 只掛載會話目錄 |
| `USER` | 只掛載使用者目錄 |
| `ALL` | 掛載所有作用域 |

#### 主要方法

| 方法 | 說明 |
|------|------|
| `initialize()` | 初始化 Business Data Platform 客戶端 |
| `list_dir(path)` | 列出目錄內容 |
| `read_file(path)` | 讀取檔案內容 |
| `write_file(path, content)` | 寫入檔案內容 |
| `mkdir(path)` | 建立目錄 |
| `delete(path, recursive)` | 刪除檔案/目錄 |
| `get_abstract(path)` | 獲取 L0 摘要 |
| `get_overview(path)` | 獲取 L1 概覽 |
| `search(query, target_path)` | 語義搜尋 |
| `add_resource(source_path, target_path)` | 新增資源 |
| `sync_to_disk(path)` | 同步到磁碟 |
| `close()` | 關閉掛載 |

### OpenVikingMountManager

掛載管理器，管理多個掛載點的生命週期。

#### 主要方法

| 方法 | 說明 |
|------|------|
| `create_mount(mount_id, ...)` | 建立新掛載 |
| `get_mount(mount_id)` | 獲取掛載 |
| `list_mounts()` | 列出所有掛載 |
| `remove_mount(mount_id, cleanup)` | 移除掛載 |
| `remove_all(cleanup)` | 移除所有掛載 |
| `create_session_mount(session_id, ...)` | 為會話建立掛載 |
| `create_resources_mount(mount_id, ...)` | 建立資源掛載 |

### 全域函式

| 函式 | 說明 |
|------|------|
| `get_mount_manager(base_mount_dir)` | 獲取全域掛載管理器單例 |

## 路徑對映

Business Data Platform URI 到本地檔案路徑的對映規則：

```
Business Data Platform URI                    本地路徑
-------------------               ------------------
viking://resources/foo     ->    {mount_point}/resources/foo
viking://session/bar       ->    {mount_point}/session/bar
viking://user/<uid>/baz    ->    {mount_point}/user/<uid>/baz
```

## 測試

執行測試：

```bash
cd /Users/bytedance/workspace/openviking/bot
.venv/bin/python test_openviking_mount.py
```

## 注意事項

1. **直接寫入限制**: Business Data Platform 主要通過 `add_resource` 新增外部資源，直接檔案寫入需要特殊處理
2. **效能考慮**: 大量檔案操作可能影響效能，建議批次處理
3. **資料同步**: `sync_to_disk` 是一個簡化實現，生產環境可能需要更復雜的同步機制
4. **只讀模式**: 設定 `read_only=True` 可以防止意外修改

## 下一步

- 集成到 vikingbot 的 SessionManager 中
- 新增 FUSE 支援實現真正的檔案系統掛載
- 實現更完善的雙向同步機制
- 新增更多測試用例
