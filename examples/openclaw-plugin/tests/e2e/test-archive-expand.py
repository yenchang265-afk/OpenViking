#!/usr/bin/env python3
"""
ov_archive_expand 歸檔展開端到端測試 — 使用者: 小杰（後端開發新人）

================================================================================
一、用例設計思路
================================================================================

核心驗證點:
  當對話累積到一定量後，早期內容會被壓縮歸檔（archive），歸檔摘要只保留概要
  資訊，精確的引數值（IP、埠、命令、hash 等）會在壓縮中丟失。當用戶追問這些
  精確細節時，LLM 需要通過呼叫 ov_archive_expand 工具展開歸檔，從原始對話中
  恢復精確資料，才能給出正確回答。

  本用例通過以下策略驗證該能力:
    1. 注入大量包含精確引數的對話（pod 名、kubectl 命令、PR 編號、行號、
       benchmark 結果、commit hash、incident report 編號等）
    2. 4 批對話 × 8 輪 = 32 輪對話，迫使系統產生多個歸檔
    3. 追問精確細節，驗證 LLM 是否呼叫 ov_archive_expand 並返回精確資料
    4. 對比：概要級問題無需展開即可回答（驗證展開的必要性）

對話資料設計:
  - CHAT_BATCH_1 (8輪): 專案技術細節 — Kafka config、JWT 引數、ClickHouse 表名、
    部署指令碼、告警規則、程式碼規範、bug 修復等
  - CHAT_BATCH_2 (8輪): 線上排障過程 — 具體 pod 名、kubectl 命令、IP 地址、
    tcpdump 命令、配置引數、curl 測試結果、incident report
  - CHAT_BATCH_3 (8輪): 程式碼評審討論 — PR 編號、具體檔案行號、review comment、
    benchmark ns/op、覆蓋率百分比、commit hash、hotfix PR
  - CHAT_BATCH_4 (8輪): 架構設計討論 — Redis 配置、gRPC proto、快取 key 格式、
    HPA 引數、Confluence 頁面 ID

  這些資料包含大量"精確值"（數字、命令、ID），是摘要壓縮時最容易丟失的資訊，
  也是 ov_archive_expand 最核心的價值場景。

驗證查詢設計:
  - EXPAND_QUESTIONS (4題): 追問精確引數 — 預期觸發 ov_archive_expand
    每題設定 expected_keywords 和 target_archive，用關鍵詞命中率 >= 50% 判定
  - NO_EXPAND_QUESTIONS (1題): 概要級問題 — 預期從摘要即可回答，無需展開

斷言策略:
  - 關鍵詞命中率 >= 50% 即判定通過（允許 LLM 回覆的表述差異）
  - 通過 openclaw.log 中的 "ov_archive_expand invoked/expanded" 日誌驗證
    工具是否真正被呼叫

================================================================================
二、測試流程
================================================================================

  Phase 1:   第一段對話 (8 輪) — 專案技術細節 → afterTurn + auto-commit
  Phase 2a:  第二段對話 (8 輪) — 線上排障過程 → afterTurn + auto-commit
  Phase 2b:  第三段對話 (8 輪) — 程式碼評審討論 → afterTurn + auto-commit
  Phase 2c:  第四段對話 (8 輪) — 架構設計討論 → afterTurn + auto-commit
  Phase 3:   驗證 Archive Index — 檢查 commit_count、記憶數、歸檔數
  Phase 4:   追問精確細節 (4 問) — 觸發 ov_archive_expand，驗證關鍵詞命中
  Phase 5:   概要級問題 (1 問) — 驗證無需展開即可回答

  可選: 在 Phase 4 前通過 --gateway-restart-cmd 重啟 Gateway 清除工作記憶，
  迫使 LLM 完全依賴歸檔獲取資訊（更嚴格的驗證）。

================================================================================
三、環境前提
================================================================================

  1. OpenViking 服務已啟動（提供歸檔儲存和展開能力）
  2. OpenClaw Gateway 已啟動並配置了 OpenViking 外掛
  3. LLM 後端可達（Gateway 需要呼叫 LLM 生成回覆和觸發工具呼叫）
  4. 有效的 Gateway auth token（通過 --token 傳入或自動發現）

  關鍵 openclaw.json 配置:
    - plugins.slots.contextEngine = "openviking"
    - plugins.entries.openviking.enabled = true
    - plugins.entries.openviking.config.autoCapture = true
    - plugins.entries.openviking.config.commitTokenThresholdRatio = 0.02
      ↑ 此值控制 auto-commit 時機，按模型上下文視窗的比例計算（0.02 = 2%）。
        32 輪對話需要多次 auto-commit 產生歸檔，比例越小歸檔越多；
        設為 0 表示每輪都 commit。
    - agents.defaults.alsoAllow = ["ov_archive_expand"]
      ↑ 必須顯式允許 ov_archive_expand 工具，否則 LLM 無法呼叫

  服務部署參考:
    - OpenViking: openviking-server（HTTP 預設 2934，AGFS 預設 2833）
    - Gateway: openclaw gateway（HTTP 預設 19789）

================================================================================
四、使用方法
================================================================================

  安裝依賴:
    pip install requests rich

  完整測試 (推薦):
    python test-archive-expand.py --phase all \\
        --gateway http://127.0.0.1:19789 \\
        --openviking http://127.0.0.1:2934 \\
        --token <your_gateway_token>

  分階段執行:
    python test-archive-expand.py --phase chat1       # 僅第一批對話
    python test-archive-expand.py --phase chat2       # 僅第二批對話
    python test-archive-expand.py --phase verify-index # 僅驗證歸檔索引
    python test-archive-expand.py --phase expand       # 僅追問精確細節
    python test-archive-expand.py --phase no-expand    # 僅概要級問題

  其他選項:
    --user-id <id>      固定使用者 ID（預設隨機生成）
    --delay <seconds>    輪次間等待秒數（預設 3s）
    --verbose / -v       詳細輸出（顯示完整 JSON 響應）
    --gateway-restart-cmd <cmd>  Phase 4 前重啟 Gateway 的命令
    --log-path <path>    Gateway 日誌路徑，測試後自動掃描 ov_archive_expand 呼叫記錄

  注意:
    - 完整測試約需 10-15 分鐘（32 輪對話 + 驗證 + 追問）
    - 首次執行前建議清理 OV 資料和 session 資料，避免干擾

================================================================================
五、驗證工具呼叫（日誌檢查）
================================================================================

  本指令碼通過關鍵詞命中率間接驗證 ov_archive_expand 是否生效。如需直接確認
  工具是否被呼叫，可通過以下方式檢查 Gateway 日誌:

  方式 1 — 自動檢查（推薦）:
    傳入 --log-path 引數，指令碼結束後自動掃描並列印工具呼叫記錄:

    python test-archive-expand.py --phase all \\
        --log-path config/.openclaw/logs/openclaw.log

  方式 2 — 手動檢查:
    # Linux / macOS
    grep "ov_archive_expand" config/.openclaw/logs/openclaw.log

    # Windows PowerShell
    Select-String -Path "config\\.openclaw\\logs\\openclaw.log" \\
        -Pattern "ov_archive_expand"

  預期日誌（每次展開會產生一對 invoked + expanded 日誌）:

    openviking: ov_archive_expand invoked (archiveId=archive_001, sessionId=...)
    openviking: ov_archive_expand expanded archive_001, messages=17, chars=82675, ...

  如果 Phase 4 通過但日誌中沒有 ov_archive_expand 記錄，說明 LLM 可能是
  從工作記憶（而非歸檔展開）中獲取的資訊。此時可通過 --gateway-restart-cmd
  在 Phase 4 前重啟 Gateway 清除工作記憶，強制走歸檔展開路徑。

================================================================================
六、已知限制
================================================================================

  1. LLM 是否呼叫 ov_archive_expand:
     不同模型對工具呼叫的傾向性不同。如果模型直接從 archive overview 摘要
     中推測答案而不展開歸檔，關鍵詞可能命中（摘要恰好包含）也可能不命中。
     使用 --gateway-restart-cmd 可強制清除工作記憶，迫使走歸檔展開路徑。

  2. 關鍵詞精確匹配:
     數字格式差異可能導致匹配失敗（如 "12000" vs "12,000" vs "1.2萬"）。
     Q4 的 "12000" 在實際測試中因 LLM 輸出 "12,000" 而未命中，但整體命中率
     仍達 67% 超過 50% 閾值。

  3. 測試耗時:
     完整測試需要 32 輪對話 + 驗證 + 追問，約 10-15 分鐘。如需快速驗證，可
     使用 --phase expand 單獨跑追問階段（前提是已有歸檔資料）。

  4. 對話順序依賴:
     4 批對話必須按順序執行（Phase 1 → 2a → 2b → 2c），因為後續批次的歸檔
     編號依賴前序批次。不能單獨跑 chat2 而跳過 chat1。

  5. 環境要求:
     Gateway 必須配置 OpenViking 外掛且啟用 ov_archive_expand 工具定義，
     否則 LLM 無法呼叫歸檔展開。

================================================================================
七、預期結果
================================================================================

  15/15 斷言全部通過:
    - Phase 1~2c: 32 輪對話全部成功
    - Phase 3: commit_count >= 3, 歸檔數 >= 3, 記憶提取數 > 0
    - Phase 4: 4 個追問全部命中關鍵詞 (>= 50%)
    - Phase 5: 概要回答正確
"""

import argparse
import io
import json
import os
import sys
import time
import uuid
from datetime import datetime
from typing import Any

import requests
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── 常量 ───────────────────────────────────────────────────────────────────

USER_ID = f"xiaojie-{uuid.uuid4().hex[:8]}"
DISPLAY_NAME = "小杰"
DEFAULT_GATEWAY = "http://127.0.0.1:19789"
DEFAULT_OPENVIKING = "http://127.0.0.1:2934"
AGENT_ID = "main"

console = Console(force_terminal=True)

# ── 測試結果收集 ──────────────────────────────────────────────────────────

assertions: list[dict] = []


def check(label: str, condition: bool, detail: str = ""):
    assertions.append({"label": label, "ok": condition, "detail": detail})
    icon = "[green]PASS[/green]" if condition else "[red]FAIL[/red]"
    msg = f"  {icon} {label}"
    if detail:
        msg += f"  [dim]({detail})[/dim]"
    console.print(msg)


# ── 第一批對話: 專案技術細節 (8 輪) ──────────────────────────────────────

CHAT_BATCH_1 = [
    "嗨！我叫小杰，剛入職三個月，在做一個使用者畫像系統。後端用 Go，框架是 Gin，資料庫用 ClickHouse。我想跟你聊聊專案的技術細節，你幫我記一下。",
    "我們的 API 認證用的是自己寫的 JWT 中介軟體，token 過期時間設的 7200 秒，重新整理 token 有效期 30 天，金鑰存在環境變數 AUTH_JWT_SECRET 裡。",
    "資料採集這塊，我寫了個 Kafka consumer，group id 是 user-profile-sync-v2，消費的 topic 是 user_behavior_events，每批最多拉 500 條訊息。",
    "畫像資料的 ClickHouse 表叫 user_profiles_v3，主鍵是 (user_id, event_date)，用了 MergeTree 引擎，TTL 設的 180 天。",
    "部署指令碼在 deploy/scripts/rollout.sh，裡面有個關鍵的金絲雀釋出邏輯，先把 10% 流量切到新版本，觀察 5 分鐘沒報警再全量。",
    "我們的 Prometheus 告警規則在 monitoring/alerts/backend.yml，有一條關鍵的：當 P99 延遲超過 500ms 持續 3 分鐘就會觸發 page 告警。",
    "程式碼規範方面，Go 專案用 golangci-lint，配置檔案在 .golangci.yml，停用了 gocyclo，開啟了 govet、errcheck、staticcheck。",
    "上週修了個嚴重 bug：當 ClickHouse 連線超時時，consumer 沒有正確回退 offset，導致訊息丟失。我寫了個 RetryableConsumer wrapper 來修復，重試間隔是指數退避，基礎間隔 200ms，最大重試 5 次。",
]

# ── 第二批對話: 某次線上排障過程 (8 輪) ──────────────────────────────────
# 嵌入大量過程性細節（具體命令、錯誤資訊、臨時埠），這些不太會被摘要保留

CHAT_BATCH_2 = [
    "緊急情況！線上推薦介面大面積超時，錯誤日誌裡出現了一條：failed to connect to reco-model-svc:8091: dial tcp 10.0.3.17:8091: i/o timeout。我先幫你記錄下排障過程。",
    "我先跑了 kubectl get pods -n reco-prod，發現 reco-model-svc-7b9f4d6c8-x2k9p 這個 pod 的 RESTARTS 是 47 次，狀態是 CrashLoopBackOff。kubectl logs 看到 OOM Killed，記憶體限制是 512Mi 但模型載入需要 800Mi。",
    "臨時解決方案：kubectl edit deployment reco-model-svc -n reco-prod，把 resources.limits.memory 從 512Mi 改成 1Gi，然後 kubectl rollout restart deployment reco-model-svc -n reco-prod。等了 3 分鐘 pod 恢復正常。",
    "但還有個隱患：我用 tcpdump -i eth0 port 8091 -w /tmp/reco-debug-20260315.pcap 抓了 5 分鐘的包，發現有個上游服務 gateway-proxy (IP 10.0.2.33) 的連線沒有正確關閉，導致連線洩漏。",
    "連線洩漏的根因：gateway-proxy 用了一個自定義的 HTTP client，pool_maxsize 設成了 200，但 idle_timeout 是 0（永不超時）。我在 gateway-proxy 的 config/http-pool.yaml 裡改成了 idle_timeout: 30s，pool_maxsize: 50。",
    "修完之後跑了個迴歸測試：curl -w '@curl-format.txt' -o /dev/null -s 'http://10.0.3.17:8091/predict?user_id=test_user_42&features=age,gender,region' 返回 time_total: 0.023s，比之前的 2.1s 快了 100 倍。",
    "事後我寫了個 incident report，編號是 INC-2026-0315-RECO-OOM，根因分類是 Resource Misconfiguration，影響時長 47 分鐘，影響使用者數約 12000。",
    "老王看完報告說，以後所有服務的 memory limit 至少設定為實際用量的 1.5 倍，並且要在 Grafana 上加一個 container_memory_working_set_bytes / container_spec_memory_limit_bytes > 0.8 的告警。",
]

# ── 第三批對話: 程式碼評審中的具體討論 (8 輪) ────────────────────────────
# 嵌入程式碼審查中的具體 review comment 和程式碼片段

CHAT_BATCH_3 = [
    "今天程式碼評審了我的推薦介面 PR，PR 編號是 #1847。老王給了 3 個重要 comment，我一個個跟你說。",
    "第一個 comment 在 internal/handler/recommend.go 的第 73 行：老王說我的錯誤處理不對，原來寫的是 if err != nil { return nil, err }，但應該包裝一下上下文：return nil, fmt.Errorf('recommend handler: fetch features for user %s: %w', userID, err)。",
    "第二個 comment 在 internal/cache/feature_cache.go 第 142 行：我用了 sync.Map 來快取使用者特徵，但老王建議改用分段鎖 map，因為 sync.Map 在寫多讀少的場景下效能不好。他推薦用 github.com/orcaman/concurrent-map/v2 這個庫。",
    "第三個 comment 是關於測試覆蓋率的：當前 recommend 包的覆蓋率只有 38%，老王要求至少到 70%。他特別指出 internal/handler/recommend_test.go 缺少對 context.Canceled 和 context.DeadlineExceeded 的邊界測試。",
    "我按老王的建議改了程式碼。feature_cache.go 的改動最大，從 sync.Map 遷移到 cmap.ConcurrentMap[string, *UserFeatures]。benchmark 跑下來：BenchmarkFeatureCacheGet-8 從 834 ns/op 降到了 412 ns/op，快了差不多一倍。",
    "測試也補了，加了 TestRecommendHandler_ContextCanceled 和 TestRecommendHandler_DeadlineExceeded 兩個用例。覆蓋率從 38% 提升到了 74%。go test -cover ./internal/handler/ 輸出：coverage: 74.2% of statements。",
    "PR 最終在週三下午 3:42 合併，commit hash 是 a3f7b2d。合併前跑了 CI，全部 green：lint 42s, test 1m18s, build 2m03s。",
    "對了，合併後我發現有個小問題：feature_cache.go 裡有一行 import 多餘了，_ 'net/http/pprof' 是除錯時加的忘了刪。我又開了個 hotfix PR #1852 修掉了。",
]

# ── 第四批對話: 架構設計討論 (8 輪) ─────────────────────────────────────

CHAT_BATCH_4 = [
    "最近團隊在討論要不要把推薦服務拆成微服務。我畫了一個架構圖，核心是 3 個服務：feature-store (負責使用者特徵儲存), model-server (負責模型推理), ranking-api (負責排序和過濾)。",
    "feature-store 的設計：用 Redis Cluster 做熱資料快取，冷資料存 ClickHouse。Redis 叢集是 3 主 3 從，每個節點 maxmemory 8GB，eviction 策略用 allkeys-lru。",
    "model-server 計劃用 gRPC 通訊，proto 檔案在 api/proto/model_service.proto。核心 RPC 是 Predict(PredictRequest) returns (PredictResponse)，PredictRequest 裡有 user_id (string), features (map<string, float>), model_version (string, 預設 'v3.2.1')。",
    "ranking-api 是面向外部的 REST 介面。我設計了一個兩層快取：L1 是本地 LRU cache (github.com/hashicorp/golang-lru/v2, 容量 10000), L2 是 Redis。快取 key 的格式是 reco:{user_id}:{model_version}:{timestamp_bucket}，timestamp_bucket 每 5 分鐘一個。",
    "團隊討論的爭議點：老王認為 feature-store 和 model-server 可以合併，因為兩者耦合度高。但我覺得拆開更好，因為 feature-store 的擴充需求（加新特徵）和 model-server 的擴充需求（換模型）是獨立的。",
    "最終架構評審的結論：先按 3 服務拆分，但 feature-store 和 model-server 共享一個 K8s namespace (reco-services)。服務間通訊走 Istio service mesh，mTLS 加密。",
    "部署策略：feature-store 3 副本（HPA min=3, max=10, CPU 閾值 70%），model-server 2 副本（HPA min=2, max=6, CPU 閾值 60%），ranking-api 4 副本（HPA min=4, max=20, CPU 閾值 65%）。",
    "對了，架構評審文件存在 Confluence 上，頁面 ID 是 ARCH-2026-RECO-MS，最後更新時間是 3 月 20 號。評審參與人：我、老王、測試小李、運維老趙。",
]

# ── 追問精確細節 (觸發 archive expand) ──────────────────────────────────
# 問的都是過程性細節：具體命令、IP 地址、錯誤資訊、commit hash 等
# 這些內容在摘要中通常會被壓縮掉

EXPAND_QUESTIONS = [
    {
        "question": "之前那次線上推薦介面故障，出問題的 pod 名字是什麼？kubectl logs 看到的錯誤是什麼？最終怎麼臨時修的？請給我精確的命令。",
        "expected_keywords": ["7b9f4d6c8-x2k9p", "OOM", "512Mi", "1Gi"],
        "target_archive": "archive_002",
        "description": "追問排障過程中的 pod 名和命令",
    },
    {
        "question": "我之前程式碼評審那個 PR 編號是多少？老王在哪個檔案的第幾行給了 comment？關於錯誤處理他具體建議怎麼改？",
        "expected_keywords": ["1847", "recommend.go", "73"],
        "target_archive": "archive_003",
        "description": "追問程式碼評審的精確 PR 和行號",
    },
    {
        "question": "feature_cache.go 遷移後的 benchmark 結果是多少 ns/op？測試覆蓋率從多少提升到了多少？PR 合併的 commit hash 是什麼？",
        "expected_keywords": ["412", "38%", "74", "a3f7b2d"],
        "target_archive": "archive_003",
        "description": "追問 benchmark 和覆蓋率精確資料",
    },
    {
        "question": "那次故障的 incident report 編號是什麼？影響了多少使用者？連線洩漏的根因是什麼配置導致的？",
        "expected_keywords": ["INC-2026-0315", "12000", "idle_timeout"],
        "target_archive": "archive_002",
        "description": "追問故障報告和根因",
    },
]

# ── 不需要展開的問題 ────────────────────────────────────────────────────

NO_EXPAND_QUESTIONS = [
    {
        "question": "我做什麼專案的？用什麼技術棧？請簡潔回答。",
        "expected_keywords": ["使用者畫像", "Go"],
        "description": "概要資訊，不需要展開歸檔",
    },
]


# ── Token 自動發現 ────────────────────────────────────────────────────────

_gateway_token: str = ""


def discover_gateway_token() -> str:
    import pathlib

    candidates = [
        pathlib.Path.cwd() / "config" / ".openclaw" / "openclaw.json",
        pathlib.Path.home() / ".openclaw" / "openclaw.json",
    ]
    state_dir = os.environ.get("OPENCLAW_STATE_DIR")
    if state_dir:
        candidates.insert(0, pathlib.Path(state_dir) / "openclaw.json")

    for p in candidates:
        try:
            cfg = json.loads(p.read_text(encoding="utf-8"))
            token = cfg.get("gateway", {}).get("auth", {}).get("token", "")
            if token:
                return token
        except Exception:
            continue
    return ""


def set_gateway_token(token: str):
    global _gateway_token
    _gateway_token = token


# ── Gateway / OpenViking API ─────────────────────────────────────────────


def send_message(gateway_url: str, message: str, user_id: str) -> dict:
    headers = {"Content-Type": "application/json"}
    if _gateway_token:
        headers["Authorization"] = f"Bearer {_gateway_token}"
    resp = requests.post(
        f"{gateway_url}/v1/responses",
        headers=headers,
        json={"model": "openclaw", "input": message, "user": user_id},
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json()


def extract_reply_text(data: dict) -> str:
    for item in data.get("output", []):
        if item.get("type") == "message" and item.get("role") == "assistant":
            for part in item.get("content", []):
                if part.get("type") in ("text", "output_text"):
                    return part.get("text", "")
    return "(無回覆)"


class OVInspector:
    def __init__(self, base_url: str, agent_id: str = AGENT_ID):
        self.base_url = base_url.rstrip("/")
        self.agent_id = agent_id

    def _headers(self) -> dict:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self.agent_id:
            h["X-OpenViking-Actor-Peer"] = self.agent_id
        return h

    def _get(self, path: str, timeout: int = 10):
        try:
            resp = requests.get(
                f"{self.base_url}{path}",
                headers=self._headers(),
                timeout=timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("result", data)
            return None
        except Exception as e:
            console.print(f"[dim]GET {path} failed: {e}[/dim]")
            return None

    def _post(self, path: str, body: dict | None = None, timeout: int = 30):
        try:
            resp = requests.post(
                f"{self.base_url}{path}",
                headers=self._headers(),
                json=body or {},
                timeout=timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("result", data)
            return None
        except Exception as e:
            console.print(f"[dim]POST {path} failed: {e}[/dim]")
            return None

    def health_check(self) -> bool:
        try:
            return requests.get(f"{self.base_url}/health", timeout=5).status_code == 200
        except Exception:
            return False

    def list_sessions(self) -> list:
        result = self._get("/api/v1/sessions")
        return result if isinstance(result, list) else []

    def get_session(self, session_id: str):
        return self._get(f"/api/v1/sessions/{session_id}")

    def get_session_context(self, session_id: str, token_budget: int = 128000):
        return self._get(
            f"/api/v1/sessions/{session_id}/context?token_budget={token_budget}",
        )

    def commit_session(self, session_id: str, wait: bool = True):
        result = self._post(f"/api/v1/sessions/{session_id}/commit", timeout=120)
        if not result:
            return None
        if wait and result.get("task_id"):
            task_id = result["task_id"]
            deadline = time.time() + 120
            while time.time() < deadline:
                time.sleep(0.5)
                task = self._get(f"/api/v1/tasks/{task_id}")
                if not task:
                    continue
                if task.get("status") == "completed":
                    result["status"] = "completed"
                    return result
                if task.get("status") == "failed":
                    result["status"] = "failed"
                    return result
        return result

    def find_latest_session(self) -> str | None:
        sessions = self.list_sessions()
        real = [
            s
            for s in sessions
            if isinstance(s, dict) and not s.get("session_id", "").startswith("memory-store-")
        ]
        if not real:
            return None
        best_id, best_time = None, ""
        for s in real:
            sid = s.get("session_id", "")
            if not sid:
                continue
            detail = self.get_session(sid)
            if not detail:
                continue
            updated = detail.get("updated_at", "")
            if updated > best_time:
                best_time = updated
                best_id = sid
        return best_id or (real[-1].get("session_id") if real else None)


# ── 渲染函式 ─────────────────────────────────────────────────────────────


def render_reply(text: str, title: str = "回覆"):
    lines = text.split("\n")
    if len(lines) > 25:
        text = "\n".join(lines[:25]) + f"\n\n... (共 {len(lines)} 行，已截斷)"
    console.print(Panel(Markdown(text), title=f"[green]{title}[/green]", border_style="green"))


def render_json(data: Any, title: str = "JSON"):
    console.print(
        Panel(json.dumps(data, indent=2, ensure_ascii=False, default=str)[:2000], title=title),
    )


# ── Phase 1: 第一批對話 ──────────────────────────────────────────────────


def run_phase_chat(
    gateway_url: str,
    user_id: str,
    messages: list[str],
    batch_label: str,
    delay: float,
    verbose: bool,
) -> tuple[int, int]:
    console.print()
    console.rule(
        f"[bold]{batch_label}: {DISPLAY_NAME} 對話 ({len(messages)} 輪)[/bold]",
    )
    console.print(f"[yellow]使用者ID:[/yellow] {user_id}")
    console.print()

    total = len(messages)
    ok = fail = 0

    for i, msg in enumerate(messages, 1):
        console.rule(f"[dim]Turn {i}/{total}[/dim]", style="dim")
        preview = msg[:150] + ("..." if len(msg) > 150 else "")
        console.print(
            Panel(
                preview,
                title=f"[bold cyan]{DISPLAY_NAME} [{i}/{total}][/bold cyan]",
                border_style="cyan",
            ),
        )
        try:
            data = send_message(gateway_url, msg, user_id)
            reply = extract_reply_text(data)
            render_reply(reply[:400] + ("..." if len(reply) > 400 else ""))
            ok += 1
        except Exception as e:
            console.print(f"[red][ERROR][/red] {e}")
            fail += 1

        if i < total:
            time.sleep(delay)

    console.print()
    console.print(f"[yellow]對話完成:[/yellow] {ok} 成功, {fail} 失敗")

    wait = max(delay * 2, 8)
    console.print(f"[yellow]等待 {wait:.0f}s 讓 afterTurn + auto-commit 處理...[/yellow]")
    time.sleep(wait)

    return ok, fail


# ── Phase 3: 驗證 Archive Index 存在 ────────────────────────────────────


def run_phase_verify_index(openviking_url: str, verbose: bool) -> str:
    console.print()
    console.rule("[bold]Phase 3: 驗證 Archive Index 存在[/bold]")
    console.print()

    inspector = OVInspector(openviking_url)

    healthy = inspector.health_check()
    check("OpenViking 服務可達", healthy)
    if not healthy:
        return ""

    session_id = inspector.find_latest_session()
    check("OV session 存在", session_id is not None, f"session_id={session_id}")
    if not session_id:
        return ""

    session_info = inspector.get_session(session_id)
    if session_info:
        commit_count = session_info.get("commit_count", 0)
        check(
            "commit_count >= 3 (至少 3 個 archive)",
            commit_count >= 3,
            f"commit_count={commit_count}",
        )

        memories = session_info.get("memories_extracted", {})
        total_mem = sum(memories.values()) if isinstance(memories, dict) else 0
        check("累計提取記憶 > 0", total_mem > 0, f"total={total_mem}")

        if verbose:
            render_json(session_info, "Session 詳情")

    ctx = inspector.get_session_context(session_id)
    if ctx:
        overview = ctx.get("latest_archive_overview", "")
        messages = ctx.get("messages", [])
        stats = ctx.get("stats", {})

        check(
            "context 返回資料",
            bool(overview) or len(messages) > 0,
            f"overview_len={len(overview)}, messages={len(messages)}",
        )

        total_archives = stats.get("totalArchives", 0)
        check(
            "歸檔數 >= 3",
            total_archives >= 3,
            f"totalArchives={total_archives}",
        )

        if verbose and overview:
            console.print(f"  [dim]overview 前 300 字: {overview[:300]}...[/dim]")
    else:
        check("context 可呼叫", False)

    return session_id or ""


# ── Phase 4: 追問精確細節 — 觸發 ov_archive_expand ──────────────────────


def run_phase_expand(
    gateway_url: str,
    user_id: str,
    delay: float,
    verbose: bool,
) -> list:
    console.print()
    console.rule(
        f"[bold]Phase 4: 追問精確細節 — 觸發 ov_archive_expand ({len(EXPAND_QUESTIONS)} 輪)[/bold]",
    )
    console.print()
    console.print("[dim]驗證點:[/dim]")
    console.print("[dim]- 追問歸檔中的精確引數值[/dim]")
    console.print("[dim]- LLM 應通過 ov_archive_expand 展開歸檔[/dim]")
    console.print("[dim]- 回覆包含原始對話中的精確資料（非泛化摘要）[/dim]")
    console.print()

    results = []
    total = len(EXPAND_QUESTIONS)

    for i, item in enumerate(EXPAND_QUESTIONS, 1):
        q = item["question"]
        keywords = item["expected_keywords"]
        desc = item["description"]

        console.rule(f"[dim]Expand Q{i}/{total}: {desc}[/dim]", style="dim")
        console.print(
            Panel(
                f"{q}\n\n[dim]期望關鍵詞: {', '.join(keywords)}[/dim]\n"
                f"[dim]目標歸檔: {item['target_archive']}[/dim]",
                title=f"[bold cyan]Expand Q{i}[/bold cyan]",
                border_style="cyan",
            ),
        )

        try:
            data = send_message(gateway_url, q, user_id)
            reply = extract_reply_text(data)
            render_reply(reply)

            reply_lower = reply.lower()
            hits = [kw for kw in keywords if kw.lower() in reply_lower]
            hit_rate = len(hits) / len(keywords) if keywords else 0
            success = hit_rate >= 0.5

            check(
                f"Expand Q{i} ({desc}): 關鍵詞命中率 >= 50%",
                success,
                f"命中={hits}, 未命中={[k for k in keywords if k not in hits]}, rate={hit_rate:.0%}",
            )

            if verbose:
                console.print(
                    f"  [dim]完整輸出: {json.dumps(data.get('output', []), ensure_ascii=False)[:500]}[/dim]"
                )

            results.append(
                {
                    "question": q,
                    "hits": hits,
                    "hit_rate": hit_rate,
                    "success": success,
                    "description": desc,
                }
            )
        except Exception as e:
            check(f"Expand Q{i}: 傳送成功", False, str(e))
            results.append(
                {
                    "question": q,
                    "hits": [],
                    "hit_rate": 0,
                    "success": False,
                    "description": desc,
                }
            )

        if i < total:
            time.sleep(delay)

    return results


# ── Phase 5: 不需要展開的問題 ───────────────────────────────────────────


def run_phase_no_expand(
    gateway_url: str,
    user_id: str,
    delay: float,
    verbose: bool,
) -> list:
    console.print()
    console.rule(
        f"[bold]Phase 5: 不需要展開的問題 ({len(NO_EXPAND_QUESTIONS)} 輪)[/bold]",
    )
    console.print("[dim]驗證: 概要級問題從摘要即可回答，無需展開[/dim]")
    console.print()

    results = []
    total = len(NO_EXPAND_QUESTIONS)

    for i, item in enumerate(NO_EXPAND_QUESTIONS, 1):
        q = item["question"]
        keywords = item["expected_keywords"]

        console.rule(f"[dim]NoExpand Q{i}/{total}[/dim]", style="dim")
        console.print(
            Panel(
                f"{q}\n\n[dim]期望關鍵詞: {', '.join(keywords)}[/dim]",
                title=f"[bold cyan]NoExpand Q{i}[/bold cyan]",
                border_style="cyan",
            ),
        )

        try:
            data = send_message(gateway_url, q, user_id)
            reply = extract_reply_text(data)
            render_reply(reply)

            reply_lower = reply.lower()
            hits = [kw for kw in keywords if kw.lower() in reply_lower]
            hit_rate = len(hits) / len(keywords) if keywords else 0

            check(
                f"NoExpand Q{i}: 概要回答正確 (命中率 >= 50%)",
                hit_rate >= 0.5,
                f"命中={hits}, rate={hit_rate:.0%}",
            )
            results.append(
                {"question": q, "hits": hits, "hit_rate": hit_rate, "success": hit_rate >= 0.5}
            )
        except Exception as e:
            check(f"NoExpand Q{i}: 傳送成功", False, str(e))
            results.append({"question": q, "hits": [], "hit_rate": 0, "success": False})

        if i < total:
            time.sleep(delay)

    return results


# ── 完整測試 ──────────────────────────────────────────────────────────────


def run_full_test(
    gateway_url: str,
    openviking_url: str,
    user_id: str,
    delay: float,
    verbose: bool,
    gateway_restart_cmd: str = "",
):
    console.print()
    console.print(
        Panel.fit(
            f"[bold]ov_archive_expand 歸檔展開測試 — {DISPLAY_NAME}[/bold]\n\n"
            f"Gateway: {gateway_url}\n"
            f"OpenViking: {openviking_url}\n"
            f"User ID: {user_id}\n"
            f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            title="測試資訊",
        ),
    )

    # Phase 1: 第一批對話 — 專案技術細節
    ok1, fail1 = run_phase_chat(
        gateway_url,
        user_id,
        CHAT_BATCH_1,
        "Phase 1: 第一段對話 — 專案技術細節",
        delay,
        verbose,
    )
    check(f"Phase 1: {ok1}/{len(CHAT_BATCH_1)} 輪成功", fail1 == 0, f"ok={ok1}, fail={fail1}")

    # Phase 2a: 第二批對話 — 排障過程
    ok2, fail2 = run_phase_chat(
        gateway_url,
        user_id,
        CHAT_BATCH_2,
        "Phase 2a: 第二段對話 — 線上排障過程",
        delay,
        verbose,
    )
    check(f"Phase 2a: {ok2}/{len(CHAT_BATCH_2)} 輪成功", fail2 == 0, f"ok={ok2}, fail={fail2}")

    # Phase 2b: 第三批對話 — 程式碼評審討論
    ok3, fail3 = run_phase_chat(
        gateway_url,
        user_id,
        CHAT_BATCH_3,
        "Phase 2b: 第三段對話 — 程式碼評審討論",
        delay,
        verbose,
    )
    check(f"Phase 2b: {ok3}/{len(CHAT_BATCH_3)} 輪成功", fail3 == 0, f"ok={ok3}, fail={fail3}")

    # Phase 2c: 第四批對話 — 架構設計討論
    ok4, fail4 = run_phase_chat(
        gateway_url,
        user_id,
        CHAT_BATCH_4,
        "Phase 2c: 第四段對話 — 架構設計討論",
        delay,
        verbose,
    )
    check(f"Phase 2c: {ok4}/{len(CHAT_BATCH_4)} 輪成功", fail4 == 0, f"ok={ok4}, fail={fail4}")

    # Phase 3: 驗證 Archive Index
    run_phase_verify_index(openviking_url, verbose)

    # Gateway 重啟 — 清除工作記憶，迫使 LLM 從歸檔獲取資訊
    if gateway_restart_cmd:
        console.print()
        console.rule("[bold yellow]重啟 Gateway — 清除工作記憶[/bold yellow]")
        console.print("[yellow]重啟前等待 10s 讓後臺 commit 完成...[/yellow]")
        time.sleep(10)
        console.print(f"[yellow]執行: {gateway_restart_cmd}[/yellow]")
        import subprocess

        try:
            result = subprocess.run(
                gateway_restart_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            console.print(f"[yellow]Gateway 重啟完成: {result.stdout.strip()}[/yellow]")
        except subprocess.TimeoutExpired:
            console.print("[yellow]Gateway 重啟命令超時，檢查健康狀態...[/yellow]")
        # 等待 Gateway 恢復
        for _attempt in range(15):
            time.sleep(2)
            try:
                r = requests.get(f"{gateway_url}/health", timeout=3)
                if r.status_code == 200:
                    console.print("[green]Gateway 健康檢查通過[/green]")
                    break
            except Exception:
                pass
        else:
            console.print("[red]Gateway 重啟後健康檢查未通過[/red]")

    # Phase 4: 追問精確細節 — 觸發 expand
    expand_results = run_phase_expand(gateway_url, user_id, delay, verbose)

    # Phase 5: 不需要展開的問題
    no_expand_results = run_phase_no_expand(gateway_url, user_id, delay, verbose)

    # ── 彙總報告 ──────────────────────────────────────────────────────────

    console.print()
    console.rule("[bold]測試報告[/bold]")

    passed = sum(1 for a in assertions if a["ok"])
    failed = sum(1 for a in assertions if not a["ok"])
    total = len(assertions)

    table = Table(title=f"斷言結果: {passed}/{total} 通過")
    table.add_column("#", style="bold", width=4)
    table.add_column("狀態", width=6)
    table.add_column("斷言", max_width=55)
    table.add_column("詳情", style="dim", max_width=55)

    for i, a in enumerate(assertions, 1):
        status = "[green]PASS[/green]" if a["ok"] else "[red]FAIL[/red]"
        table.add_row(str(i), status, a["label"][:55], (a.get("detail") or "")[:55])

    console.print(table)

    tree = Tree(f"[bold]通過: {passed}/{total}, 失敗: {failed}[/bold]")
    tree.add(f"Phase 1: 專案技術細節 — {ok1}/{len(CHAT_BATCH_1)}")
    tree.add(f"Phase 2a: 線上排障 — {ok2}/{len(CHAT_BATCH_2)}")
    tree.add(f"Phase 2b: 程式碼評審 — {ok3}/{len(CHAT_BATCH_3)}")
    tree.add(f"Phase 2c: 架構設計 — {ok4}/{len(CHAT_BATCH_4)}")
    tree.add("Phase 3: Archive Index 驗證")

    expand_ok = sum(1 for r in expand_results if r["success"])
    tree.add(f"Phase 4: 歸檔展開 — {expand_ok}/{len(expand_results)} 問題回答正確")

    no_expand_ok = sum(1 for r in no_expand_results if r["success"])
    tree.add(f"Phase 5: 無需展開 — {no_expand_ok}/{len(no_expand_results)} 問題回答正確")

    fail_list = [a for a in assertions if not a["ok"]]
    if fail_list:
        fail_branch = tree.add(f"[red]失敗斷言 ({len(fail_list)})[/red]")
        for a in fail_list:
            fail_branch.add(f"[red]FAIL[/red] {a['label']}")

    console.print(tree)

    if failed == 0:
        console.print("\n[green bold]全部通過! ov_archive_expand 歸檔展開驗證成功。[/green bold]")
    else:
        console.print(f"\n[red bold]有 {failed} 個斷言失敗。[/red bold]")


# ── 日誌掃描: 驗證 ov_archive_expand 工具呼叫 ────────────────────────────


def scan_expand_log(log_path: str):
    """掃描 Gateway 日誌，提取 ov_archive_expand 呼叫記錄。"""
    import pathlib

    p = pathlib.Path(log_path)
    if not p.exists():
        console.print(f"\n[yellow]日誌檔案不存在: {log_path}[/yellow]")
        console.print("[dim]跳過工具呼叫日誌驗證[/dim]")
        return

    console.print()
    console.rule("[bold]ov_archive_expand 工具呼叫日誌驗證[/bold]")
    console.print(f"[dim]日誌檔案: {log_path}[/dim]")
    console.print()

    invoked_lines = []
    expanded_lines = []

    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            for line in f:
                if "ov_archive_expand invoked" in line:
                    invoked_lines.append(line.strip())
                elif "ov_archive_expand expanded" in line:
                    expanded_lines.append(line.strip())
    except Exception as e:
        console.print(f"[red]讀取日誌失敗: {e}[/red]")
        return

    if not invoked_lines and not expanded_lines:
        console.print("[red]未找到 ov_archive_expand 呼叫記錄！[/red]")
        console.print(
            "[dim]可能原因: LLM 從工作記憶（而非歸檔展開）獲取了資訊。"
            "嘗試使用 --gateway-restart-cmd 在 Phase 4 前重啟 Gateway。[/dim]",
        )
        return

    log_table = Table(title="ov_archive_expand 呼叫記錄", show_lines=True)
    log_table.add_column("#", style="bold", width=4)
    log_table.add_column("操作", width=10)
    log_table.add_column("歸檔 ID", style="cyan", width=14)
    log_table.add_column("詳情", style="dim")

    import re

    row_idx = 0
    for line in invoked_lines:
        row_idx += 1
        m = re.search(r"archiveId=(\w+)", line)
        archive_id = m.group(1) if m else "?"
        log_table.add_row(str(row_idx), "invoked", archive_id, "呼叫展開")

    for line in expanded_lines:
        row_idx += 1
        m_id = re.search(r"expanded (\w+)", line)
        m_msg = re.search(r"messages=(\d+)", line)
        m_chars = re.search(r"chars=(\d+)", line)
        archive_id = m_id.group(1) if m_id else "?"
        msgs = m_msg.group(1) if m_msg else "?"
        chars = m_chars.group(1) if m_chars else "?"
        log_table.add_row(
            str(row_idx),
            "expanded",
            archive_id,
            f"恢復 {msgs} 條訊息, {chars} 字元",
        )

    console.print(log_table)

    archive_counts: dict[str, int] = {}
    for line in invoked_lines:
        m = re.search(r"archiveId=(\w+)", line)
        if m:
            aid = m.group(1)
            archive_counts[aid] = archive_counts.get(aid, 0) + 1

    console.print()
    console.print(
        f"[green]共 {len(invoked_lines)} 次 invoked, {len(expanded_lines)} 次 expanded[/green]"
    )
    for aid, cnt in sorted(archive_counts.items()):
        console.print(f"  {aid}: {cnt} 次呼叫")

    check(
        "日誌中存在 ov_archive_expand 呼叫記錄",
        len(invoked_lines) > 0,
        f"invoked={len(invoked_lines)}, expanded={len(expanded_lines)}",
    )


# ── 入口 ──────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description=f"ov_archive_expand 歸檔展開測試 — {DISPLAY_NAME}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--gateway", default=DEFAULT_GATEWAY, help=f"Gateway 地址 (預設: {DEFAULT_GATEWAY})"
    )
    parser.add_argument(
        "--openviking",
        default=DEFAULT_OPENVIKING,
        help=f"OpenViking 地址 (預設: {DEFAULT_OPENVIKING})",
    )
    parser.add_argument("--user-id", default=USER_ID, help="測試使用者 ID (預設: 隨機)")
    parser.add_argument(
        "--phase",
        choices=["all", "chat1", "chat2", "verify-index", "expand", "no-expand"],
        default="all",
        help="執行階段 (預設: all)",
    )
    parser.add_argument("--delay", type=float, default=3.0, help="輪次間等待秒數 (預設: 3)")
    parser.add_argument("--token", default="", help="Gateway auth token (預設: 自動發現)")
    parser.add_argument("--agent-id", default=AGENT_ID, help=f"Agent ID (預設: {AGENT_ID})")
    parser.add_argument(
        "--gateway-restart-cmd",
        default="",
        help="Gateway 重啟命令 (在 Phase 4 前執行，清除工作記憶以迫使 archive expand)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="詳細輸出")
    parser.add_argument(
        "--log-path",
        default="",
        help="Gateway 日誌路徑 (如 config/.openclaw/logs/openclaw.log)，測試後自動掃描 ov_archive_expand 呼叫",
    )
    args = parser.parse_args()

    gateway_url = args.gateway.rstrip("/")
    openviking_url = args.openviking.rstrip("/")
    user_id = args.user_id

    token = args.token or discover_gateway_token()
    set_gateway_token(token)

    console.print(f"[bold]ov_archive_expand 歸檔展開測試 — {DISPLAY_NAME}[/bold]")
    console.print(f"[yellow]Gateway:[/yellow] {gateway_url}")
    console.print(f"[yellow]OpenViking:[/yellow] {openviking_url}")
    console.print(f"[yellow]User ID:[/yellow] {user_id}")

    if args.phase == "all":
        run_full_test(
            gateway_url,
            openviking_url,
            user_id,
            args.delay,
            args.verbose,
            gateway_restart_cmd=args.gateway_restart_cmd,
        )
    elif args.phase == "chat1":
        run_phase_chat(gateway_url, user_id, CHAT_BATCH_1, "Phase 1", args.delay, args.verbose)
    elif args.phase == "chat2":
        run_phase_chat(gateway_url, user_id, CHAT_BATCH_2, "Phase 2", args.delay, args.verbose)
    elif args.phase == "verify-index":
        run_phase_verify_index(openviking_url, args.verbose)
    elif args.phase == "expand":
        run_phase_expand(gateway_url, user_id, args.delay, args.verbose)
    elif args.phase == "no-expand":
        run_phase_no_expand(gateway_url, user_id, args.delay, args.verbose)

    if args.log_path:
        scan_expand_log(args.log_path)

    if assertions:
        passed = sum(1 for a in assertions if a["ok"])
        total_a = len(assertions)
        console.print(f"\n[yellow]斷言統計: {passed}/{total_a} 通過[/yellow]")

    console.print("\n[yellow]測試結束。[/yellow]")


if __name__ == "__main__":
    main()
