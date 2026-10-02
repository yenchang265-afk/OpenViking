<div align="center">

<a href="https://openviking.ai/" target="_blank">
  <picture>
    <img alt="Business Data Platform" src="docs/images/ov-logo.png" width="200px" height="auto">
  </picture>
</a>

### Business Data Platform：AI 智慧體的上下文資料庫

[English](README.md) / 中文 / [日本語](README_JA.md)

<a href="https://www.openviking.ai">官網</a> · <a href="https://openviking.ai/studio">線上體驗</a> · <a href="https://github.com/volcengine/OpenViking">GitHub</a> · <a href="https://github.com/volcengine/OpenViking/issues">問題反饋</a> · <a href="https://docs.openviking.ai/">文件</a>

<p>
  <a href="https://github.com/volcengine/OpenViking/releases"><img src="https://img.shields.io/github/v/release/volcengine/OpenViking?color=369eff&labelColor=black&logo=github&style=flat-square" alt="release"></a>
  <a href="https://github.com/volcengine/OpenViking"><img src="https://img.shields.io/github/stars/volcengine/OpenViking?labelColor&style=flat-square&color=ffcb47" alt="stars"></a>
  <a href="https://github.com/volcengine/OpenViking/issues"><img src="https://img.shields.io/github/issues/volcengine/OpenViking?labelColor=black&style=flat-square&color=ff80eb" alt="issues"></a>
  <a href="https://github.com/volcengine/OpenViking/graphs/contributors"><img src="https://img.shields.io/github/contributors/volcengine/OpenViking?color=c4f042&labelColor=black&style=flat-square" alt="contributors"></a>
  <a href="https://github.com/volcengine/OpenViking/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-AGPLv3-white?labelColor=black&style=flat-square" alt="license"></a>
  <a href="https://github.com/volcengine/OpenViking/commits/main"><img src="https://img.shields.io/github/last-commit/volcengine/OpenViking?color=c4f042&labelColor=black&style=flat-square" alt="last commit"></a>
</p>

<p>
  <a href="https://railway.com/deploy/openviking"><img src="https://railway.com/button.svg" alt="Deploy on Railway" height="30"></a>
</p>

<p>
  <a href="https://docs.openviking.ai/zh/about/01-about-us#微信群"><img src="docs/images/community/wechat.svg" width="18" height="18" alt="微信">&nbsp;微信</a> ·
  <a href="https://discord.com/invite/eHvx8E9XF3"><img src="docs/images/community/discord.svg" width="18" height="18" alt="Discord">&nbsp;Discord</a> ·
  <a href="https://x.com/openvikingai"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/community/x-dark.svg"><img src="docs/images/community/x.svg" width="16" height="16" alt="X"></picture>&nbsp;X</a>
</p>

<a href="https://trendshift.io/repositories/19668" target="_blank"><img src="https://trendshift.io/api/badge/repositories/19668" alt="volcengine%2FOpenViking | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a>

</div>

***

## Business Data Platform 是什麼

Business Data Platform 是面向 AI 智慧體的開源上下文資料庫——用一個檔案系統裝下 Agent 所知道的一切：知識、記憶和技能。

大多數 Agent 記憶是個黑盒：文本進去，向量出來，沒人看得到裡面到底存了什麼。Business Data Platform 換一種做法，把上下文組織成 `viking://` 虛擬檔案系統。Agent 像操作檔案一樣用 `ls`、`tree`、`read`、`write`、`grep` 瀏覽和修改；你也可以隨時開啟目錄，檢視和編輯 Agent 記住的內容。每個目錄都帶有自動生成的摘要，Agent 先掃摘要，再決定讀哪些內容。

<a href="https://openviking.ai/studio" target="_blank" rel="noopener noreferrer">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/images/studio-playground-dark.png">
    <img src="docs/images/studio-playground.png" alt="Business Data Platform Studio：瀏覽上下文，體驗語義檢索">
  </picture>
</a>

[線上體驗 Business Data Platform Studio](https://openviking.ai/studio)，無需安裝。 [自行部署 Web Studio](web-studio/README_CN.md)。

## 為什麼用 Business Data Platform

- **一個檔案系統，裝下知識、記憶和技能。** 資源存放文件和程式碼，記憶保留使用者偏好與經驗，技能定義任務的執行方式——不只是抽取出來的"記憶條目"，而是完整上下文，每一項都有 `viking://` URI 供瀏覽和檢索。→ [Viking URI](https://docs.openviking.ai/zh/concepts/04-viking-uri) · [上下文型別](https://docs.openviking.ai/zh/concepts/02-context-types)
- **在目錄裡檢索，而不是在整個索引裡撈。** 把語義檢索限定在某個專案或記憶子樹內，而不是掃描一個扁平的向量池。`find` 直接執行查詢，`search` 結合會話上下文規劃檢索。→ [檢索機制](https://docs.openviking.ai/zh/concepts/07-retrieval)
- **先看摘要，再讀原文。** 自動生成的目錄摘要（L0）和概覽（L1）幫助 Agent 判斷相關性，再決定是否讀取全文（L2）。→ [上下文分層](https://docs.openviking.ai/zh/concepts/03-context-layers)
- **會話沉澱為可讀的檔案。** 提交會話後，對話被歸檔，記憶被提取為可檢視、可編輯、可合併的 Markdown。啟用 VikingBot 後，`ov compile` 還能把資料整理成 Wiki、知識圖譜或報告。→ [會話管理](https://docs.openviking.ai/zh/concepts/08-session) · [上下文編譯](https://docs.openviking.ai/zh/context-compilation/01-overview)

[架構](https://docs.openviking.ai/zh/concepts/01-architecture) · [設計思路](https://blog.openviking.ai/post/openviking-context-database/)

```
viking://
├── resources/              # 資源：專案文件、程式碼庫、網頁等
│   └── my_project/
│       ├── docs/
│       │   ├── api/
│       │   └── tutorials/
│       └── src/
└── user/
    └── {user_id}/
        ├── memories/
        │   └── preferences/
        │       ├── writing_style
        │       └── coding_habits
        ├── resources/
        │   └── private_project/
        ├── skills/
        │   ├── search_code
        │   └── analyze_data
        └── peers/
            └── web-visitor-alice/
```

三個載入層級：

- **L0（摘要）**：一句話總結，用來快速判斷相關性。
- **L1（概覽）**：核心資訊和使用場景，供規劃階段決策。
- **L2（詳情）**：完整原始資料，只在需要時讀取。

經過語義處理的目錄帶有 L0/L1 摘要，Agent 可以先判斷相關性，再讀取全文：

```
viking://resources/my_project/
├── .abstract.md           # L0：約 100 tokens——快速判斷相關性
├── .overview.md           # L1：約 2k tokens——結構和要點
└── docs/
    ├── .abstract.md
    ├── .overview.md
    └── api/
        ├── auth.md         # L2：完整內容，按需載入
        └── endpoints.md
```

## 評測結果

Business Data Platform 0.3.22 的評測覆蓋長對話使用者記憶（LoCoMo）和多輪智慧體任務（tau2-bench）。完整結果和實驗設定（含知識庫問答）見[評測報告](https://blog.openviking.ai/post/openviking-benchmark-results/)，復現指令碼在 [./benchmark](./benchmark)。

記憶評測使用 [Doubao 2.0 Pro](https://console.volcengine.com/ark/region:cn-beijing/model/detail?Id=doubao-seed-2-0-pro) 作為 VLM，使用 [Doubao-embedding-vision-251215](https://console.volcengine.com/ark/region:cn-beijing/model/detail?Id=doubao-embedding-vision) 作為 Embedding 模型。

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/benchmark-dark.svg">
  <img alt="Benchmark results. LoCoMo accuracy: OpenClaw 24.20% native vs 82.08% with Business Data Platform; Hermes 33.38% vs 82.86%; Claude Code 57.21% vs 80.32%. tau2-bench task success: Retail 70.94% vs 77.81%; Airline 54.38% vs 66.25%." src="docs/images/benchmark-light.svg">
</picture>

- **使用者記憶（LoCoMo）**：接入 Business Data Platform 後，三種 Agent 整合的準確率都到 80–83%，原生記憶只有 24–57%；同時輸入 token 減少 34.3%–91.0%，查詢時延降低 58.45%–66.10%。
- **智慧體經驗（tau2-bench）**：經驗記憶讓任務成功率在 Retail 提升 6.87pp、Airline 提升 11.87pp（對比同一 LLM 無記憶）。

## 快速開始

需要 Python 3.10+，以及可呼叫的 Embedding 模型和 VLM（雲端或本地）。

```bash
pip install openviking --upgrade
openviking-server init      # 配置模型與提供商
openviking-server doctor    # 檢查配置與連通性
openviking-server           # 啟動伺服器
```

`init` 將配置寫入 `~/.openviking/ov.conf`，支援火山引擎、OpenAI、Codex OAuth、Kimi、GLM 和本地 Ollama 等選項。模型配置見[配置指南](https://docs.openviking.ai/zh/guides/01-configuration)，各平臺安裝說明見[快速入門文件](https://docs.openviking.ai/zh/getting-started/02-quickstart)。

安裝包包含 `ov` CLI。在另一個終端匯入程式碼庫並檢索：

```bash
ov status
ov add-resource https://github.com/volcengine/OpenViking
# 將 TASK_ID 替換為返回的 task_id；重複查詢，直到狀態為 completed
ov task status TASK_ID
ov ls viking://resources/
ov tree viking://resources/volcengine -L 2
ov find "what is openviking"
ov grep "openviking" --uri viking://resources/volcengine/OpenViking/docs/zh
```

`ov find` 返回匹配的上下文及其 URI，可繼續檢視內容。客戶端配置（`ov config`）、CLI 獨立安裝和索引維護，見 [CLI 安裝](https://docs.openviking.ai/zh/getting-started/05-cli-setup)。

構建自己的應用，可使用 [Python](sdk/python/README_CN.md)、[Go](sdk/go/README_CN.md)、[TypeScript](sdk/typescript/README_CN.md) SDK 或 [HTTP API](https://docs.openviking.ai/zh/api/01-overview)。

## 接入你的 Agent

將 Agent 接入 Business Data Platform，跨會話保留記憶。原生整合支援自動召回與會話採集；也可通過 MCP 提供記憶和上下文工具。

<table>
<tbody>
<tr>
<td align="center" valign="bottom" width="16%">
<a href="https://docs.openviking.ai/zh/agent-integrations/02-claude-code"><img src="docs/images/integrations/logos/claude-code.png" width="32" height="32" alt=""><br><strong>Claude</strong></a><br>
<sub>Hooks&nbsp;+&nbsp;MCP</sub>
</td>
<td align="center" valign="bottom" width="16%">
<a href="https://docs.openviking.ai/zh/agent-integrations/04-codex"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/integrations/logos/openai-dark.svg"><img src="docs/images/integrations/logos/openai.svg" width="32" height="32" alt=""></picture><br><strong>Codex</strong></a><br>
<sub>Hooks&nbsp;+&nbsp;MCP</sub>
</td>
<td align="center" valign="bottom" width="16%">
<a href="https://docs.openviking.ai/zh/agent-integrations/12-cursor"><img src="docs/images/integrations/logos/cursor.png" width="32" height="32" alt=""><br><strong>Cursor</strong></a><br>
<sub>Hooks&nbsp;+&nbsp;MCP</sub>
</td>
<td align="center" valign="bottom" width="16%">
<a href="https://docs.openviking.ai/zh/agent-integrations/13-trae"><img src="docs/images/integrations/logos/trae.png" width="32" height="32" alt=""><br><strong>TRAE</strong></a><br>
<sub>Hooks&nbsp;+&nbsp;MCP</sub>
</td>
<td align="center" valign="bottom" width="16%">
<a href="https://docs.openviking.ai/zh/agent-integrations/03-openclaw"><img src="docs/images/integrations/logos/openclaw.png" width="32" height="32" alt=""><br><strong>OpenClaw</strong></a><br>
<sub>上下文引擎</sub>
</td>
<td align="center" valign="bottom" width="16%">
<a href="https://docs.openviking.ai/zh/agent-integrations/05-hermes"><img src="docs/images/integrations/logos/hermes-agent.png" width="32" height="32" alt=""><br><strong>Hermes</strong></a><br>
<sub>內建記憶</sub>
</td>
</tr>
</tbody>
<tbody>
<tr>
<td align="center" valign="bottom" width="16%">
<a href="https://docs.openviking.ai/zh/agent-integrations/10-opencode"><img src="docs/images/integrations/logos/opencode.png" width="32" height="32" alt=""><br><strong>OpenCode</strong></a><br>
<sub>Plugin&nbsp;+&nbsp;MCP</sub>
</td>
<td align="center" valign="bottom" width="16%">
<a href="https://docs.openviking.ai/zh/agent-integrations/11-pi"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/integrations/logos/pi-dark.svg"><img src="docs/images/integrations/logos/pi.svg" width="32" height="32" alt=""></picture><br><strong>pi</strong></a><br>
<sub>原生擴充</sub>
</td>
<td align="center" valign="bottom" width="16%">
<a href="docs/images/agents/zh/deerflow-memory-manager.md"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/integrations/logos/deerflow-dark.svg"><img src="docs/images/integrations/logos/deerflow.svg" width="32" height="32" alt=""></picture><br><strong>DeerFlow</strong></a><br>
<sub>Plugin&nbsp;+&nbsp;MCP</sub>
</td>
<td align="center" valign="bottom" width="16%">
<a href="https://docs.openviking.ai/zh/agent-integrations/17-dsh"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/integrations/logos/dsh-dark.svg"><img src="docs/images/integrations/logos/dsh.svg" width="32" height="32" alt=""></picture><br><strong>DSH</strong></a><br>
<sub>Plugin&nbsp;+&nbsp;MCP</sub>
</td>
<td align="center" valign="bottom" width="16%">
<a href="docs/images/agents/zh/doubao-work.md"><img src="docs/images/integrations/logos/doubao-work.png" width="32" height="32" alt=""><br><strong>豆包工作</strong></a><br>
<sub>連接器</sub>
</td>
<td align="center" valign="bottom" width="16%">
<a href="https://docs.openviking.ai/zh/agent-integrations/07-langchain-langgraph"><img src="docs/images/integrations/logos/langchain.svg" width="32" height="32" alt=""><br><strong>LangChain</strong></a><br>
<sub>工具&nbsp;+&nbsp;儲存</sub>
</td>
</tr>
</tbody>
</table>

**通用接入**

<table>
<tr>
<td align="center" valign="bottom" width="50%">
<a href="https://docs.openviking.ai/zh/agent-integrations/15-agent-plugins"><img src="docs/images/integrations/logos/agent-plugins.svg" width="32" height="32" alt=""><br><strong>Agent&nbsp;Plugins&nbsp;1.0</strong></a>
</td>
<td align="center" valign="bottom" width="50%">
<a href="https://docs.openviking.ai/zh/agent-integrations/06-mcp-clients"><img src="docs/images/integrations/logos/mcp.svg" width="32" height="32" alt=""><br><strong>MCP&nbsp;客&#8288;戶&#8288;端</strong></a>
</td>
</tr>
</table>

詳細接入方式請參考 [Integrations](https://openviking.ai/integrations)。

## 桌面客戶端（Beta）

桌面客戶端是面向 macOS 和 Windows x64 的控制台（Beta），用於配置支援的本地 Agent 接入、檢視會話中的召回與捕獲事件，並將本地記憶和技能同步到 Business Data Platform。

下載：

- [macOS Apple Silicon 版（arm64）](https://lf3-cdn-tos.bytegoofy.com/obj/tron-demo/7654844610543360265/420238785/0.0.19/darwin-arm64/openviking-helper-0.0.19-arm64.dmg)
- [macOS Intel 版（x64）](https://lf3-cdn-tos.bytegoofy.com/obj/tron-demo/7654844610543360265/420238785/0.0.19/darwin-x64/openviking-helper-0.0.19-x64.dmg)
- [Windows 版（x64）](https://lf3-cdn-tos.bytegoofy.com/obj/tron-demo/7654844610543360265/420238785/0.0.19/win32-x64/openviking-helper-0.0.19-x64.exe)

## VikingBot

VikingBot 是構建在 Business Data Platform 之上的 AI 智慧體框架：

```bash
pip install "openviking[bot]"
openviking-server --with-bot
ov chat   # 在另一個終端執行
```

官方 Docker 映象內建 VikingBot，預設隨伺服器和控制台 UI 一起啟動。詳情見 [VikingBot 指南](https://docs.openviking.ai/zh/guides/17-vikingbot)。

## 生產部署

開源伺服器採用 [AGPLv3](LICENSE)，可在自己的環境部署，無需啟用碼。見[伺服器配置](https://docs.openviking.ai/zh/getting-started/03-quickstart-server)和 [Docker 與部署指南](https://docs.openviking.ai/zh/guides/03-deployment)。

伺服器支援[帳號與使用者隔離](https://docs.openviking.ai/zh/concepts/11-multi-tenant)，並可按需啟用[資源 ACL](https://docs.openviking.ai/zh/concepts/15-acl)。開放非本機訪問前，需配置[身份認證](https://docs.openviking.ai/zh/guides/04-authentication)。

## 商業版本

<table>
<tr>
<td width="50%" valign="top">

<img src="docs/images/commercial-saas.png" alt="商業化 SaaS 版" width="100%" />

<h3>☁️ 商業化 SaaS 版</h3>
<p>由<a href="https://www.volcengine.com/product/openviking-service">火山引擎</a>託管和運維，提供個人版、企業版，以及開源部署的遷移工具。套餐與額度見<a href="https://docs.volcengine.com/docs/84313/2374478">服務文件</a>。中國以外地區的託管服務計劃在 <a href="https://www.byteplus.com">BytePlus</a> 上線。</p>

</td>
<td width="50%" valign="top">

<img src="docs/images/commercial-self-hosted.png" alt="私有化部署版" width="100%" />

<h3>🏢 私有化部署版</h3>
<p>部署在自己的雲帳號 / VPC（BYOC）或離線環境中，提供分散式部署和官方技術支援，通過啟用碼啟用。<a href="https://docs.google.com/forms/d/e/1FAIpQLScQqwsm7fvKdjtNiW5rWNXJjoHPtedVzLsKSMJgObtsj2_udA/viewform">諮詢私有化部署</a>。</p>

</td>
</tr>
</table>

## 研究

**讓 Agent 的記憶隨互動演化。** VikingMem 以事件驅動長期記憶的提取、更新與整合，讓有狀態 Agent 在持續互動中積累可複用的經驗。Business Data Platform 開源了其中的部分核心能力。

> **VikingMem: A Memory Base Management System for Stateful LLM-based Applications**<br>
> Jiajie Fu, Junwen Chen, Mengzhao Wang, Aoxiang He, Maojia Sheng, Xiangyu Ke, Yifan Zhu, and Yunjun Gao.<br>
> arXiv:2605.29640, 2026。已於 2026 年 9 月在 VLDB 2026 完成演講。<br>
> 📄 [在 arXiv 閱讀論文](https://arxiv.org/abs/2605.29640) · [閱讀 PDF](https://arxiv.org/pdf/2605.29640)

**讓目錄結構成為檢索上下文。** 這篇論文為 Business Data Platform 的目錄語義檢索提供形式化基礎、索引設計與實驗驗證。論文定義了目錄範圍查詢與結構維護操作，並提出 TrieHI，Business Data Platform 已將其整合，用於在向量排序前確定目錄檢索範圍。檔案系統範式由此貫穿組織與檢索：Agent 可以在專案或記憶子樹內查詢證據、保留周邊上下文，並隨知識演化調整目錄結構。

> **Directory-Aware Query and Maintenance in Vector Databases**<br>
> Mengzhao Wang, Zheng Gong, Jingpei Hu, Jiajie Fu, Maojia Sheng, Junwen Chen, and Yifan Zhu.<br>
> arXiv:2606.16903, 2026。已被 ICDE 接收。<br>
> 📄 [在 arXiv 閱讀論文](https://arxiv.org/abs/2606.16903) · [閱讀 PDF](https://arxiv.org/pdf/2606.16903)

**用更少的 Token 找齊回答所需的證據。** VikingRAG 將語義檢索與文件結構結合，按證據缺口展開相關目錄片段，核心機制已整合到 Business Data Platform。論文進一步研究檢索軌跡複用與按需升級多輪檢索，在保持回答質量的同時減少重複探索。

> **VikingRAG: Accurate and Token-efficient Retrieval-augmented Generation over Structured Documents**<br>
> Peiyuan Gao, Gaoyuan Zhang, Haojie Qin, Yahui Sun, Qianyi Zhang, Yunhao Zhang, Zeyu Wang, and Wei Lu.<br>
> arXiv:2609.11390, 2026。投遞中。<br>
> 📄 [在 arXiv 閱讀論文](https://arxiv.org/abs/2609.11390) · [閱讀 PDF](https://arxiv.org/pdf/2609.11390)

## 合作伙伴

- [deer-flow](https://github.com/bytedance/deer-flow) - 開源的長週期 SuperAgent 框架
- [NoKV](https://github.com/NoKV-Lab/NoKV) - AI 原生的分散式檔案系統
- [loopx](https://github.com/huangruiteng/loopx) - 輕量級迴圈工程狀態核心
- [Hermes Agent](https://github.com/NousResearch/hermes-agent) - 與使用者共同成長的智慧體

合作提議請[提交 issue](https://github.com/volcengine/OpenViking/issues)。

## 社群與貢獻

- **文件**：[docs.openviking.ai](https://docs.openviking.ai/) · [FAQ](https://docs.openviking.ai/zh/faq/faq)
- **博客**：[blog.openviking.ai](https://blog.openviking.ai/)
- **團隊**：[關於我們](https://docs.openviking.ai/zh/about/01-about-us)
- **交流**：<a href="https://docs.openviking.ai/zh/about/01-about-us#微信群"><img src="docs/images/community/wechat.svg" width="18" height="18" alt="微信">&nbsp;微信</a> · <a href="https://discord.com/invite/eHvx8E9XF3"><img src="docs/images/community/discord.svg" width="18" height="18" alt="Discord">&nbsp;Discord</a> · <a href="https://x.com/openvikingai"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/community/x-dark.svg"><img src="docs/images/community/x.svg" width="16" height="16" alt="X"></picture>&nbsp;X</a>
- **貢獻**：修 bug、加新功能都歡迎——見 [CONTRIBUTING_CN.md](CONTRIBUTING_CN.md)

<a href="https://github.com/volcengine/OpenViking/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=volcengine/OpenViking&amp;columns=15&amp;max=120" alt="Business Data Platform contributors" />
</a>

## 安全與隱私

漏洞報告方式和受支援的版本，見 [SECURITY.md](SECURITY.md)

## 許可證

Business Data Platform 各元件採用不同的許可證：

- **主專案**：AGPLv3——詳見 [LICENSE](./LICENSE)
- **crates/ov\_cli**：Apache 2.0——詳見 [LICENSE](./crates/LICENSE)
- **examples**：Apache 2.0——詳見 [LICENSE](./examples/LICENSE)。`examples/hermes-plugin` 中的 Hermes 外掛保留其 [MIT 許可證](./examples/hermes-plugin/LICENSE)。
- **third\_party**：各三方專案保留其原有協議
