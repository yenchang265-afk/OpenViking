# FilePreview

[English](README.md) / 中文

多格式檔案預覽。宿主給出內容與檔名，元件負責格式識別、渲染器載入、標題欄、頁籤、檢視切換與編輯。

> **當前是佔位實現。** 外殼（頁籤行、內容區標題行、頁籤切換、複製、編輯、ref 控制代碼）
> 已按最終形態實現，可以直接互動；檔案正文尚未接入 FileViewer，檔案頁籤暫以純文本
> 降級展示。下文描述的是目標行為。

呼叫方不需要知道這是 Markdown 還是 PDF，也不需要註冊渲染器——檔名決定一切：

```tsx
<FilePreview
  tabs={[
    {
      kind: 'file',
      key: 'file',
      source: { content, fileName: 'SKILL.md', path: 'viking://…/SKILL.md' },
    },
  ]}
/>
```

## 為什麼以 FileViewer 為底座

多格式預覽的難點不在渲染單個格式，而在格式路由、渲染器按需載入、大檔案准入與狀態機。這些已經有成熟實現，重寫一遍只會得到一份更差的版本。

因此本元件以 [`@ark-design/ui`](https://www.npmjs.com/package/@ark-design/ui) 的 `FileViewerCore` 作為渲染底座，在它之上補齊 OpenViking 需要的部分：標題行、頁籤、檢視切換、編輯與業務插槽。

`@ark-design/ui` 是**可選 peer dependency**：只有使用本模組的消費方需要安裝，不裝時其餘模組不受影響。

```bash
npm install @ark-design/ui
```

內建渲染器覆蓋程式碼、純文本、JSON、Markdown、HTML、表格、PDF、Word、PowerPoint、音影片、CAD 與 3D 模型。無副檔名的檔案按檔名匹配，例如 `Dockerfile` 與 `Makefile`。支援範圍固定，不對外開放覆蓋。

## 內容由頁籤驅動

預覽的內容是頁籤列表，每個頁籤的正文有兩種來源：

| 型別              | 渲染路徑                 | 典型用途                      |
| ----------------- | ------------------------ | ----------------------------- |
| `kind: 'file'`    | 經 FileViewer 按格式渲染 | 檔案原文、原始碼、文件          |
| `kind: 'content'` | 完全由宿主渲染           | 經驗看板、wiki 看板、目錄摘要 |

兩類頁籤共享外殼——頁籤行、內容區標題行（路徑麵包屑、複製、許可權標記、標題行插槽），差異只在正文怎麼來。當前啟用哪個頁籤由元件內部維護，宿主不感知；需要從外部跳轉時用 ref 控制代碼的 `setActiveTab`。

選中目錄時首個頁籤可以是 L0/L1 摘要這類內容頁籤，因此元件不假設第一個一定是檔案。

## 狀態由元件判定

載入中、載入失敗與格式不支援不通過 props 表達，元件根據內容與檔案型別自行判定：沒有內容即載入中，內容帶錯誤即失敗，檔名沒有匹配的渲染器即不支援。三種狀態都可以通過插槽換成宿主自己的內容。

編輯態同理：草稿、儲存中與失敗提示都在元件內部。宿主通過 `editing.loadContent` 提供完整文本，通過非同步 `editing.save` 執行儲存；`editing.onSave` 僅在儲存成功後通知已儲存的文本，失敗時保留草稿並顯示提示。`editing.onCancel` 在草稿被丟棄後通知，儲存成功不觸發它。

執行能力與成功通知分開：檔案操作由 `operations.openParent`、`operations.download`、`operations.openUri` 提供，成功後才觸發對應的 `onOpenParent`、`onDownload`、`onOpenUri`。省略執行方法時該操作不可用，省略通知不影響操作。失敗時不觸發成功通知。

複製由元件完成。`onCopyPath` 與 `onCopyContent` 分別在路徑、正文複製成功後通知已複製的值，失敗時不觸發；省略回撥不影響複製。提供路徑時顯示路徑複製按鈕，檔案頁籤的正文複製按鈕在沒有可複製文本時停用。

## 元件不負責什麼

- 不發起業務請求。下載、儲存與導航由宿主提供執行能力；成功通知不負責執行這些操作。
- 不判斷誰能看、誰能改——許可權標記由宿主渲染後從插槽傳入。
- 不內建業務內容。看板、圖譜、摘要都通過頁籤或插槽注入，元件不知道它們是什麼。

## 文件與開發

- 屬性表與可執行示例見文件站 `Components → FilePreview`（待隨實現補充）。
- 開發與構建命令見[前端工作區 README](../../../../../README.md)，模組約定見[包說明](../../../README.md)。
- 獨立樣式入口 `@openviking/react/components/file-preview/style.css`，與 JS 入口分離，可按需引入。
