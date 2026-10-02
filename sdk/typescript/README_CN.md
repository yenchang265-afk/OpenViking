# @openviking/sdk

Business Data Platform 的輕量級 JavaScript/TypeScript HTTP SDK，面向 Node.js 18+，沒有執行時依賴。

```bash
npm install @openviking/sdk
```

```ts
import { OpenVikingClient } from "@openviking/sdk";

const client = new OpenVikingClient({
  baseUrl: "http://127.0.0.1:1933",
  apiKey: "your-key",
});

const results = await client.search("部署文件", {
  targetUri: "viking://resources",
  limit: 10,
});
```

SDK 與 Python `openviking-sdk`、Go SDK 使用相同的 HTTP API、身份請求頭、響應信封和錯誤碼，覆蓋資源與技能、檔案系統與內容、資源關係、檢索、會話、OVPack、快照、任務、Watch、Observer 狀態和租戶管理介面。

Node.js 中存在的本地檔案路徑會自動上傳，目錄會先壓縮後上傳；其他字串會作為 URL 或服務端路徑傳送。

如果只希望入庫並生成向量、不走 VLM 語義理解，可以給 `addResource` 傳 `processingMode: "vectors_only"`。該模式會寫入/同步資源樹並向量化當前檔案，但不會生成或重新整理 `.abstract.md` / `.overview.md`。

```ts
const task = await client.addResource("./docs/guide.md", {
  to: "viking://resources/guide",
  processingMode: "vectors_only",
});
console.log(task.task_id);
```

通過 `client.getTask(task.task_id as string)` 查詢匯入狀態，任務為 `completed` 後再檢索匯入內容。

事件記憶 tags 可設定為 session 預設值、後續更新，也可在單次 commit 時覆蓋。向 `commitSession` 傳 `[]` 表示本次顯式跳過 session 預設 tags。

```ts
await client.createSession({
  sessionId: "s1",
  memoryExtractionConfig: {
    events: { tags: ["team=search", "channel=web"] },
  },
});
await client.createSession({ sessionId: "manual", autoCommitPolicy: null });
await client.updateSessionConfig("s1", {
  autoCommitPolicy: { message_count_threshold: 25 },
  memoryExtractionConfig: {
    events: { tags: ["team=search", "channel=app"] },
  },
});
await client.updateSessionConfig("s1", { autoCommitPolicy: null });
await client.commitSession("s1", {
  keepRecentCount: 0,
  eventTags: ["team=search", "channel=web"],
});
await client.commitSession("s1", { keepRecentCount: 0, eventTags: [] });
```

使用共享臨時儲存的部署可設定 `uploadMode: "shared"`；服務端也接受 `"local"`（預設值）。

OVPack 匯出和備份與 Python、Go SDK 契約一致：內容會流式寫入 Node.js 本地檔案，並返回最終檔案路徑。

```ts
const packPath = await client.exportOVPack(
  "viking://resources/docs",
  "./backups",
);
await client.importOVPack(packPath, "viking://resources", {
  onConflict: "overwrite",
  vectorMode: "auto",
});
```

## 釋出

推送 `typescript-sdk@0.1.0` 格式的 tag 會自動釋出對應版本，也可以從 GitHub Actions 手動觸發同一 workflow。首次釋出使用具備 `@openviking` scope 許可權的倉庫 `NPM_TOKEN`；包建立後，需要在 npm 為倉庫 `volcengine/OpenViking` 和 workflow `typescript-sdk-release.yml` 配置 Trusted Publisher，後續釋出即可像 `@openviking/cli` 一樣使用 OIDC。
