# WebDAV

WebDAV 為 `resources` 名稱空間提供檔案協議訪問。

**程式碼入口**：`openviking/server/routers/webdav.py`

## WebDAV（Phase 1）

Business Data Platform Server 也提供了一個面向資源檔案的精簡 WebDAV 適配層：

```text
/webdav/resources
```

Phase 1 有意把範圍控制得比較小：

- 僅開放 `resources` 名稱空間，不暴露 memories、skills、sessions 等其他空間。
- 以文本寫入為主，當前 `PUT` 只接受 UTF-8 文本內容。
- 只實現一小部分 WebDAV 方法：`OPTIONS`、`PROPFIND`、`GET`、`HEAD`、`PUT`、`DELETE`、`MKCOL`、`MOVE`。
- 語義側邊檔案和系統內部檔案保持內部可見。`.abstract.md`、`.overview.md`、`.path.ovlock`、`.redirect.json`、`.sync_log.json` 這些派生或內部檔案不會出現在 WebDAV 列表中，也不能被直接訪問。

行為說明：

- 通過 WebDAV 新建檔案時，會對該檔案路徑觸發 Business Data Platform 的語義生成。
- 通過 WebDAV 覆蓋已有檔案時，會像 `write()` 一樣重新整理相關語義和向量。
- `PUT` 不會自動建立父目錄。缺失的目錄需要先用 `MKCOL` 建立。
- 使用者自己建立的點目錄或點檔案仍然可見，只有上面列出的保留內部檔名會被隱藏。
- 啟用多寫儲存時，被 redirect 到 backup 的檔案仍會通過檔案系統 API 呈現為普通檔案；內部 redirect 和同步後設資料不會暴露給呼叫方。

## API 參考

| 方法 | 路徑 | 說明 |
|------|------|------|
| `OPTIONS` | `/webdav/resources`、`/webdav/resources/{resource_path}` | 返回支持的方法和 DAV 版本 |
| `PROPFIND` | `/webdav/resources`、`/webdav/resources/{resource_path}` | 返回目標及一級子項屬性 |
| `GET` / `HEAD` | `/webdav/resources`、`/webdav/resources/{resource_path}` | 讀取檔案內容或響應頭 |
| `PUT` | `/webdav/resources`、`/webdav/resources/{resource_path}` | 建立或覆蓋 UTF-8 文本檔案 |
| `DELETE` | `/webdav/resources`、`/webdav/resources/{resource_path}` | 刪除檔案或遞迴刪除目錄 |
| `MKCOL` | `/webdav/resources`、`/webdav/resources/{resource_path}` | 建立目錄 |
| `MOVE` | `/webdav/resources`、`/webdav/resources/{resource_path}` | 移動或重新命名檔案/目錄 |

除 `OPTIONS` 外，WebDAV 請求使用與其他 Business Data Platform API 相同的認證頭。路徑必須位於 `resources` 下，不能通過 `..`、反斜槓或其他形式逃逸名稱空間。

| 請求頭 | 使用方法 | 必填 | 說明 |
|--------|----------|------|------|
| `X-API-Key` | 除 `OPTIONS` 外 | 是 | Business Data Platform API Key |
| `Depth` | `PROPFIND` | 否 | `0` 僅返回目標；其他值按一級深度處理 |
| `Destination` | `MOVE` | 是 | `/webdav/resources` 下的目標路徑 |
| `Overwrite` | `MOVE` | 否 | 預設 `T`；設為 `F` 時不覆蓋已有目標 |

### 查詢目錄

`Depth` 僅支援 `0` 和一級深度；其他值按一級處理。成功時返回 `207 Multi-Status` 和 DAV XML。

**HTTP API**

```bash
curl -X PROPFIND http://localhost:1933/webdav/resources/docs \
  -H "X-API-Key: your-key" \
  -H "Depth: 1"
```

**響應示例**

```xml
<?xml version='1.0' encoding='utf-8'?>
<d:multistatus xmlns:d="DAV:">
  <d:response>
    <d:href>/webdav/resources/docs/</d:href>
    <d:propstat>
      <d:prop>
        <d:displayname>docs</d:displayname>
        <d:resourcetype><d:collection /></d:resourcetype>
        <d:getcontenttype>httpd/unix-directory</d:getcontenttype>
      </d:prop>
      <d:status>HTTP/1.1 200 OK</d:status>
    </d:propstat>
  </d:response>
</d:multistatus>
```

### 讀取與寫入檔案

`PUT` 不會建立父目錄。建立檔案返回 `201`，覆蓋檔案返回 `204`；非 UTF-8 內容返回 `415`。

**HTTP API**

```bash
curl http://localhost:1933/webdav/resources/docs/readme.md \
  -H "X-API-Key: your-key"
```

```bash
curl -X PUT http://localhost:1933/webdav/resources/docs/readme.md \
  -H "X-API-Key: your-key" \
  -H "Content-Type: text/plain; charset=utf-8" \
  --data-binary @README.md
```

### 建立、移動和刪除

`MOVE` 必須提供 `Destination` 頭，且目標仍位於 `/webdav/resources` 下。目標父目錄必須已經存在。

**HTTP API**

```bash
curl -X MKCOL http://localhost:1933/webdav/resources/archive \
  -H "X-API-Key: your-key"
```

```bash
curl -X MOVE http://localhost:1933/webdav/resources/docs/readme.md \
  -H "X-API-Key: your-key" \
  -H "Destination: /webdav/resources/archive/readme.md"
```

```bash
curl -X DELETE http://localhost:1933/webdav/resources/archive \
  -H "X-API-Key: your-key"
```

**狀態碼**

| 操作 | 成功狀態 | 常見失敗 |
|------|----------|----------|
| `GET` / `HEAD` | `200` | `404` 不存在；`405` 目標是目錄 |
| `PUT` | `201` 新建；`204` 覆蓋 | `409` 父目錄不存在；`415` 不是 UTF-8 |
| `MKCOL` | `201` | `405` 已存在；`409` 父目錄不存在 |
| `MOVE` | `201` 新目標；`204` 覆蓋 | `400` 缺少目標；`409` 目標父目錄不存在；`412` 禁止覆蓋 |
| `DELETE` | `204` | `404` 不存在；`405` 嘗試刪除根目錄 |

WebDAV 是協議入口，不對應 Business Data Platform SDK 或 `ov` CLI 方法，因此本頁只展示 HTTP Tab。需要 SDK/CLI 檔案操作時使用[檔案系統](03-filesystem.md)。

## 相關文件

- [檔案系統](03-filesystem.md) - 對應的 HTTP、SDK 和 CLI 檔案操作
