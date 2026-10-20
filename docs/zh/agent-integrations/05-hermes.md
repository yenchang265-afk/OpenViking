# Hermes

為 [Hermes Agent](https://hermes-agent.nousresearch.com/) 配置 OpenViking 長期記憶。

## 開始使用

在要使用的 Hermes profile 中執行：

```bash
hermes plugins install openviking --enable
hermes memory setup openviking
hermes
```

安裝時接受依賴安裝提示。如果當前 Hermes 版本仍內建 OpenViking，請跳過安裝命令。
該版本會使用內建副本，不提供 Quick Local。

對話歷史用於理解當前聊天。長期記憶儲存有用的資訊，供後續聊天使用。
公共記憶是不屬於某個傳送者的記憶。

選擇 **Personal Agent** 可召回公共記憶和當前傳送者的記憶，並保留現有對話歷史設定。
選擇 **Shared Agent** 可在每個群組或話題內共享對話歷史，並召回同一 OpenViking 使用者
下所有傳送者的記憶。Shared Agent 會要求確認。

然後選擇連線方式：

- **Quick Local** 安裝本地服務和 embedding 模型，複用受支援的 Hermes LLM 抽取記憶。
  LLM 仍可使用遠端 API。
- **OpenViking Service (VolcEngine Cloud)** 通過服務 API Key 連線火山引擎的
  [OpenViking 託管雲服務](https://www.volcengine.com/product/openviking-service?utm_source=opensource_docs&utm_medium=referral&utm_campaign=agent-integrations_05-hermes)，
  無需安裝服務端或配置本地模型。
- **Custom** 使用 URL 和憑據連線自己的服務，也可以複用已儲存的 `ovcli.conf`。

配置後正常聊天即可。外掛預設在待提交內容達到 20,000 tokens、會話結束或切換時
請求提交。OpenViking 完成抽取後，記憶才能被召回。已有服務端資料會保留。

Quick Local 服務在 Hermes 退出後仍會執行。支援的模型、服務控制命令和執行環境
升級說明見[外掛指南](https://hermes-agent.nousresearch.com/docs/plugins/openviking)。

## 檢視狀態

```bash
hermes memory status
```

`available` 表示 provider 已配置，不代表服務健康，也不代表記憶抽取成功。

## 更新

```bash
hermes plugins update openviking
```

更新後重啟 Hermes 或 gateway。連線設定和資料會保留。更新 Quick Local 服務時，
重新執行配置嚮導並選擇 Quick Local。正常聊天使用已安裝的服務，不會檢查更新。

Hermes 更新移除內建副本時，會為已使用 OpenViking 的 profile 嘗試安裝目錄外掛。
如果失敗，請在該 profile 中執行上面的安裝命令。

## 更多資訊

- [外掛指南](https://hermes-agent.nousresearch.com/docs/plugins/openviking)
- [整合能力參考](./16-capability-reference.md)
- [服務部署](../guides/03-deployment.md)
- [API Key](../guides/04-authentication.md)
