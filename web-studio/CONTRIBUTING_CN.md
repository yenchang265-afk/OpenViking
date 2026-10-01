# 參與 Web Studio 國際化維護

Web Studio 支援英文和繁體中文。本文面向在 `web-studio` 中新增或修改使用者可見文本的貢獻者。兩種語言都能正常使用，這項改動才算完成。

先確認文本來自哪裡：

| 文本來源                                    | 處理方式                                                   |
| ------------------------------------------- | ---------------------------------------------------------- |
| 固定介面文案                                | 同時新增英文和繁體中文鍵，再通過 `t()` 或 `<Trans>` 渲染。 |
| 穩定的服務端列舉、狀態、指標或顯示錶頭      | 在本地化介面卡中把已知值對映到 i18n 鍵。                   |
| 模型名稱、路徑、URI、識別符號、命令或使用者內容 | 除非產品定義了顯示名稱，否則保留原值。                     |
| 服務端原始錯誤或診斷資料                    | 翻譯面向使用者的錯誤摘要，同時保留可供排查的原始詳情。       |

## 翻譯資源

從倉庫根目錄看，語言資源位於：

```text
web-studio/src/i18n/locales/en/
web-studio/src/i18n/locales/zh-CN/
```

`web-studio/src/i18n/locales/en.ts` 和 `web-studio/src/i18n/locales/zh-CN.ts` 負責彙總各模組。新增文案應放入負責該頁面或功能的現有名稱空間。確實需要拆分模組時，應同時建立對應的英文和中文檔案，並在兩個語言入口中註冊。

內部鍵名應表達所屬模組和用途：

```ts
settings.connection.userHint
monitoringPage.detail.columns.status
resources.retrieval.emptyTitle
```

不要直接把英文句子作為鍵名。同一個短詞在不同位置含義不同時，也不要為了複用而共用一個含糊的鍵。

## 新增界面文案

元件使用文案前，先在兩種語言資源中新增相同的鍵：

```ts
// web-studio/src/i18n/locales/en/workspace.ts
refresh: 'Refresh'

// web-studio/src/i18n/locales/zh-CN/workspace.ts
refresh: '刷新'
```

普通文本和元件屬性使用 `t()`：

```tsx
const { t } = useTranslation('monitoringPage')

<Button aria-label={t('refresh')}>{t('refresh')}</Button>
```

只有句子中包含巢狀 React 元素時才使用 `<Trans>`。所有語言中的插值名稱和含義必須一致：

```ts
updatedAt: 'Updated at {{time}}'
updatedAt: '更新於 {{time}}'
```

不要用語言判斷和寫死的字串選擇介面文案：

```tsx
// 不要新增這種寫法。
i18n.language.startsWith('zh') ? '刷新' : 'Refresh'
```

語言判斷可以用於不同語言的文件連結或日期格式，但不應代替語言包。

## 服務端返回的文本

不要直接翻譯任意服務端輸出。服務端值可能是模型名稱、Provider 值、路徑、URI、識別符號、命令或原始錯誤詳情。

優先使用結構化欄位。在介面邊界將穩定的列舉值或協議標籤對映到 i18n 鍵，請求、比較、日誌和錯誤處理仍使用原始值。

介面返回 ASCII 表格等面向顯示的文本時，按以下方式處理：

1. 將傳輸格式解析成有型別的介面資料。
2. 只轉換明確登記的表頭、指標、狀態和列舉值。
3. 由元件渲染轉換後的資料。
4. 未登記的值保持原樣；只有產品已經定義安全顯示名稱時才轉換。

監控頁面已經採用這一結構：

- [`parse-status.ts`](./src/routes/monitoring/-lib/parse-status.ts) 負責解析傳輸格式。
- [`localize-observer-status.ts`](./src/routes/monitoring/-lib/localize-observer-status.ts) 負責把穩定的服務端文本對映到 i18n 鍵。
- [`observer-status-content.tsx`](./src/routes/monitoring/-components/observer-status-content.tsx) 負責渲染本地化後的資料。

不要把本地化對映重新寫進路由元件。

## 翻譯範圍

| 應翻譯                                     | 除非產品定義了顯示名稱，否則保持原樣 |
| ------------------------------------------ | ------------------------------------ |
| 頁面標題、按鈕、表單標籤、幫助文字、空狀態 | API 金鑰值、協議欄位名稱、命令       |
| 面向使用者的表頭和狀態                       | 模型名稱、Provider 值、集合名稱      |
| 已知佇列、角色、指標和列舉的顯示名稱       | ID、路徑、URI、檔名、操作識別符號    |
| 面向使用者的校驗提示和錯誤摘要               | 原始錯誤詳情和診斷資料               |

`Agent`、`Root`、`Trusted`、`VikingBot`、`VLM` 和 `Embedding` 等詞在表示產品角色或技術概念時可以保留英文，但各頁面必須保持一致。

## PR 審查清單

提交審查前逐項確認：

- 每條新增的使用者可見文本都有英文和繁體中文。
- 元件使用 `t()` 或 `<Trans>`，沒有新增寫死的語言判斷。
- 不同語言中的佔位符、複數變數、連結和技術識別符號保持一致。
- 服務端標籤通過帶上下文的白名單轉換，未登記的值保持原樣。
- 已在受影響的介面切換並檢視兩種語言，同時檢查功能涉及的空、載入、成功和錯誤狀態。
- 較長的中文在支援的頁面寬度下不會遮擋數值或控制元件。
- 解析器或本地化介面卡會影響執行結果時，有對應的目標測試。

當前配置的 `i18next/no-literal-string` ESLint 規則可以發現不少 JSX 字面量，但無法覆蓋所有 TypeScript 工具函式、條件表示式、服務端響應和動態生成的標籤。因此，Lint 只是檢查項之一，不能證明功能已經完整本地化。

## 驗證

按改動範圍執行檢查：

```bash
cd web-studio
npm run format
npm run lint
npm test -- <relevant-test-files>
```

改動涉及共享本地化程式碼、解析邏輯、路由或多個頁面時，再執行 `npm test` 和 `npm run build`。未執行的檢查及原因應如實說明。

## 相關文件

- [OpenViking 貢獻指南](../CONTRIBUTING_CN.md)：倉庫通用的貢獻流程和要求。
