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
  <FileBrowser />
</OpenVikingProvider>;
```

開源版額外傳 `apiKey`；商業版由瀏覽器 Cookie 鑑權，因此不傳 `apiKey`，跨源呼叫時把 `credentials` 設為 `include`。

Provider 掛載本身不發請求，也不讀取瀏覽器中儲存的憑證。

## 配置欄位

每個欄位都是值。請求頭由 Client 組裝，呼叫方不需要手寫 `X-API-Key`、`X-OpenViking-Account`、`X-OpenViking-User` 或 `V-Resource-Id`。

| 欄位          | 請求頭                 | 說明                                                                           |
| ------------- | ---------------------- | ------------------------------------------------------------------------------ |
| `baseURL`     | —                      | 服務地址及可選閘道器字首，不含 `/api/v1`。空字串表示同源。                     |
| `apiKey`      | `X-API-Key`            | 開源版使用。函式形式每次請求重新求值，可讀取輪換後的憑證。                     |
| `accountId`   | `X-OpenViking-Account` | OpenViking 帳號，對應資料空間。                                                |
| `userId`      | `X-OpenViking-User`    | 帳號內的使用者。                                                               |
| `resourceId`  | `V-Resource-Id`        | 當前庫。資料面介面需要它。                                                     |
| `credentials` | —                      | 傳給 `fetch` 的 `RequestCredentials`。預設 `same-origin`；商業版需 `include`。 |
| `signal`      | —                      | 呼叫方的 `AbortSignal`。                                                       |
| `fetch`       | —                      | 傳輸層覆蓋，用於測試或沒有全域性 `fetch` 的平臺。                              |

欄位省略或為空字串時不傳送對應請求頭。商業版的控制面介面只需 Cookie，因此不傳 `apiKey`，也不傳身份頭。

## 分層覆蓋

模組或單次請求可以覆蓋個別欄位。解析逐欄位進行——本次請求的值，然後是 Provider 的值，最後是預設值——呼叫方只寫要改的部分：

```ts
await client.request({
  method: 'GET',
  path: '/api/v1/fs/ls',
  query: { uri },
  options: { resourceId: otherLibraryId },
});
```

`baseURL: ''` 是明確的「同源」，與省略該欄位不同。

## 直接呼叫

`createOvClient` 不依賴 React，用於沒有 Provider 的宿主：

```ts
import { createOvClient } from '@openviking/react/client';

const client = createOvClient({
  baseURL: 'https://ov.example.com/gateway/openviking',
  apiKey: 'sk-...',
  accountId,
  userId,
  resourceId,
});

const rows = await client.request<FsEntry[]>({
  method: 'GET',
  path: '/api/v1/fs/ls',
  query: { uri, output: 'agent' },
});
```

`request` 返回原生響應的 `result`。`baseURL` 是實際生效的地址，用於隔離快取與訂閱。

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

不管用哪種傳輸層，這三件事都由它負責，模組不再重複：拼接服務地址與路徑、把身份欄位轉成請求頭、把響應變成結果或 `OvClientError`。

## 開發

在 `frontend/` 下：

```bash
npm run build:lib
npm run typecheck
npm test
```

客戶端沒有執行時依賴，只在真正發請求時才用 `fetch`，因此在服務端渲染階段匯入是安全的。
