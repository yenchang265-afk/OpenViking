# 團隊與組織

## 專案概述

OpenViking 是面向 AI Agent 的開源上下文資料庫，由字節跳動火山引擎 Viking 團隊發起並維護。它用檔案系統組織資源、記憶和技能，供 Agent 瀏覽、檢索和按需讀取。

[在 GitHub 檢視 OpenViking](https://github.com/volcengine/OpenViking)

## 團隊介紹

### Viking 團隊背景

Viking 團隊主要開發向量檢索、知識庫和記憶管理產品。團隊有數十名工程師，覆蓋分散式系統、機器學習、資料工程和 AI 演算法，在上下文工程上有商業化落地經驗。OpenViking 將這些領域的工程經驗用於開源上下文資料庫，與社群共同開發。

#### 核心技術能力

**大規模向量檢索系統**
- 支撐億級向量資料的即時檢索與相似度計算
- 具備毫秒級響應能力，滿足高併發業務場景需求
- 支援混合檢索策略，結合語義相似性與關鍵詞匹配

**多模態內容理解引擎**
- 支援文本、影像、音訊、影片等多種資料型別的智慧解析
- 實現跨模態語義關聯與內容理解
- 提供統一的內容抽象與語義表示

**分散式系統架構設計**
- 具備構建高可用、可擴充分散式系統的豐富實踐經驗
- 支援彈性伸縮與故障自動恢復機制
- 實現資料一致性與系統性能的最佳平衡

這些工作涉及三個相互關聯的問題：如何從非結構化內容中提取可檢索的資訊，如何在大量候選內容中找到相關上下文，以及如何保留對後續任務有用的互動經驗。OpenViking 對應提供[資源解析與提取](../concepts/06-extraction.md)、[上下文檢索](../concepts/07-retrieval.md)和[會話與記憶管理](../concepts/08-session.md)。可沿這些入口瞭解實現和使用條件。

### 發展歷程與技術演進

| 時間階段 | 里程碑事件 | 技術突破與產業影響 |
|----------|-----------|-------------------|
| **2019-2023** | VikingDB 向量資料庫在字節跳動內部大規模應用 | 支撐了公司內部多個核心產品的非結構化資訊檢索需求，積累了大規模向量檢索的工程實踐經驗，驗證了向量資料庫在真實業務場景中的技術價值 |
| **2024年** | 推出面向開發者的產品矩陣：VikingDB、Viking知識庫、Viking記憶庫 | 在火山引擎公有云平臺正式提供服務，已成功支撐數千家企業客戶開發 AI 原生應用，標誌著上下文工程技術從內部工具向商業化產品的成功轉型 |
| **2025年** | 擴充至 AI 搜尋、知識助手等上層應用產品 | 構建了從基礎設施到應用層的完整產品矩陣，進一步驗證了上下文工程技術在不同業務場景中的商業價值，形成了技術到產品的完整閉環 |
| **2025年末** | 開源 [MineContext](https://github.com/volcengine/MineContext) 專案 | 探索主動式服務的 AI 應用模式，驗證個人上下文工程的技術理念，為 OpenViking 的開源積累了社群運營經驗 |
| **2026年初** | 開源 OpenViking 專案 | 推出全新設計的上下文資料庫架構，為全球 AI Agent 生態系統提供開源基礎設施，標誌著 Viking 團隊從商業產品提供商向開源技術貢獻者的戰略轉變 |

### 學術合作與產學研結合

OpenViking 自啟動起就與高校和研究機構合作，共同探索面向 AI Agent 的上下文資料庫設計與工程實踐，讓研究工作貼近實際應用需求。

我們誠摯感謝以下學者的寶貴貢獻與技術指導，共同發起了 OpenViking 專案：

- 中國人民大學資訊學院副教授孫亞輝老師
- 浙江大學軟體學院教授高雲君老師，研究員朱軼凡、葛叢叢老師
- 上海交通大學人工智慧學院副教授，無問芯穹聯合創始人兼首席科學家戴國浩老師

我們與學術界的合作模式包括：

- **聯合研究專案**：共同開展上下文工程的前沿研究
- **技術研討會**：定期組織學術交流與技術方案評審
- **人才培養**：為研究生提供實踐平臺與研究課題
- **成果轉化**：將學術研究成果轉化為工程實踐

### 研究論文

以下論文來自上述合作，其中部分核心機制已整合到 OpenViking。

- **VikingMem: A Memory Base Management System for Stateful LLM-based Applications**<br>
  Jiajie Fu, Junwen Chen, Mengzhao Wang, Aoxiang He, Maojia Sheng, Xiangyu Ke, Yifan Zhu, and Yunjun Gao. arXiv:2605.29640, 2026。已在 VLDB 2026 演講。<br>
  以事件驅動長期記憶的提取、更新與整合，服務有狀態 Agent。[arXiv](https://arxiv.org/abs/2605.29640) · [PDF](https://arxiv.org/pdf/2605.29640)
- **Directory-Aware Query and Maintenance in Vector Databases**<br>
  Mengzhao Wang, Zheng Gong, Jingpei Hu, Jiajie Fu, Maojia Sheng, Junwen Chen, and Yifan Zhu. arXiv:2606.16903, 2026。已被 ICDE 接收。<br>
  目錄範圍檢索的形式化基礎與索引設計（TrieHI），OpenViking 用它在向量排序前確定目錄檢索範圍。[arXiv](https://arxiv.org/abs/2606.16903) · [PDF](https://arxiv.org/pdf/2606.16903)
- **VikingRAG: Accurate and Token-efficient Retrieval-augmented Generation over Structured Documents**<br>
  Peiyuan Gao, Gaoyuan Zhang, Haojie Qin, Yahui Sun, Qianyi Zhang, Yunhao Zhang, Zeyu Wang, and Wei Lu. arXiv:2609.11390, 2026。投遞中。<br>
  將語義檢索與文件結構結合，按證據缺口展開相關目錄片段。[arXiv](https://arxiv.org/abs/2609.11390) · [PDF](https://arxiv.org/pdf/2609.11390)

## 開源組織建設

### 專案發展階段

專案圍繞上下文儲存與檢索、Agent 整合和部署能力持續迭代。已實現的能力與後續方向見[路線圖](03-roadmap.md)，已釋出的變更見[更新日誌](02-changelog.md)。

### 治理架構與決策機制

開源治理委員會負責技術路線、版本與功能優先順序、核心架構和相容性評審、工程規範、貢獻者協作，以及相關專案的整合。成員包括 Maojia Sheng（[@MaojiaSheng](https://github.com/MaojiaSheng)）、Haojie Qin（[@qin-ctx](https://github.com/qin-ctx)）、Jiahui Zhou（[@zhoujh01](https://github.com/zhoujh01)）、Zhiheng Liu（[@ZaynJarvis](https://github.com/ZaynJarvis)）。符合條件的社群貢獻者可以通過後續的提名與選舉程式加入委員會。

具體模組的協作入口和近期活躍評審者見[貢獻指南](https://github.com/volcengine/OpenViking/blob/main/docs/repository/CONTRIBUTING_CN.md)。

功能建議和問題在 [GitHub Issues](https://github.com/volcengine/OpenViking/issues) 討論，程式碼與文件變更通過 Pull Request 評審。涉及公開介面、資料儲存、許可權邊界或跨模組架構的改動，請先說明當前行為、目標行為、請求或配置示例，以及相容性影響，再開始實現。

## 社群參與

### 加入社群

#### 微信群

掃描二維碼新增小助手，備註“OpenViking”，申請加入交流群：

![微信掃碼加群](../../images/wechat-group-qrcode.png)

也可以加入 [Discord](https://discord.com/invite/eHvx8E9XF3)，或在 [X](https://x.com/openvikingai) 檢視專案動態。

### 參與方式

- **報告問題或提建議**：在 [Issues](https://github.com/volcengine/OpenViking/issues) 提供場景、版本和復現步驟。
- **改程式碼或文件**：閱讀[貢獻指南](https://github.com/volcengine/OpenViking/blob/main/docs/repository/CONTRIBUTING_CN.md)，提交實現、測試、文件或翻譯。
- **開發整合**：為 Agent 工具或框架新增外掛，參考[外掛開發指南](../agent-integrations/18-plugin-development.md)。
- **分享經驗**：在社群分享使用案例、排障過程，或幫助其他使用者解決問題。

Issue 和 PR 需要提供的資訊見[貢獻指南](https://github.com/volcengine/OpenViking/blob/main/docs/repository/CONTRIBUTING_CN.md)。

## 討論與協作機制

[GitHub 倉庫](https://github.com/volcengine/OpenViking) 儲存程式碼、文件和評審記錄。[GitHub Discussions](https://github.com/volcengine/OpenViking/discussions) 用於技術方案討論和社群交流，群聊適合即時交流；需要跟蹤的問題和方案請同步到 Issue 或 Pull Request，方便後續查閱和協作。

希望開展技術合作或生態整合的研究機構和企業，可以在 GitHub Discussions 發起討論。
