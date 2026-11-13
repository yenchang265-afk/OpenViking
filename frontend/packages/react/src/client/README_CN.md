# Client

[English](README.md) / 中文

OpenViking 請求客戶端，從 `@openviking/react/client` 匯出：基於 `fetch` 的原生 OpenViking API 客戶端，以及把配置下發給區塊的 `OpenVikingProvider`。

## 怎麼用

在應用根部配置一次 Provider。傳的是欄位值，不是請求頭：

```tsx
import { OpenVikingProvider } from '@openviking/react/client';
import { FileBrowser } from '@openviking/react/modules/file-browser';

<OpenVikingProvider
  baseURL="https://ov.example.com/gateway/openviking"
  accountId={accountId}
  userId={userId}
  resourceId={libraryId}
>
  <FileBrowser />
</OpenVikingProvider>;
```

開源版額外傳 `apiKey`；商業版由瀏覽器 Cookie 鑑權，不傳 `apiKey`。`credentials` 預設 `include`，跨源請求也一樣，仍遵循服務端 CORS 與瀏覽器 Cookie 策略。

Provider 掛載本身不發請求，也不讀取瀏覽器中儲存的憑證。它的 `locale` 設定子樹的介面語言，見[國際化](../../../../docs/docs/zh/guide/i18n.mdx)。

## 配置欄位

每個欄位都是值。請求頭由 Client 組裝，呼叫方不需要手寫 `X-API-Key`、`X-OpenViking-Account`、`X-OpenViking-User` 或 `V-Resource-Id`。

| 欄位          | 請求頭                 | 說明                                                                                                                     |
| ------------- | ---------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `baseURL`     | -                      | 服務地址及可選閘道器字首，不含 `/api/v1`。空字串表示同源。                                                               |
| `apiKey`      | `X-API-Key`            | 開源版的憑證。                                                                                                           |
| `accountId`   | `X-OpenViking-Account` | OpenViking 帳號 ID，對應資料空間。                                                                                       |
| `userId`      | `X-OpenViking-User`    | 帳號內的使用者 ID。                                                                                                      |
| `resourceId`  | `V-Resource-Id`        | 當前庫 ID。資料面介面需要它。                                                                                            |
| `signal`      | -                      | 中止請求的 `AbortSignal`。                                                                                               |
| `credentials` | -                      | 傳給 `fetch` 的 `RequestCredentials`。預設 `include`，可覆蓋為 `same-origin` 或 `omit`。只能在 Provider 或客戶端上設定。 |
| `fetch`       | -                      | 替換全域性 `fetch`，用於測試、鏈路追蹤或沒有全域性 `fetch` 的平臺。只能在 Provider 或客戶端上設定。                      |

四個身份欄位也可以傳函式，返回字串或字串的 Promise。函式每次請求求值一次，因此可以讀取輪換後的憑證。身份欄位省略或為空字串時不傳送對應請求頭。

## 分層覆蓋

區塊或單次請求可以覆蓋個別欄位（`baseURL`、身份欄位和 `signal`）。解析逐欄位進行：本次請求的值，然後是最近的 Provider 的值，最後是預設值。巢狀的 Provider 繼承它省略的欄位。呼叫方只寫要改的部分：

```ts
await client.request({
  method: 'GET',
  path: OV_PATHS.fsLs,
  query: { uri },
  options: { resourceId: otherLibraryId },
});
```

`baseURL: ''` 明確表示「同源」，與省略該欄位不同。身份欄位傳空字串，則清除從上一層繼承的值。

## 直接呼叫

`createOvClient` 不依賴 `OpenVikingProvider`，用於 React 樹之外的程式碼：

```ts
import { createOvClient, OV_PATHS } from '@openviking/react/client';

const client = createOvClient({
  baseURL: 'https://ov.example.com/gateway/openviking',
  apiKey,
  accountId,
  userId,
  resourceId,
});

const rows = await client.request<{ uri: string; isDir?: boolean }[]>({
  method: 'GET',
  path: OV_PATHS.fsLs,
  query: { uri, output: 'agent' },
});
```

`request` 返回原生響應的 `result`。`client.baseURL` 是建立客戶端時的服務地址，適合作為快取或訂閱的鍵。

列表介面把 `has_more` 放在 `result` 之外。`requestEnvelope` 把兩者一起返回為 `{ result, hasMore }`，只有響應設定了 `has_more: true` 時 `hasMore` 才為 `true`：

```ts
const { result, hasMore } = await client.requestEnvelope<{ uri: string }[]>({
  method: 'GET',
  path: OV_PATHS.fsLs,
  query: { uri, node_limit: 200, offset: 0 },
});
```

## 二進位制響應

`responseType: 'blob'` 讓 `request` 跳過外殼解析，直接返回原始位元組。預覽圖片、下載檔案都走這條路：

```ts
const blob = await client.request<Blob>({
  method: 'GET',
  path: OV_PATHS.contentDownload,
  query: { uri },
  responseType: 'blob',
});
```

失敗響應仍是 JSON 外殼，錯誤碼照常保留在 `OvClientError.code` 上。下載請求沒有 `body`，因此不會帶上 `content-type: application/json`。`requestEnvelope` 不接受 `responseType: 'blob'`。

## 事件流

`stream` 建立 SSE 連線，返回的事件可以 `for await` 逐個消費：

```ts
const stream = await client.stream({
  method: 'POST',
  path: OV_PATHS.botChatStream,
  body: { message, session_id },
});

for await (const event of stream) {
  // event.data 是原始文本，事件型別在 JSON 裡面
}

stream.abort();
```

- `accept: text/event-stream` 預設傳送，`headers` 可追加或覆蓋；身份欄位仍由 Client 組裝並在同名時勝出。
- `body` 允許任意欄位，按原樣傳送，服務端約定的選項因此可以透傳。
- `data` 保持原文，不做 JSON 解析：OpenViking 把事件型別和事件 id 放在 `data` 的 JSON 裡，不佔 SSE 的 `event` / `id` 欄位。
- 只有註釋的心跳塊（`: keepalive`）不產生事件；末尾缺空行的塊仍會派發。
- `stream` 在響應到達時 resolve。HTTP 失敗、`content-type` 不是事件流，以及非流響應裡的 `status: 'error'`，都在 resolve 之前丟擲 `OvClientError`。
- `abort()` 或通過 `signal` 取消後，迭代安靜結束而不拋 `AbortError`：取消是呼叫方的意圖，不是失敗。
- 一條流只能迭代一次。

## 介面路徑

`OV_PATHS` 集中維護原生介面路徑，介面改名時只改一處。帶路徑引數的介面用 `OV_PATH_BUILDERS`，引數會自動 URL 編碼：

```ts
import { OV_PATHS, OV_PATH_BUILDERS } from '@openviking/react/client';

await client.request({ method: 'GET', path: OV_PATHS.fsLs, query: { uri } });
await client.request({
  method: 'POST',
  path: OV_PATH_BUILDERS.sessionMessages(sessionId),
  body: { role: 'user', content },
});
```

`OV_PATHS` 是 `as const` 物件，不是 `enum`，開啟 `isolatedModules` 或 `verbatimModuleSyntax` 的消費者因此仍能正常編譯。

## 失敗

`OvClientError` 是 `request`、`requestEnvelope` 和 `stream` 唯一的失敗型別。它區分 HTTP 失敗與原生響應裡的 `status: 'error'`，並保留服務端錯誤碼、`statusCode`、`details`、`requestId` 與 `responseBody`。`isOvClientError` 用於把 `unknown` 收窄到該型別。

服務端給出錯誤碼時，`code` 就是該錯誤碼，否則取下列之一：

- `HTTP_<status>`：HTTP 失敗。
- `UNKNOWN`：`status: 'error'` 的響應沒有錯誤碼。
- `NETWORK_ERROR`：傳輸層失敗。
- `UNEXPECTED_CONTENT_TYPE`：`stream` 收到的不是事件流。
- `INVALID_REQUEST`：`requestEnvelope` 被要求返回 `blob`。

通過 `signal` 取消請求不算客戶端失敗：`request` 以原始的 `AbortError` 拒絕。

## 替換傳輸層

預設傳輸層呼叫全域性 `fetch`。要讓請求經過自己的函式，把 `fetch` 傳給 `OpenVikingProvider` 或 `createOvClient`，例如新增鏈路追蹤，或在測試裡返回固定響應：

```tsx
const fixedFetch: typeof fetch = async () =>
  new Response(JSON.stringify({ result: [] }), {
    headers: { 'content-type': 'application/json' },
  });

<OpenVikingProvider fetch={fixedFetch}>
  <FileBrowser />
</OpenVikingProvider>;
```

`createOvClient` 返回的 `OvClient` 帶有 `request`、`requestEnvelope`、`stream` 和 `baseURL`，是區塊依賴的介面。區塊始終使用最近的 Provider 建立的客戶端，Provider 不接收自己實現的客戶端，所以要改變區塊的傳輸方式，就傳 `fetch`。不管傳輸層怎麼換，這三件事都由 Client 負責，區塊不再重複：拼接服務地址與路徑、把身份欄位轉成請求頭、把響應變成結果或 `OvClientError`。

## 服務端渲染

匯入 `@openviking/react/client` 沒有副作用，在服務端渲染階段是安全的。`createOvClient` 需要一個 `fetch`，可以是全域性的，也可以是你傳入的，兩者都沒有就會拋錯。

客戶端的測試位於 `packages/react/test/client*.test.mjs`，在 `frontend/` 下執行 `npm test`（見[前端工作區 README](../../../../README.md)）。
