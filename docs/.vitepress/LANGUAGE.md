# Site language behavior / 站點語言規則

The interface follows the browser's **first** preferred language. Chinese tags use Chinese; the website additionally supports Traditional Chinese, Japanese, Korean and Spanish. Other sites use English for unsupported languages. IP location, top-level domain and secondary browser languages do not affect this decision.

Choose a language in the language menu to remember it, including when it is already displayed. Choose **Follow browser** to resume automatic selection and remove the language query override. Only menu choices persist. `?lang=en` and other supported language tags control the current page without changing the saved choice; Studio also accepts `?lng=`. On Docs, `/en/` and `/zh/` paths take precedence over queries and saved preferences. The root opens the localized documentation homepage automatically; the localized homepages remain stable URLs.

The shared cookie and each origin's fallback localStorage key are `openviking-language-preference`. Values are `auto`, `en`, `zh`, `zh-TW`, `ja`, `ko`, or `es`. No value means `auto`. The cookie wins over localStorage, including when its value is `auto`. Production cookies use the matching `.openviking.ai` or `.openviking.net` parent domain, `Path=/`, a one-year lifetime, `SameSite=Lax`, and `Secure` on HTTPS. The two parent domains remain independent. A bilingual site may display English for a saved `ja` choice without changing that original choice. Old language records (`openviking-preferences.lang`, `i18nextLng`, `blog.lang`, sessionStorage and window.name) are ignored; theme behavior is retained. Disabled storage still permits changes for the current page.

Each repository contains the same self-contained `language-preference.js` and `language-preference.contract.js`; keep their copies and test cases aligned when changing the contract. There is no remote configuration or runtime dependency between repositories. Focus, history restoration and browser-language changes refresh the preference. Explicit page languages continue to win.

Publish the compatible widget before releasing host integrations. Hosts mount it with their current locale, then call `VikingBotWidget.setLocale('en' | 'zh')` to update UI copy in place. Older widget bundles remain mounted when this method is absent. Language changes preserve drafts, panel state, history and connections; they do not change the model's reply policy. Widget assets at `/studio/embed-widget/vikingbot-widget.js` must be routed to the widget's static build even while the Studio page is closed. Verify a JavaScript MIME type and bundle response, not a homepage HTML fallback, before production widget acceptance. These changes do not reopen Studio.

## 中文說明

介面預設只讀取瀏覽器的首選語言；中文標籤使用中文。官網還支援繁體中文、日語、韓語和西班牙語，其他站點遇到未支援語言時顯示英語。自動判斷不使用 IP、所在地區、頂級域名或瀏覽器第二語言。

在語言選單中點選具體語言會儲存選擇，即使當前已經顯示該語言。選擇“跟隨瀏覽器”會恢復自動判斷，並清除 URL 的語言覆蓋。只有選單操作儲存偏好；`?lang=` 只決定當前頁面，Studio 相容 `?lng=`。Docs 的 `/en/`、`/zh/` 路徑優先於查詢引數和儲存的偏好；根入口自動開啟對應語言的文件首頁，兩個語言首頁都是穩定地址。Docs 手動切換儘量保留當前文件，缺少譯文時回退到目標語言簡介頁，不存在的錨點回到頁首。

Cookie 和本站 localStorage 統一使用新鍵 `openviking-language-preference`，取值為 `auto` 或上述六種官網語言程式碼，無記錄等同於自動。Cookie 優先於 localStorage，顯式 `auto` 也優先。正式域名在各自父域共享 Cookie，一年有效，`Path=/`、`SameSite=Lax`，HTTPS 下啟用 `Secure`；`.ai` 與 `.net` 相互獨立。不支援的語言只在顯示時回退，不覆蓋原始選擇。舊語言記錄不遷移，主題偏好保留；儲存不可用時仍可在本頁切換。重新獲得焦點、歷史恢復和瀏覽器語言變化時重讀偏好，顯式頁面語言繼續優先。

四個倉庫內的解析模組和契約測試應同步維護，不引入執行時跨倉依賴。釋出時先發布相容舊呼叫的新 widget，再發布各宿主接入。`setLocale()` 原地更新元件文案，保留面板、草稿、歷史與連線；不改變模型回覆語言策略。舊 widget 缺少此方法時保留現有例項。元件靜態資源路由須與 Studio 頁面關閉狀態分開，上線驗收要確認指令碼地址返回 JavaScript；本改動不恢復 Studio 的開放狀態。

## Verification / 驗證

The shared contract runs 30 cases in each repository. The Docs route suite covers root-to-homepage routing and document language switching; widget locale tests preserve the mounted view, inputs, selection, message history and connection, and verify the translated suggestion payload. The built section-link check also verifies that homepage section anchors remain valid. No coverage threshold is configured for this change.

Chromium checks use local production bundles served under the real `.ai`/`.net` hostnames through request interception, with a local widget and mocked chat transport. They cover both parent-domain cookie scopes and isolation, focus refresh, explicit URLs, legacy language records with retained theme, Blog legacy URLs, desktop/mobile keyboard controls, old widget compatibility, drafts across language changes, and Docs `DOCS_BASE=/guide/`. These are local integration checks, not production chat/backend validation.

Known environment limits: the deployed widget URL currently returns `text/html` and needs its static route restored before release. Studio's whole-project `tsc --noEmit` reports existing errors identical to a clean target-branch checkout; widget typechecking passes. With all storage APIs forced to throw, VitePress 1.6.4's built-in `check-dark-mode` inline script reports a storage error, while documentation and language switching remain usable. Website lint has 11 existing warnings and no errors.

共享契約在各倉執行 30 項；Docs 路由新增 11 項，widget 原地切換新增 4 項。各站構建和 widget 型別檢查通過。瀏覽器驗收使用本地生產構建、真實域名 Cookie 規則和模擬聊天傳輸，不代表線上後端驗收已完成。Studio 全量型別檢查的已有錯誤與乾淨目標分支一致；VitePress 內建深色模式指令碼在強制停用所有儲存 API 時會報錯，但正文和語言切換可用。上線前仍需恢復 widget 的 JavaScript 靜態資源響應。
