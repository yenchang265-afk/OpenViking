# ACL API

ACL 通過獨立的 `/api/v1/acl` 介面查詢和修改，只適用於 `viking://resources/...` 共享資源。許可權模型見[資源訪問控制](../concepts/15-acl.md)。

## 接口

| 方法 | 路徑 | 行為 |
|---|---|---|
| GET | `/api/v1/acl?uri={uri}` | 查詢直接、繼承和有效許可權 |
| PUT | `/api/v1/acl` | 設定直接授權、繼承模式 |
| POST | `/api/v1/acl/grant` | 設定單個 principal 的直接許可權 |
| POST | `/api/v1/acl/revoke` | 刪除單個 principal 的直接授權 |
| DELETE | `/api/v1/acl?uri={uri}` | 清空直接授權並恢復 inherit |

**HTTP**

```http
GET /api/v1/acl?uri={uri}
PUT /api/v1/acl
DELETE /api/v1/acl?uri={uri}
POST /api/v1/acl/grant
POST /api/v1/acl/revoke
```

以上操作均要求 `manage`，無許可權時返回 403。帳號 ADMIN 隱式擁有 manage。

查詢響應中的 `result`：

```json
{
  "uri": "viking://resources/project-a",
  "acl_mode": "restricted",
  "direct_entries": [{"principal": "user:bob", "level": "read"}],
  "inherited_entries": [{"principal": "user:*", "level": "manage"}],
  "effective_entries": [{"principal": "user:bob", "level": "read"}]
}
```

修改介面直接返回 ACL report。`set_acl` 請求：

```json
{
  "uri": "viking://resources/project-a",
  "acl_mode": "restricted",
  "entries": [{"principal": "user:bob", "level": "read"}]
}
```

- `entries`：完整替換直接授權；省略則保留；`[]` 清空。
- `acl_mode`：`inherit` 合併直接與繼承授權，`restricted` 僅使用直接授權；省略則保留。
- 兩個欄位至少傳一個。繼承和有效許可權是隻讀欄位。
- principal 支援 `user:{id}`、`group:{id}`、`user:*`，level 支援 `read`、`write`、`manage`。重複 principal 保留最高 level。
- `grant_acl` 請求為 `{uri, principal, level}`；`revoke_acl` 為 `{uri, principal}`；重置使用 `DELETE /api/v1/acl?uri={uri}`。增刪單個條目由服務端在鎖內完成。

## 建立和寫入時設定

`POST /api/v1/resources`、`POST /api/v1/fs/mkdir`、`POST /api/v1/content/write` 都接受頂層 `acl` 欄位；支援 tags 的介面中，`acl` 與 `tags`、`tag_mode` 並列：

```json
{
  "acl": {
    "acl_mode": "restricted",
    "entries": [{"principal": "user:bob", "level": "read"}]
  }
}
```

不傳 ACL：新節點直接授權為空並繼承父目錄，已有節點保留原許可權。顯式傳 ACL：新節點要求呼叫者從父目錄繼承 manage，已有節點要求自身 manage；在內容修改前校驗，write 許可權不能用來提權。沒有建立者額外許可權。

匯入只把直接 ACL 設定到最終匯入根節點，子節點繼承；自動建立的中間父目錄不接收該授權。相同內容重新匯入也會更新顯式傳入的 ACL。

帳號 `acl.enabled` 預設 false，關閉時按原 namespace 規則訪問，ACL 不參與鑑權；開啟後共享根目錄固定 `user:* = manage` 且不可修改。傳入 ACL 不會自動開啟帳號開關，也不會自動切換 restricted。

ACL 仍儲存在 context 索引內，允許短暫不一致，按現有非同步任務和 wait 語義生效。獨立修改 ACL 要求目標已有 context 記錄；本次不增加無向量記錄或空檔案支援。

**CLI**

```bash
ov acl get viking://resources/project-a
ov acl set viking://resources/project-a --acl-mode restricted --entry user:bob=read
ov acl grant viking://resources/project-a --principal user:bob --level write
ov acl revoke viking://resources/project-a --principal user:bob
ov acl rm viking://resources/project-a

ov mkdir viking://resources/project-a --acl '{"acl_mode":"restricted","entries":[{"principal":"user:bob","level":"read"}]}'
ov add-resource ./docs --to viking://resources/docs --acl '{"acl_mode":"restricted","entries":[]}'
ov write viking://resources/project-a/a.md --content hello --mode create --acl '{"acl_mode":"inherit"}'
```

## SDK

```python
acl = {"acl_mode": "restricted", "entries": [{"principal": "user:bob", "level": "read"}]}
client.mkdir(uri, acl=acl)
client.add_resource("./docs", to=uri, options={"acl": acl})
client.write(file_uri, "hello", options={"acl": acl})
report = client.acl_get(uri)
client.acl_set(uri, [], acl_mode="restricted")
client.acl_grant(uri, "user:bob", "read")
client.acl_revoke(uri, "user:bob")
client.acl_delete(uri)
```

非同步 Python 使用相同方法名。TypeScript 對應 `aclGet(uri)`、`aclSet`、`aclGrant`、`aclRevoke`、`aclDelete`；建立介面的 options 支援 `acl`，mkdir 使用第三個引數。Go 對應 `ACL(ctx, uri)`、`SetACL`、`SetACLMode`、`GrantACL`、`RevokeACL`、`DeleteACL`，通過 `ACLSpec` 設定建立許可權。
