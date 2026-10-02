## 步驟1：安裝

1. 安裝 OpenViking 外掛：

   ```bash
   openclaw plugins install clawhub:@openviking/openclaw-plugin
   ```

2. 將 OpenClaw 連線至火山引擎託管的 OpenViking 服務：

   ```bash
   openclaw openviking setup --base-url https://api.vikingdb.cn-beijing.volces.com/openviking --api-key <$OPENVIKING_API_KEY>
   ```

3. 配置 `peer_role`：`peer_role` 用於標識對話參與者的型別，並非許可權角色。其中，`assistant` 表示不同的 Agent、工具或模型，`person` 表示不同的人類參與者。完成上述配置後，`peer_role` 預設為 `none`。如需調整 `peer_role`，可執行以下命令：

   ```bash
   openclaw openviking setup --reconfigure
   ```

4. 重啟 Gateway 使配置生效：

   ```bash
   openclaw gateway restart
   ```

## 步驟2：驗證

1. 在終端執行如下命令檢查接入狀態：

   ```bash
   openclaw openviking status
   ```

2. 返回如下結果即表示接入成功：

   ```text
   🦣 OpenViking Plugin Status

     Status: Configured
     mode:      remote
     baseUrl:   `https://api.vikingdb.cn-beijing.volces.com/openviking`
     apiKey:    set
     peer_role: none
     accountId: not set
     userId:    not set
     slot:      active

     ✓ Server reachable (version: v0.x.xx.x)
   ```

## 故障排查

| 問題 | 處理 |
|---|---|
| 外掛未生效 | 重跑安裝，再執行 `openclaw gateway restart` |
| 401 / 403 | 檢查鑑權憑據 |

## 參考

- 手動配置文件：[OpenClaw](https://docs.openviking.net/zh/agent-integrations/03-openclaw)
- 原始碼：[examples/openclaw-plugin](https://github.com/volcengine/OpenViking/tree/main/examples/openclaw-plugin)
