# @openviking/react

[English](README.md) / 中文

用於在 OpenViking（面向 AI 智慧體的上下文資料庫）之上構建應用介面的 React 業務元件與區塊。
VikingBot 是無頭模組：從 `@openviking/react/modules/viking-bot` 匯入 `useVikingBotChat`、`useVikingBotSessions` 及契約。Console 預設內建呼叫；獨立 VikingBot 宿主也可直接使用。它不匯出組合檢視或 CSS，Hook 不從包根或 Console 轉匯出。

## 安裝

```bash
npm install @openviking/react
```

`react` 與 `react-dom` 是 peer 依賴（`^18.2.0 || ^19.0.0`）。FileBrowser 通過 FilePreview 展示檔案內容，FilePreview 還需要可選的 peer 依賴 `@ark-design/ui`，版本和需要配套安裝的包見 [FilePreview 頁面](../../docs/docs/zh/components/file-preview.mdx)。

## 快速開始

### 業務元件

業務元件只渲染傳入的資料，不發請求。引入元件和樣式，並給容器設定高度：

```tsx
import { useState } from 'react';
import {
  FileTree,
  type FileTreeRow,
} from '@openviking/react/components/file-tree';
import '@openviking/react/components/file-tree/style.css';

const rows: FileTreeRow[] = [
  {
    kind: 'entry',
    id: 'viking://resources',
    uri: 'viking://resources',
    name: 'resources',
    type: 'directory',
    depth: 0,
    expanded: true,
  },
  {
    kind: 'entry',
    id: 'viking://resources/intro.md',
    uri: 'viking://resources/intro.md',
    name: 'intro.md',
    type: 'file',
    depth: 1,
  },
];

export function Tree() {
  const [selectedId, setSelectedId] = useState<string>();
  return (
    <div style={{ height: 320 }}>
      <FileTree
        rows={rows}
        selectedId={selectedId}
        operations={{ select: async (row) => setSelectedId(row.id) }}
      />
    </div>
  );
}
```

### 區塊

區塊自己從 OpenViking API 取數。把它放進 `OpenVikingProvider`，由 Provider 持有服務地址和憑證：

```tsx
import { OpenVikingProvider } from '@openviking/react/client';
import { FileBrowser } from '@openviking/react/modules/file-browser';
import '@openviking/react/modules/file-browser/style.css';

export function Browser({ apiKey }: { apiKey: string }) {
  return (
    <OpenVikingProvider baseURL="https://ov.example.com" apiKey={apiKey}>
      <div style={{ height: 600 }}>
        <FileBrowser />
      </div>
    </OpenVikingProvider>
  );
}
```

`baseURL` 是不含 `/api/v1` 的服務地址。其餘身份欄位、各區塊的 `requestOptions` 覆蓋，以及 Provider 的完整規則見[區塊概覽](../../docs/docs/zh/modules/index.mdx)。

## 入口

所有 JavaScript 入口都是 ESM。不提供 `@openviking/react/components`、`@openviking/react/modules` 這類整類聚合的入口。

| 匯入路徑                              | 提供                                                                                                                                                                              |
| ------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `@openviking/react`                   | 業務元件和區塊，以及各自的主 Props 型別，例如 `FileTree` 與 `FileTreeProps`。`FilePreview` 除外，需要從它的子路徑匯入。                                                           |
| `@openviking/react/components/<名稱>` | 單個元件及其相關型別（行、選項、控制代碼、文案），例如 `components/file-tree`。同族元件放在分組目錄下，例如 `components/auth/email-login-form`。                                  |
| `@openviking/react/modules/<名稱>`    | 區塊 `file-browser`、`console`、`scope-cascade`，或 `viking-bot` 無頭模組。                                                                                                       |
| `@openviking/react/client`            | `OpenVikingProvider` 與請求客戶端（`createOvClient`、`OvClientError` 等）。                                                                                                       |
| `@openviking/react/icons`             | 圖示元件與檔案型別圖示函式。                                                                                                                                                      |
| `…/style.css`                         | 樣式。JavaScript 不會引入 CSS，用到什麼引入什麼：整包用 `@openviking/react/style.css`，一類用 `components/style.css` 或 `modules/style.css`，單個元件或區塊用各自的 `style.css`。 |

每個樣式入口都可以獨立使用，並包含所依賴元件的樣式。

## 文件

- [快速開始](../../docs/docs/zh/guide/getting-started.mdx)
- [國際化](../../docs/docs/zh/guide/i18n.mdx)：`locale` 與 `labels`
- [業務元件](../../docs/docs/zh/components/index.mdx)：概覽頁連結到每個業務元件的頁面
- [區塊](../../docs/docs/zh/modules/index.mdx)：概覽頁介紹 `OpenVikingProvider` 與 `requestOptions`，每個區塊一個頁面
- [請求客戶端](./src/client/README_CN.md)：`createOvClient`、事件流、錯誤與介面路徑

## 許可證

`@openviking/react` 使用 AGPL-3.0-only 許可證，與 OpenViking 倉庫一致（[LICENSE](../../../LICENSE)）。內部的 Button、Input、Modal 與 Drawer 改編自 Arco Design（MIT），宣告隨包保留在 `LICENSE.arco-design`；Button 與 Input 的視覺規則改編自 `@arco-design/theme-ve-o-aml-design@0.0.36`（MIT）。圖示的來源與授權（包括 Apache-2.0 的檔案型別圖示）記錄在 [`packages/icons`](../icons/README.md)。
