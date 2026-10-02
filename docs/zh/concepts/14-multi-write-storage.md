# 多寫儲存

多寫儲存讓 Business Data Platform 在一個統一的檔案系統抽象下，同時使用一個主儲存和多個備份儲存。它適合資料高可用、跨區域副本、讀加速、儲存遷移等場景。

從 API 使用者視角看，`read()`、`write()`、`ls()`、`stat()` 等介面不變。多寫邏輯位於 RAGFS 內部，呼叫方不需要關心檔案最終落在哪個底層後端。

## 核心模型

多寫儲存由一個 primary 和多個 backup 組成：

| 角色 | 配置位置 | 說明 |
| --- | --- | --- |
| primary | `storage.agfs.backend` | 權威寫入目標，也是讀取兜底 |
| backup | `storage.agfs.backups.items[]` | 接收復制寫入，可選參與讀取 |

沒有配置 `backups` 時，Business Data Platform 繼續使用原有單後端模式。

## 寫入路徑

預設情況下，寫入先落到 primary，再複製到 write-enabled backup。

```text
Client
  -> Business Data Platform API
  -> RAGFS MultiWrite
  -> primary
  -> backup1 / backup2 / ...
```

backup 未配置 `operations` 時預設參與寫入。這樣可以用最少配置得到冷備能力。

## 同步模式

多寫支援兩種一致性模式。

| 模式 | 配置值 | 行為 | 適用場景 |
| --- | --- | --- | --- |
| 非同步多寫 | `async` | primary 寫成功後立即返回，backup 後臺同步 | 低延遲寫入、最終一致 |
| 同步多寫 | `sync` | primary 寫成功後等待 backup 確認 | 更強寫入確認、可接受額外延遲 |

非同步模式下，backup 可能在短時間內落後於 primary。同步模式下，可以通過 `write_ack_count` 和 `write_ack_timeout_ms` 控制需要等待多少 backup 確認，以及等待多久。

即使使用同步模式，未確認或超時的 backup 仍會由後臺重試修復。

## 讀取路徑

讀取不會預設訪問所有 backup。只有顯式宣告 `read` 操作的 backup 才會進入讀路由。

讀取順序如下：

```text
1. 按 priority 升序訪問 read-enabled backup
2. 回退到 primary
3. 如果檔案被 redirect，則訪問 redirect target
4. 仍未命中則返回 NotFound
```

這種設計避免冷備節點預設參與讀取，降低讀到舊資料的風險。

## Redirect

Redirect 表示“某些檔案不寫入 primary，而是寫入指定 backup”。

常見用途：

- 大檔案進入物件儲存。
- 特定字尾檔案進入專門 backend。
- 主儲存只儲存常規內容，特殊檔案由其他 backend 儲存。

Redirect 策略配置在 primary 上。命中策略後，Business Data Platform 會把對映記錄到內部後設資料中。使用者執行 `ls()`、`stat()`、`read()` 時仍能看到正常的檔案系統檢視。

## Exclude

Exclude 表示“某個 backup 不接收匹配的檔案”。

常見用途：

- 記憶體或快取 backend 不儲存大檔案。
- 某個 backup 只儲存文本類資源。
- 某個低成本 backend 排除臨時或超大檔案。

Exclude 策略配置在 backup 上，隻影響該 backup 是否接收寫入。

## 內部後設資料

多寫使用兩個內部後設資料檔案：

| 文件 | 作用 |
| --- | --- |
| `.redirect.json` | 記錄 redirect 檔案對應的目標 backend |
| `.sync_log.json` | 記錄每個檔案的同步版本和 backup 確認進度 |

這些檔案對普通使用者不可見，不會出現在常規列表結果中，也不應通過公開 API 直接讀寫。

如果 primary 開啟靜態資料加密，這些內部後設資料也會跟隨 primary 加密策略寫入。

## 加密關係

多寫不會改變 Business Data Platform 的透明加密模型。

規則如下：

- Python 層和公共 API 不感知加密實現。
- primary 在全域加密開啟時必須加密。
- backup 可以獨立決定是否加密。
- 內部後設資料必須走 primary 的加密入口。

這意味著啟用多寫後，呼叫方式仍然不變；只需要通過配置決定每個 backend 的加密策略。

## 與 OVPack 的關係

多寫只負責“啟用之後的新寫入”。它不會自動同步啟用之前已經存在於 primary 中的歷史檔案。

如果要遷移存量資料，推薦流程是：

1. 使用 OVPack 或其他受控方式完成全量遷移。
2. 校驗目標 backend 資料。
3. 啟用多寫配置。
4. 後續新增和修改的資料由多寫持續複製。

## 限制

- 非同步模式下 backup 可能短暫落後。
- 啟用多寫前的歷史檔案需要單獨遷移或回填。
- redirect 檔案依賴內部後設資料恢復目錄檢視。
- 多程序同時寫同一 primary 時，需要未來的分散式後設資料鎖能力。
- 熱點目錄會頻繁更新內部後設資料，可能帶來額外寫放大。

## 相關文件

- [儲存架構](./05-storage.md)
- [配置指南](../guides/01-configuration.md)
- [多寫儲存指南](../guides/13-multi-write-storage.md)
- [OVPack 匯入匯出](../guides/09-ovpack.md)
