# OpenViking Go SDK

Go SDK 是面向 OpenViking Server 的 HTTP 客戶端，作為獨立 Go module 放在主倉庫 `sdk/go` 下。

```bash
go get github.com/volcengine/OpenViking/sdk/go
```

## 初始化

```go
client, err := openviking.NewClient(openviking.Config{
    BaseURL: "http://localhost:1933",
    APIKey:  "your-key",
    Timeout: 120 * time.Second,
})
if err != nil {
    log.Fatal(err)
}
defer client.CloseIdleConnections()
```

Go SDK 傳送的身份請求頭與 Python HTTP client 一致：

| Config 字段 | HTTP Header |
|-------------|-------------|
| `APIKey` | `X-API-Key` |
| `Account` | `X-OpenViking-Account` |
| `User` | `X-OpenViking-User` |
| `ActorPeerID` | `X-OpenViking-Actor-Peer` |

普通 `api_key` 部署下只需要設定 `APIKey`，服務端會從 API key 推導 account/user 身份。只有在 trusted 部署或閘道器顯式透傳租戶身份時，才需要設定 `Account` 和 `User`。

Go SDK 不保留舊 `agent_id` 相容路徑。

## 圖片檢索示例

`FindOptions.Image` 和 `SearchOptions.Image` 支援本地路徑、`viking://`、`http(s)://` 或 `data:image` URI；本地圖片會在 SDK 內轉成 base64 data URI，HTTP 請求體仍傳送服務端欄位 `image_url`。

```go
// 本地圖片以圖搜圖
imageResults, err := client.Find(ctx, "", &openviking.FindOptions{
    TargetURI: "viking://resources/images",
    Image:     "./query.png",
    Limit:     5,
})

// 已入庫圖片作為查詢圖
storedImageResults, err := client.Find(ctx, "", &openviking.FindOptions{
    TargetURI: "viking://resources/images",
    Image:     "viking://resources/images/cat.png",
    Limit:     5,
})

// 圖文聯合檢索
similarPosters, err := client.Search(ctx, "紅色海報風格", &openviking.SearchOptions{
    TargetURI: "viking://resources/images",
    Image:     "./poster.png",
    Limit:     5,
})
_, _, _ = imageResults, storedImageResults, similarPosters
```

## 已實現介面

| 模組 | Go 方法 |
|------|---------|
| 資源和技能匯入 | `AddResource`, `AddSkill`, `WaitProcessed` |
| 技能管理 | `ListSkills`, `FindSkills`, `ValidateSkill`, `GetSkill`, `UpdateSkill`, `DeleteSkill` |
| Watch 管理 | `ListWatches`, `GetWatch`, `UpdateWatch`, `DeleteWatch`, `TriggerWatch` |
| 檔案系統和內容 | `List`, `Tree`, `Stat`, `Attrs`, `Mkdir`, `Remove`, `Move`, `Read`, `Abstract`, `Overview`, `Write`, `SetTags`, `Reindex` |
| 檢索 | `Find`, `Search`, `Grep`, `Glob` |
| 會話和任務 | `CreateSession`, `ListSessions`, `GetSession`, `UpdateSessionConfig`, `SessionExists`, `GetSessionContext`, `GetSessionArchive`, `DeleteSession`, `AddMessage`, `BatchAddMessages`, `CommitSession`, `GetTask`, `ListTasks` |
| OVPack | `ExportOVPack`, `BackupOVPack`, `ImportOVPack`, `RestoreOVPack` |
| 系統和 observer | `Health`, `CheckConsistency`, `GetStatus`, `IsHealthy`, `QueueStatus`, `VikingDBStatus`, `ModelsStatus` |
| 管理接口 | `AdminCreateAccount`, `AdminCreateAccountWithOptions`, `AdminListAccounts`, `AdminDeleteAccount`, `AdminRegisterUser`, `AdminRegisterUserWithOptions`, `AdminListUsers`, `AdminRemoveUser`, `AdminSetRole`, `AdminRegenerateKey`, `AdminRegenerateKeyWithOptions`, `AdminMigrate` |

## 暫未實現介面

Go SDK v1 的邊界是對齊當前 Python HTTP client，不覆蓋所有 server 路由。

| 模組 | 原因 |
|------|------|
| 舊 `agent_id` 相容 | 新 SDK 只使用 `ActorPeerID`。 |
| Privacy config 路由 | 當前屬於 server-only 管理面，Python HTTP client 未公開。 |
| Metrics endpoint | Prometheus 文本抓取端點，不是標準 JSON SDK API。 |
| Console/debug/backend-sync/session tool-result 等端點 | 屬於運維或 server-only 能力，未納入 Python HTTP client parity。 |

## 管理使用者配置

建立使用者時如需寫入初始服務端使用者配置，使用 options 版本。普通 add 呼叫不需要 SDK 側預設值；省略 `To` / `TargetURI`，讓服務端解析使用者和部署預設值。

```go
seed := "alice-seed"
_, err := client.AdminRegisterUserWithOptions(ctx, "acme", "alice", "user", &openviking.AdminRegisterUserOptions{
    Seed: &seed,
    UserConfig: map[string]any{
        "add_targets": map[string]any{
            "resource_uri": "viking://~/resources/project-a",
            "skill_uri":    "viking://~/skills",
        },
    },
})

newSeed := "alice-new-seed"
_, err = client.AdminRegenerateKeyWithOptions(ctx, "acme", "alice", &openviking.AdminRegenerateKeyOptions{
    Seed: &newSeed,
})
```

傳入 `Seed` 時，返回的 API Key 會基於 `sha256(user_id + "\0" + seed)` 生成；省略時仍使用隨機生成邏輯。
使用 `nil` 表示不傳 `Seed`；傳入字串指標表示顯式傳送 seed，包括會被服務端拒絕的空字串。

## 技能和 Watch 示例

匯入預設返回 `task_id`。通過 `client.GetTask(ctx, taskID)` 查詢狀態。

```go
skill, err := client.AddSkill(ctx, "./skills/search-web", nil)
if err != nil {
    return err
}
fmt.Println(skill["task_id"])
```

任務為 `completed` 後再檢索匯入的技能：

```go
skills, err := client.ListSkills(ctx, nil)
found, err := client.FindSkills(ctx, "search the web", &openviking.FindSkillsOptions{
    Limit: 5,
})
_, _ = skills, found
```

`AddResource` 在 `WatchInterval > 0` 時會建立 watch；已有任務可用專用 watch 方法管理：

```go
watches, err := client.ListWatches(ctx, &openviking.ListWatchesOptions{
    ActiveOnly: true,
})
updated, err := client.UpdateWatch(ctx, openviking.UpdateWatchOptions{
    ToURI:         "viking://resources/docs",
    WatchInterval: openviking.Float64(30),
    IsActive:      openviking.Bool(true),
})
triggered, err := client.TriggerWatch(ctx, openviking.WatchRef{
    ToURI: "viking://resources/docs",
})
_, _, _ = watches, updated, triggered
```

## 驗證指令碼

編輯 `examples/basic_usage/main.go` 頂部常量：

```go
const (
    baseURL = "http://localhost:1933"
    apiKey  = "your-key"
)
```

執行：

```bash
cd sdk/go
go run ./examples/basic_usage
```

指令碼會建立一個臨時 Markdown 檔案，匯入為 OpenViking resource，讀取並更新內容，執行語義檢索，驗證 watch 和 skill 管理介面，然後建立多訊息 session、commit、輪詢記憶抽取任務，並檢索使用者記憶和 peer-scoped 記憶。

## 測試

```bash
cd sdk/go
go test ./...
```
