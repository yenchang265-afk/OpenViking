# 服務角色與啟停

`server.roles` 支援 `api`、`queue_worker`、`scheduler` 的任意非空組合，預設全部啟用；`--roles` 可覆蓋配置：

```bash
openviking-server --config ov.conf --roles api
openviking-server --config ov.conf --roles queue_worker --workers 2
openviking-server --config ov.conf --roles scheduler
```

| 角色 | 啟動內容 |
| --- | --- |
| `api` | 業務 HTTP / MCP；按配置啟用 Studio、OAuth、Gateway |
| `queue_worker` | 佇列任務處理與到期清理 |
| `scheduler` | 已啟用的 Watch、Compile、Session idle、歸檔規則清理掃描；到期任務釋出 |

`--workers` 指定程序數，各 worker 載入相同角色。
各節點註冊 `/health`、`/ready`，以及需要鑑權的
`/api/v1/system/status`、`/api/v1/system/wait`、`/api/v1/system/consistency`。
`/metrics` 按配置啟用。其他路由和 MCP 要求 `api`，`--with-bot` 也要求 `api`。

- OAuth 或內嵌 Gateway（`gateway.enabled: true`）要求所有角色同進程部署，保證 Account/User 刪除完整。
- 使用內建 VikingBot 的 Skill Compile 要求 `api` 和 `queue_worker` 同進程執行；拆分時，兩端配置 `compile_api.base_url`，指向共同可訪問的 Compile Runtime。

啟動先準備儲存和帳戶能力、恢復任務，再啟用角色。
SIGINT/SIGTERM 先停生產者、排空消費者及寫入，再關閉依賴；無法排空時保留依賴。
退出指令碼須等待清理完成。

配置重新整理、Task 維護和到期登記按配置在各節點執行。

含 `scheduler` 且啟用 Redis 到期功能時，預設由父程序託管獨立 Expiry publisher。
`expiry.publisher_separate_process=false` 指定程序內執行。

嵌入 Core 按 `initialize()` → 依賴接線 → `recover()` → `start_background()` 呼叫。
`create_app(service=...)` 接收尚未執行的服務，儲存由呼叫方管理。
同一服務支援一次宿主 lifespan，啟動與關閉須在同一 task 內完成。

多程序要求共享儲存；本地儲存使用獨佔鎖。
scheduler 按模組協調，沒有覆蓋所有掃描任務的統一 leader。
