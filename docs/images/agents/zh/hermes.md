# 為 Hermes 配置 OpenViking Service

[OpenViking Service](https://www.volcengine.com/product/openviking-service) 是
火山引擎託管和運營的 OpenViking 雲服務，無需安裝服務端或配置本地模型。
在 [OpenViking 控制台](https://console.volcengine.com/vikingdb/openviking/region:openviking+cn-beijing)
開通服務，然後從**使用者管理**的 **API Key** 中建立金鑰。

## 安裝和配置

在要使用的 Hermes profile 中執行：

```bash
hermes plugins install openviking --enable
hermes memory setup openviking
```

安裝時接受依賴安裝提示。如果當前 Hermes 版本已內建 OpenViking，請跳過安裝命令。

在嚮導中：

1. 選擇 **Personal Agent** 可召回公共記憶和當前傳送者的記憶，並保留現有歷史設定。
   選擇 **Shared Agent** 可在每個群組或話題內共享歷史，召回同一 OpenViking 使用者
   下所有傳送者的記憶。Shared Agent 會要求確認。
2. 若出現配置來源選項，選擇 **Create new OpenViking profile**。也可以複用已儲存的
   `ovcli.conf`。
3. 選擇 **OpenViking Service (VolcEngine Cloud)**。
4. 輸入服務 API Key。
5. 選擇儲存位置。**Keep in Hermes only** 儲存到 Hermes 的 `.env`。
   **Mirror to OpenViking store** 儲存到本地 `ovcli.conf.<name>` 並關聯到 Hermes。
   兩種方式都會將憑據儲存在當前電腦。
6. 儲存 OpenViking profile 時，填寫名稱，例如 `hermes`。這只是本地配置名稱，
   不會建立使用者或改變訪問許可權。

然後啟動新的 Hermes 會話：

```bash
hermes
```

外部外掛還提供 **Quick Local**，可複用受支援的 Hermes LLM，安裝本地服務和
embedding 模型。要求和已知問題見[外掛指南](https://hermes-agent.nousresearch.com/docs/plugins/openviking)。

## 檢視狀態

```bash
hermes memory status
```

確認 provider 為 `openviking`，狀態為 `available`。這隻表示配置已儲存，
不代表服務健康或記憶抽取成功。

## 故障排查

| 問題 | 處理 |
|------|------|
| 外掛未安裝 | 在該 profile 中執行 `hermes plugins install openviking --enable`。 |
| 使用了其他 provider | 重新執行 `hermes memory setup openviking`。 |
| 狀態不是 available | 檢查儲存的連線設定和關聯的 `ovcli.conf`。 |

## 更多資訊

- [Hermes 整合](https://docs.openviking.net/zh/agent-integrations/05-hermes)
- [外掛指南](https://hermes-agent.nousresearch.com/docs/plugins/openviking)
