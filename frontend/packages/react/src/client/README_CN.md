# Client

[English](README.md) / 中文

OpenViking 請求客戶端，從 `@openviking/react/client` 匯出。自帶基於 `fetch` 的傳輸層，以及把配置下發給模組的 React Provider。

## 怎麼用

宿主在應用根部配置一次 Provider。傳的是欄位值，不是請求頭：

```tsx
import { OpenVikingProvider } from '@openviking/react/client';

<OpenVikingProvider
  baseURL="https://ov.example.com/gateway/openviking"
  accountId={accountId}
  userId={userId}
  resourceId={libraryId}
>
  <FileBrowser locale="zh-CN" />
</OpenVikingProvider>;
```

開源版額外傳 `apiKey`；商業版由瀏覽器 Cookie 鑑權，因此不傳 `apiKey`。`credentials` 預設 `include`，跨源呼叫也無需顯式傳入，仍遵循服務端 CORS 與瀏覽器 Cookie 策略。

Provider 掛載本身不發請求，也不讀取瀏覽器中儲存的憑證。

## 配置欄位

每個欄位都是值。請求頭由 Client 組裝，呼叫方不需要手寫 `X-API-Key`、`X-OpenViking-Account`、`X-OpenViking-User` 或 `V-Resource-Id`。

| 欄位          | 請求頭                 | 說明                                                                                         |
| ------------- | ---------------------- | -------------------------------------------------------------------------------------------- |
| `baseURL`     | —                      | 服務地址及可選閘道器字首，不含 `/api/v1`。空字串表示同源。                                   |
| `apiKey`      | `X-API-Key`            | 開源版使用。函式形式每次請求重新求值，可讀取輪換後的憑證。                                   |
| `accountId`   | `X-OpenViking-Account` | OpenViking 帳號，對應資料空間。                                                              |
| `userId`      | `X-OpenViking-User`    | 帳號內的使用者。                                                                             |
| `resourceId`  | `V-Resource-Id`        | 當前庫。資料面介面需要它。                                                                   |
| `credentials` | —                      | 傳給 `fetch` 的 `RequestCredentials`。預設 `include`，可按需覆蓋為 `same-origin` 或 `omit`。 |
| `signal`      | —                      | 呼叫方的 `AbortSignal`。                                                                     |
| `fetch`       | —                      | 傳輸層覆蓋，用於測試或沒有全域性 `fetch` 的平臺。                                            |

欄位省略或為空字串時不傳送對應請求頭。商業版的控制面介面只需 Cookie，因此不傳 `apiKey`，也不傳身份頭。

## 分層覆蓋

模組或單次請求可以覆蓋個別欄位。解析逐欄位進行——本次請求的值，然後是 Provider 的值，最後是預設值——呼叫方只寫要改的部分：

```ts
await client.request({
  method: 'GET',
  path: OV_PATHS.fsLs,
  query: { uri },
  options: { resourceId: otherLibraryId },
});
```

`baseURL: ''` 是明確的「同源」，與省略該欄位不同。

## 直接呼叫

`createOvClient` 不依賴 React，用於沒有 Provider 的宿主：

```ts
import { createOvClient, OV_PATHS } from '@openviking/react/client';

const client = createOvClient({
  baseURL: 'https://ov.example.com/gateway/openviking',
  apiKey: 'sk-...',
  accountId,
  userId,
  resourceId,
});

const rows = await client.request<FsEntry[]>({
  method: 'GET',
  path: OV_PATHS.fsLs,
  query: { uri, output: 'agent' },
});
```

`request` 返回原生響應的 `result`。`baseURL` 是實際生效的地址，用於隔離快取與訂閱。

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

失敗響應仍是 JSON 外殼，錯誤碼照常保留在 `OvClientError.code` 上。二進位制響應沒有 body，因此不會帶上 `content-type: application/json`。

## 事件流

`stream` 建立 SSE 連線，返回的事件可以 `for await` 逐個消費：

```ts
const stream = await client.stream({
  method: 'POST',
  path: '/bot/v1/chat/stream',
  body: { message, session_id },
});

for await (const event of stream) {
  // event.data 是原始文本，事件型別在 JSON 裡面
}

stream.abort();
```

- `accept: text/event-stream` 預設傳送，`headers` 可追加或覆蓋；身份欄位仍由 Client 組裝並在同名時勝出。
- `body` 允許任意欄位，服務端約定的開關（例如只訂閱已有會話的 `Attach`）原樣轉發。
- `data` 保持原文不做 JSON 解析：OpenViking 把事件型別和事件 id 放在 `data` 的 JSON 裡，不佔 SSE 的 `event` / `id` 欄位。
- 只有註釋的心跳塊（`: keepalive`）不產生事件；末尾缺空行的塊仍會派發。
- 響應到達即 resolve。HTTP 失敗、`content-type` 不是事件流、以及非流響應裡的 `status: 'error'` 都在 resolve 之前丟擲 `OvClientError`。
- `abort()` 或呼叫方 signal 取消後，迭代安靜結束而不拋 `AbortError`——取消是呼叫方的意圖，不是失敗。

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

`OV_PATHS` 用 `as const` 而不是 `enum`：字串 enum 在 `isolatedModules` 下不會內聯，產出的物件還會被當成副作用；作為公開匯出時它是 ambient const enum，消費者一旦開啟 `isolatedModules` 或 `verbatimModuleSyntax` 就會直接編譯失敗。

## 失敗

`OvClientError` 是唯一的失敗型別。它區分 HTTP 失敗與原生響應裡的 `status: 'error'`，並保留服務端錯誤碼、狀態、附加資訊與請求標識。`code` 在服務端給出錯誤碼時用服務端的，否則為 `HTTP_<status>` 或 `NETWORK_ERROR`。`isOvClientError` 用於把 `unknown` 收窄到該型別。

## 替換傳輸層

`OvClient` 是模組依賴的介面。要複用宿主已有的 axios 例項或 OpenAPI 生成的 SDK 時實現它：

```ts
class AxiosOvClient implements OvClient {
  constructor(
    private readonly instance: AxiosInstance,
    readonly baseURL: string,
  ) {}

  async request<TResult>(spec: OvRequestSpec): Promise<TResult> {
    const { data } = await this.instance.request({
      method: spec.method,
      url: spec.path,
      params: spec.query,
      data: spec.body,
      signal: spec.options?.signal,
    });
    if (data?.status === 'error') {
      throw new OvClientError({
        code: data.error?.code ?? 'UNKNOWN',
        message: data.error?.message ?? 'Request failed',
      });
    }
    return data?.result ?? data;
  }
}
```

不管用哪種傳輸層，這三件事都由它負責，模組不再重複：拼接服務地址與路徑、把身份欄位轉成請求頭、把響應變成結果或 `OvClientError`。`OvClient` 還有 `stream`，實現自定義傳輸層時也要一併提供；事件流的分幀可以直接複用匯出的解析器思路，但解析器本身留在包內，不單獨開放。

## 開發

在 `frontend/` 下：

```bash
npm run build:lib
npm run typecheck
npm test
```

客戶端沒有執行時依賴，只在真正發請求時才用 `fetch`，因此在服務端渲染階段匯入是安全的。
