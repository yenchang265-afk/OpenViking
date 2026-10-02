# Trajectory / Experience 經驗學習框架重構
>
> 目標：把真實或離線環境中的 agent rollout 轉換為 trajectory，再從 trajectory 估計 experience 更新訊號，最終通過可審查、可合併、可併發安全的 policy update 機制更新 `experiences` 目錄。

## 1. 總體定位

當前框架把 `experiences` 目錄視為一個可最佳化的 **Experience Policy Set**：

```text
viking://user/<user>/memories/experiences/
```

目錄中的每個 experience 檔案是一個 `Experience`，整個目錄共同構成 agent 的經驗策略。訓練框架不直接繫結某個 agent loop；它只約束以下抽象鏈路：

```text
CaseLoader
  -> RolloutExecutor
  -> PolicyTrainer
       -> RolloutAnalyzer
       -> GradientEstimator
       -> PolicyOptimizer
       -> PolicyUpdater
```

其中 `PolicyTrainer` 是訓練入口。預設本地實現會在程序內執行 `analyze -> estimate -> plan -> apply`；遠端實現可以把 rollout 通過 `session.commit` 提交給 Business Data Platform 服務端，由服務端完成分析和訓練。

### 1.1 訓練執行細節圖

<img src="https://gist.githubusercontent.com/chenjw/c2de3083d0e1dac3a192c74f98c020c7/raw/502e01c5e207ce8b2b4076a6cd84b8fe9dc06543/train-execution-details.svg" alt="Business Data Platform session.train 訓練執行細節" width="100%">

這張圖強調三個實現邊界：

- **並行邊界**：case rollout、rollout analysis、gradient estimation 可以並行。
- **序列邊界**：`ExperienceSet.lock()` 內的 `reload -> PolicyOptimizer.plan -> PolicyUpdater.apply` 必須序列。
- **儲存邊界**：trajectory 寫入發生在 `RolloutAnalyzer`；experience 讀取/合併/寫入發生在 optimizer/updater；session archive 和 `memory_diff.json` 只出現在 `session.commit` 路徑。
- **LLM 邊界**：紅色特殊框表示該模組會呼叫 LLM / `ExtractLoop`，包括 trajectory 抽取、experience gradient 估計和 patch merge。


## 2. 程式碼結構

當前模組結構：

```text
openviking/session/train/
  context.py          # PipelineContext / ExecutionContext
  domain.py           # domain dataclass
  engine.py           # PolicyTrainingEngine：共享 analyze/estimate/plan/apply 核心
  gradients.py        # PatchSemanticGradient
  interfaces.py       # Protocol 接口
  pipeline.py         # OfflinePolicyOptimizationPipeline

  components/         # 可替換元件實現
    case_loader.py
    gradient_estimator.py
    memory_store.py
    policy_optimizer.py
    policy_trainer.py
    policy_updater.py
    remote.py
    rollout_executor.py
    session_commit.py
    snapshotter.py
    trajectory_analyzer.py
```

設計邊界：

- 根目錄保留框架核心、domain、介面和編排。
- `components/` 放所有具體實現。
- `openviking.session.train` 頂層繼續匯出常用類，便於外部使用。

## 3. 核心 Domain Model

### 3.1 Experience / ExperienceSet

`Experience` 對應 experiences 目錄下的一個 experience 檔案。

```python
@dataclass(slots=True)
class Experience:
    name: str
    uri: str
    version: int
    status: PolicyStatus
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    links: list[dict[str, Any]] = field(default_factory=list)
    backlinks: list[dict[str, Any]] = field(default_factory=list)
```

`ExperienceSet` 是某個 experiences 根目錄的快照：

```python
@dataclass(slots=True)
class ExperienceSet:
    root_uri: str
    policies: list[Experience]
    metadata: dict[str, Any] = field(default_factory=dict)
    viking_fs: Any | None = field(default=None, repr=False, compare=False)
    request_context: Any | None = field(default=None, repr=False, compare=False)
```

當前實現中，`ExperienceSet` 還負責提供併發安全能力：

```python
async with policy_set.lock():
    latest_policy_set = await policy_set.reload()
```

約定：

- `root_uri` 是 experiences 目錄 URI。
- `links/backlinks` 對應 memory file 中的 `MEMORY_FIELDS.links/backlinks`，用於在 train 域快照內保留 v2 link 協議資料。
- `policies` 是當前目錄下所有 experience 檔案解析後的快照。
- `viking_fs` / `request_context` 是執行時依賴，用於 `lock()` 和 `reload()`，不參與 equality/repr。
- `PolicyTrainingEngine.plan_and_apply(...)` 會先加 policy tree lock，再 reload 最新 policy set，然後 plan/apply。

### 3.2 Trajectory

`Trajectory` 是從 rollout 中抽取並持久化的可訓練軌跡樣本，對應 trajectories 目錄下的 memory 檔案。

```python
@dataclass(slots=True)
class Trajectory:
    name: str
    uri: str
    content: str
    outcome: TrajectoryOutcome | str
    retrieval_anchor: str
    metadata: dict[str, Any] = field(default_factory=dict)
```

約定：

- `Rollout` 是原始執行記錄。
- `Trajectory` 是從 rollout messages 中抽取出的訓練樣本。
- trajectory 檔案由 `TrajectoryRolloutAnalyzer` 通過 `ExtractLoop + MemoryUpdater` 寫入 `memories/trajectories`。

### 3.3 Case / Rubric

`Case` 是可執行、可復現、可評估的訓練/評測樣例。

```python
@dataclass(slots=True)
class Case:
    name: str
    task_signature: str
    input: dict[str, Any]
    rubric: Rubric
    metadata: dict[str, Any] = field(default_factory=dict)
```

`Rubric` 定義“什麼叫做好”和“怎麼檢查”。當前不再保留獨立 `Outcome` 概念。

```python
@dataclass(slots=True)
class Rubric:
    name: str
    description: str
    criteria: list[RubricCriterion]
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class RubricCriterion:
    name: str
    description: str
    required: bool
    weight: float
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 3.4 Rollout

`Rollout` 是某個 policy snapshot 在某個 case 上執行後的記錄。

```python
@dataclass(slots=True)
class Rollout:
    case: Case
    messages: list[Message]
    policy_snapshot_id: str
    evaluation: RubricEvaluation | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

當前關鍵變化：`Rollout.evaluation` 是一等可選欄位。

- 如果環境本身能給 reward / evaluation，`RolloutExecutor` 應直接填入 `rollout.evaluation`。
- 訓練時 `TrajectoryRolloutAnalyzer` 優先沿用 `rollout.evaluation`；沒有時才通過注入的 `RolloutEvaluator` 評估；再沒有時用“是否抽取到 trajectory”作為 fallback evaluation。
- `pipeline.eval(...)` 不再呼叫 `RolloutAnalyzer`，只依賴 `RolloutExecutor` 返回的 `rollout.evaluation`；如果 eval rollout 缺 evaluation，會直接報錯。

### 3.5 RubricEvaluation

```python
@dataclass(slots=True)
class RubricEvaluation:
    passed: bool
    score: float
    criterion_results: list[CriterionResult]
    feedback: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class CriterionResult:
    criterion_name: str
    passed: bool
    score: float
    feedback: list[str]
    evidence: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)
```

在 tau2 集成中：

- `passed = reward >= 1.0`
- `score = reward`
- report 展示以 `accuracy = passed_count / case_count` 為主，`average_reward` 為輔助指標。

## 4. SemanticGradient

`SemanticGradient` 是針對一個目標 experience 的語義更新訊號。當前介面以 `MemoryFile` before/after 表達，而不是文本 patch 物件。

```python
class SemanticGradient(Protocol):
    @property
    def before_file(self) -> MemoryFile | None: ...

    @property
    def after_file(self) -> MemoryFile: ...

    @property
    def target_experience_name(self) -> str: ...
    @property
    def target_experience_uri(self) -> str | None: ...
    @property
    def base_version(self) -> int | None: ...
    @property
    def rationale(self) -> str: ...
    @property
    def links(self) -> list[StoredLink]: ...
    @property
    def confidence(self) -> float: ...
    @property
    def metadata(self) -> dict[str, Any]: ...
```

當前具體實現：

```python
@dataclass(slots=True)
class PatchSemanticGradient:
    before_file: MemoryFile | None
    after_file: MemoryFile
    base_version: int | None
    rationale: str
    links: list[StoredLink]
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)
```

約定：

- `before_file is None` 表示建議新建。
- `after_file` 是建議的目標 memory file 狀態。
- `links` 承載 exp→traj 的 provenance，沿用 v2 `MEMORY_FIELDS.links/backlinks` 協議；來源軌跡關係使用 `StoredLink(from_uri=exp_uri, to_uri=traj_uri, link_type="derived_from", weight=1.0)`，不再引入單獨的軌跡 URI 列表欄位。
- patch 文本不是 gradient 自身欄位，而是由 `PatchMergeContextProvider` 在 merge 階段把 before/after memory file 渲染為欄位級 unified diff。

## 5. PolicyUpdatePlan / PolicyUpdater

`PolicyOptimizer.plan(...)` 輸出 `PolicyUpdatePlan`，`PolicyUpdater.apply(...)` 負責真正寫檔案。

```python
PolicyPlanItemKind = Literal["upsert_experience", "delete_experience"]

@dataclass(slots=True)
class PolicyPlanItem:
    kind: PolicyPlanItemKind
    target_experience_name: str
    target_experience_uri: str | None
    before_content: str | None
    after_content: str | None
    base_version: int | None = None
    confidence: float | None = None
    links: list[StoredLink] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class PolicyUpdatePlan:
    items: list[PolicyPlanItem] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class PolicyApplyResult:
    updated_policy_set: ExperienceSet
    written_uris: list[str] = field(default_factory=list)
    deleted_uris: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
```

當前 `MemoryFilePolicyUpdater` 支援：

- `upsert_experience`
- `delete_experience`
- 基於 `before_content` 的輕量 base-content guard，避免覆蓋已發散內容。

## 6. 介面定義

### 6.1 CaseLoader

```python
class CaseLoader(Protocol):
    async def batches(self, context: Any) -> AsyncIterator[list[Case]]: ...
```

實現：

- `ListCaseLoader`
- `RemoteCaseLoader`：通過 HTTP 服務拉取 cases。

### 6.2 RolloutExecutor

```python
class RolloutExecutor(Protocol):
    async def execute(
        self,
        cases: list[Case],
        policy_set: ExperienceSet,
        context: ExecutionContext,
    ) -> list[Rollout]: ...
```

實現：

- `SingleTurnLLMRolloutExecutor`
- `RemoteRolloutExecutor`
- `Tau2RolloutExecutor`（benchmark/tau2 內部實現，通過 tau2 service 暴露給訓練流程）

### 6.3 RolloutEvaluator

```python
class RolloutEvaluator(Protocol):
    async def evaluate(self, rollout: Rollout, context: Any) -> RubricEvaluation: ...
```

用途：環境不能直接提供 `rollout.evaluation` 時，`RolloutAnalyzer` 可注入 evaluator 進行評估。

### 6.4 RolloutAnalyzer

```python
class RolloutAnalyzer(Protocol):
    async def analyze(self, rollout: Rollout, context: Any) -> RolloutAnalysis: ...
```

當前實現：`TrajectoryRolloutAnalyzer`。

職責：

1. 確定 rollout evaluation：
   - 優先使用 `rollout.evaluation`
   - 否則使用注入的 `RolloutEvaluator`
   - 否則基於是否抽取到 trajectory 生成預設 evaluation
2. 將 evaluation feedback 追加到 trajectory extraction messages。
3. 通過 `AgentTrajectoryContextProvider + ExtractLoop` 只抽取 `trajectories` memory type。
4. 通過 `MemoryUpdater.apply_operations(...)` 寫入 trajectory memory。
5. 讀取寫入的 trajectory 檔案並返回 `RolloutAnalysis`。

### 6.5 GradientEstimator

```python
class GradientEstimator(Protocol):
    async def estimate(
        self,
        analysis: RolloutAnalysis,
        experience_set: ExperienceSet,
        context: Any,
    ) -> list[SemanticGradient]: ...
```

當前實現：`ExperienceGradientEstimator`。

它複用：

- `AgentExperienceContextProvider`
- `ExtractLoop`
- `MemoryIsolationHandler(allowed_memory_types={"experiences"})`

但不呼叫 `MemoryUpdater.apply_operations(...)`。它把 ExtractLoop 產生的 upsert operations 轉成 `PatchSemanticGradient`。

### 6.6 PolicyOptimizer

```python
class PolicyOptimizer(Protocol):
    async def plan(
        self,
        gradients: list[SemanticGradient],
        policy_set: ExperienceSet,
        context: Any,
    ) -> PolicyUpdatePlan: ...
```

當前實現：`PatchMergePolicyOptimizer`。

它不按 target 分組限制輸出，而是把一批 gradients 一次性交給 `PatchMergeContextProvider + ExtractLoop` 進行全域 merge。LLM 可以：

- 合併多個 patch 到一個 experience。
- 把一個臃腫 patch 拆成多個 experience。
- 合併相似新檔案。
- 主動輸出刪除操作。

### 6.7 PolicyUpdater

```python
class PolicyUpdater(Protocol):
    async def apply(
        self,
        plan: PolicyUpdatePlan,
        policy_set: ExperienceSet,
        context: Any,
    ) -> PolicyApplyResult: ...
```

實現：

- `DryRunPolicyUpdater`
- `MemoryFilePolicyUpdater`

### 6.8 PolicyTrainer

```python
class PolicyTrainer(Protocol):
    async def train_rollouts(
        self,
        rollouts: list[Rollout],
        policy_set: ExperienceSet,
        context: Any,
        analyses: list[RolloutAnalysis] | None = None,
    ) -> RolloutTrainingResult: ...
```

實現：

- `BatchPolicyTrainer`：顯式 batch，本地執行 analyze/estimate/plan/apply。
- `StreamingPolicyTrainer`：即時 rollout 輸入，先 analyze/estimate，再按梯度數量和時間視窗攢批，批次 plan/apply。
- `SessionCommitPolicyTrainer`：把 rollout 寫入遠端 Business Data Platform session，通過 `session.commit` 讓服務端完成訓練。

### 6.9 PolicyOptimizationPipeline

```python
class PolicyOptimizationPipeline(Protocol):
    async def train(...) -> PipelineResult: ...
    async def eval(...) -> PipelineEvaluationResult: ...
    async def train_from_rollouts(...) -> RolloutTrainingResult: ...
```

當前實現：`OfflinePolicyOptimizationPipeline`。

## 7. PipelineContext / ExecutionContext

```python
@dataclass(slots=True)
class PipelineContext:
    case_load_context: Any = None
    snapshot_context: Any = None
    analysis_context: Any = None
    gradient_context: Any = None
    optimization_context: Any = None
    apply_context: Any = None
    execution_metadata: dict[str, Any] = field(default_factory=dict)
    max_epochs: int = 1

@dataclass(slots=True)
class ExecutionContext:
    policy_snapshot_id: str
    metadata: dict[str, Any] = field(default_factory=dict)
```

`max_epochs` 是訓練迭代次數。之前文件中的 `max_iterations` 已改為 epoch 概念。

## 8. 訓練流程

### 8.1 OfflinePolicyOptimizationPipeline.train

```text
for epoch in range(ctx.max_epochs):
  for cases in case_loader.batches(...):
    snapshot_id = snapshotter.snapshot(policy_set)
    rollouts = rollout_executor.execute(cases, policy_set, ExecutionContext(snapshot_id))
    training_result = policy_trainer.train_rollouts(rollouts, policy_set, ctx)
    policy_set = training_result.apply_result.updated_policy_set
```

預設 `policy_trainer` 是 `BatchPolicyTrainer`，因此本地訓練鏈路為：

```text
Rollout[]
  -> RolloutAnalyzer.analyze(...)
  -> GradientEstimator.estimate(...)
  -> PolicyTrainingEngine.plan_and_apply(...)
       -> async with ExperienceSet.lock()
       -> ExperienceSet.reload()
       -> PolicyOptimizer.plan(...)
       -> PolicyUpdater.apply(...)
```

### 8.2 OfflinePolicyOptimizationPipeline.eval

```text
CaseLoader -> RolloutExecutor -> Rollout.evaluation -> PipelineEvaluationResult
```

eval 階段不會呼叫 `RolloutAnalyzer`，不會抽 trajectory，也不會寫 policy。它要求 `RolloutExecutor` 返回帶 `evaluation` 的 rollout。

### 8.3 train_from_rollouts

即時場景或外部系統已經產生 rollout 時，可以繞過 `CaseLoader / PolicySnapshotter / RolloutExecutor`：

```text
Rollout[] -> policy_trainer.train_rollouts(...)
```

約束：每個 rollout 必須包含 `case`。

## 9. Batch 與 Streaming

### 9.1 BatchPolicyTrainer

適合離線訓練，輸入一批 rollout 後直接完成一次：

```text
analyze -> estimate -> plan -> apply
```

### 9.2 StreamingPolicyTrainer

適合即時 commit / 併發 rollout 場景。

流程：

```text
submit_rollout(rollout)
  -> analyze rollout
  -> estimate gradients
  -> submit gradients to StreamingBatcher
  -> 等待該 rollout 所在 batch 被 flush 並 apply
```

flush 觸發條件：

- `max_gradients_per_update` 達到閾值
- 最老 gradient 等待超過 `max_wait_seconds`
- `close()` 時 flush 剩餘內容

預設配置：

```python
@dataclass(slots=True)
class StreamingPolicyTrainerConfig:
    max_gradients_per_update: int = 8
    max_wait_seconds: float = 10.0
    timer_check_interval_seconds: float = 1.0
    trace_console: bool = False
```

程序內全域共享：

```python
get_streaming_policy_trainer(...)
make_streaming_policy_trainer_key(policy_root_uri, request_context)
```

併發安全由 `PolicyTrainingEngine.plan_and_apply(...)` 中的 `ExperienceSet.lock()` 保證。

## 10. Patch Merge 機制

### 10.1 PatchSemanticGradient 到 PatchMergePatch

`PatchMergePolicyOptimizer` 會把每個 `SemanticGradient` 轉為：

```python
@dataclass(slots=True)
class PatchMergePatch:
    before_file: MemoryFile | None
    after_file: MemoryFile
    metadata: dict[str, Any]
```

### 10.2 PatchMergeContextProvider

位置：`openviking/session/memory/patch_merge_context_provider.py`

職責：

- 給 LLM 提供待合併 patch 相關的原始 memory 檔案。
- 將 `MemoryFile` before/after 渲染為欄位級 unified diff。
- 用 embedding 檢索額外候選檔案，幫助發現相似/重複 memory。
- 暴露指定 memory type 的 schema，讓 ExtractLoop 輸出合法 memory operations。

輸入檔案選擇：

```text
required_file_uris = patch target uri / superseded policy uri
extra_candidate_files = embedding search 當前 memory_type 下的相似檔案
max_extra_candidate_files = max(5, len(required_file_uris))
search_limit = max_extra_candidate_files * 2
```

欄位 diff 規則：

- 只展示發生變化的欄位。
- 字符串按行 diff。
- dict/list 先 JSON 格式化再 diff。
- `content` 已在 `Field Diff: content` 中展示，因此不會額外在 metadata 中重複塞完整 content。

### 10.3 PatchMergePolicyOptimizer

```text
SemanticGradient[]
  -> PatchMergeContextProvider.prefetch()
  -> ExtractLoop(max_iterations=1)
  -> ResolvedOperations
  -> PolicyPlanItem[]
```

輸出支援：

- upsert experience
- delete experience

merge 輸入/輸出日誌通過 `tracer.info(..., console=False)` 記錄，避免預設汙染 console。

## 11. session.commit 即時訓練接入

`SessionCompressorV3` 已把使用者記憶抽取和即時訓練接起來。

### 11.1 使用者記憶抽取

`SessionCompressorV3._extract_user_memories(...)`：

1. 通過原使用者記憶 `ExtractLoop` 抽取使用者記憶。
2. case 不再額外單獨呼叫 LLM，而是作為一種普通 memory type：`cases`。
3. 抽取結果交給 `StreamingMemoryUpdater` 做 patch merge 寫入使用者記憶。
4. 如有 `archive_uri`，寫入 `memory_diff.json`，其中包含頂層 `trace_id`。

`memory_diff.json` 頂層結構包含：

```json
{
  "archive_uri": "...",
  "trace_id": "...",
  "extracted_at": "...",
  "operations": {...},
  "skipped_operations": [...],
  "summary": {...}
}
```

### 11.2 從 cases 觸發 streaming train

`SessionCompressorV3.train_from_extracted_cases(...)`：

```text
extracted Case[] + original commit messages
  -> Rollout(case, messages, policy_snapshot_id=session-commit:...)
  -> StreamingPolicyTrainer.submit_rollout(...)
```

即真實 session.commit 產生的對話可以被轉為 rollout 輸入訓練框架。

## 12. SessionCommitPolicyTrainer：遠端服務端訓練

`SessionCommitPolicyTrainer` 是一個 `PolicyTrainer` 實現，用於“訓練框架在外部，Business Data Platform 服務端負責訓練”的場景。

它會把 rollout 寫成一個臨時 session：

```text
[CaseSpec message]
[Rollout messages]
[OutcomeEvaluation message]
```

其中：

- `CaseSpec` 放在開頭，只含 case/rubric/task context，不含 evaluation。
- `OutcomeEvaluation` 放在最後，只含 evaluation，作為訓練訊號。
- rollout 的工具結果會通過 `ToolPart` 的 `tool_output` 上傳，而不是普通 text。

然後執行：

```text
client.create_session(...)
client.batch_add_messages(...)
client.commit_session(...)
client.get_task(...) until completed/failed/timeout
```

CaseSpec 會做精簡，避免傳入巨大或重複欄位：

- 不傳 `policy`
- 不傳 `data_root`
- 不傳 `rollout_metadata`
- 不傳 `policy_snapshot_id`
- 保留 `domain/split/data_split/task_id/task_no/user_query/ground_truth/rubric`

## 13. Remote HTTP 元件

`components/remote.py` 提供通用 HTTP 元件：

- `RemoteCaseLoader`
- `RemoteRolloutExecutor`

它們面向一個環境/benchmark service：

```text
POST /v1/cases/query
POST /v1/rollouts/execute
GET  /v1/rollouts/executions/{execution_id}
```

其中 `/v1/rollouts/execute` 只負責提交單個 case 的 rollout execution，返回
`execution_id`；`RemoteRolloutExecutor` 會併發提交多個 case，並通過
`/v1/rollouts/executions/{execution_id}` 輪詢狀態。這樣長耗時 rollout 不會佔用
一個超長 HTTP request，也便於未來 benchmark service 做多機部署和負載均衡。

這樣訓練框架不需要直接依賴 tau2 或其他 benchmark 的程式碼，只依賴通用
Case/Rollout JSON 協議。

## 14. tau2 集成

### 14.1 架構

當前 tau2 訓練分為兩個程序：

```text
tau2 service
  - 依賴 tau2 / vikingbot
  - 暴露 case query 和 rollout execute HTTP API

train/eval runner
  - 使用 RemoteCaseLoader / RemoteRolloutExecutor
  - 使用 SessionCommitPolicyTrainer 提交 Business Data Platform session.commit
  - 本身不直接依賴 tau2 runtime
```

### 14.2 tau2 service

位置：

```text
benchmark/tau2/train/service_app.py
benchmark/tau2/train/run_service.sh
```

啟動：

```bash
benchmark/tau2/train/run_service.sh \
  --host 127.0.0.1 \
  --port 1944
```

### 14.3 remote train/eval

位置：

```text
benchmark/tau2/train/run_batch_train_eval.sh
openviking/session/train/run_batch_train_eval.py
openviking/session/train/batch_runner.py
```

預先只跑 test 分數（不訓練）：

```bash
benchmark/tau2/train/run_batch_train_eval.sh \
  --epochs 0 \
  --eval-index 24 \
  --trials 8
```

訓練前先跑一次 test baseline，再訓練並跑最終 test：

```bash
benchmark/tau2/train/run_batch_train_eval.sh \
  --baseline-eval \
  --epochs 4 \
  --trials 8
```

輸出以 accuracy 為主，階段日誌由 session/train lifecycle hooks 統一輸出：

```text
[baseline_rollout] epoch=-1 trials=8 cases_per_trial=25 total_rollouts=200 accuracy=... ± ... avg_reward=... ± ...
================= epoch 0 =================
[train_rollout] epoch=0 cases=25 accuracy=... passed=... avg_reward=...
[train] epoch=0 commits=25 errors=0
[final_test_rollout] epoch=4 trials=8 cases_per_trial=25 total_rollouts=200 accuracy=... ± ... avg_reward=... ± ...
```

### 14.4 tau2 rollout messages

`Tau2RolloutExecutor` 會把工具結果轉成真正的 `ToolPart`：

```json
{
  "type": "tool",
  "tool_id": "tau2-tool-0",
  "tool_name": "get_reservation_details",
  "tool_input": {...},
  "tool_output": "...",
  "tool_status": "completed"
}
```

這樣上傳到 `session.commit` 後，服務端可以複用已有 tool output 外部化和 memory extraction 邏輯。


## 15. tau2 接入新評測框架示意圖

tau2 的接入方式體現了推薦的 benchmark 整合模式：benchmark runtime 獨立成 HTTP service，訓練框架只通過通用 `RemoteCaseLoader` / `RemoteRolloutExecutor` 接入。

<img src="https://gist.githubusercontent.com/chenjw/5c8f05a10f2c3f1913eb6c9d4293f0a4/raw/d9151bc8bbceccf3e56486897061c76a5d6f0cfa/tau2-train-eval-architecture.svg" alt="tau2 接入 Business Data Platform 新訓練評測框架" width="100%">


圖中需要特別注意：tau2 runtime service 雖然不負責訓練寫入，但它執行 rollout 時會通過 VikingBot / Business Data Platform tools 讀取當前 Business Data Platform memories。因此 final_eval 能看到 train epoch 後寫入的最新 experiences。

### 15.1 接入分層

```text
tau2 service
  - 依賴 tau2 / vikingbot
  - 負責 case 查詢、rollout 執行、環境 reward 評估
  - 輸出通用 Case / Rollout / RubricEvaluation JSON

train/eval runner
  - 不直接依賴 tau2 runtime
  - 使用 RemoteCaseLoader 查詢 case
  - 使用 RemoteRolloutExecutor 執行 rollout
  - 使用 SessionCommitPolicyTrainer 把訓練 rollout 提交給 Business Data Platform 服務端

Business Data Platform server
  - 通過 session.commit 接收 rollout messages
  - 服務端內部執行 trajectory extraction / gradient estimation / patch merge / policy update
```

### 15.2 train/eval 時序

```text
baseline_eval:
  RemoteCaseLoader(test)
    -> RemoteRolloutExecutor
    -> Tau2RolloutExecutor
    -> rollout.evaluation
    -> accuracy / avg_reward report

train epoch:
  RemoteCaseLoader(train)
    -> RemoteRolloutExecutor
    -> Tau2RolloutExecutor
    -> SessionCommitPolicyTrainer
    -> session.commit
    -> SessionCompressorV3
    -> StreamingPolicyTrainer
    -> experiences update

final_eval:
  RemoteCaseLoader(test)
    -> RemoteRolloutExecutor
    -> Tau2RolloutExecutor reads latest Business Data Platform experiences
    -> rollout.evaluation
    -> accuracy delta report
```

### 15.3 為什麼 eval 不走 RolloutAnalyzer

在 tau2 場景中，環境執行完 rollout 後可以直接給出 reward，因此 `Tau2RolloutExecutor` 會返回：

```python
Rollout(
    case=case,
    messages=messages,
    policy_snapshot_id=snapshot_id,
    evaluation=RubricEvaluation(...),
)
```

所以 `OfflinePolicyOptimizationPipeline.eval(...)` 只統計 `rollout.evaluation`：

```text
accuracy = passed_count / case_count
average_reward = mean(evaluation.score)
```

eval 不抽 trajectory、不估計 gradient、不寫 experience。

### 15.4 訓練如何通過 session.commit 進入服務端

`SessionCommitPolicyTrainer` 會把 rollout 轉成臨時 session messages：

```text
[Business Data Platform Training CaseSpec]
[Rollout messages: user / assistant / ToolPart]
[Business Data Platform OutcomeEvaluation]
```

其中：

- `CaseSpec` 放在開頭，只描述任務和 rubric，不包含 evaluation。
- `OutcomeEvaluation` 放在最後，作為訓練訊號。
- tau2 工具結果使用 `ToolPart.tool_output` 上傳，服務端可以複用已有 tool output 外部化和 memory extraction 邏輯。

### 15.5 指標展示

tau2 runner 的報告以正確率為主：

```text
[baseline_eval] epoch=-1 cases=10 accuracy=20.00% passed=2/10 avg_reward=0.200000
[train_epoch] epoch=0 cases=50 accuracy=18.00% passed=9/50 avg_reward=0.180000 commits=50 errors=0
[final_eval] epoch=1 cases=10 accuracy=30.00% passed=3/10 avg_reward=0.300000

baseline accuracy: 20.00% (2/10)
final accuracy: 30.00% (3/10)
accuracy delta: +10.00pp
```

`average_reward` 保留為輔助指標；主指標是 `accuracy`。

### 15.6 以 tau2 為例：新場景接入需要實現的介面

一個新的 benchmark / domain / environment 接入訓練評測框架時，推薦複用 tau2
的分層方式：把場景 runtime 獨立成一個 HTTP service，訓練程序繼續使用通用
`RemoteCaseLoader` / `RemoteRolloutExecutor`。訓練框架不關心場景內部怎麼啟動
agent、怎麼呼叫工具、怎麼計算 reward，只要求 service 實現下面這些協議。

#### 15.6.1 Case 查詢介面

```text
POST /v1/cases/query
```

請求：

```json
{
  "dataset": "tau2",
  "domain": "airline",
  "split": "train",
  "cursor": null,
  "limit": 100,
  "filters": {}
}
```

響應：

```json
{
  "cases": [
    {
      "name": "tau2_airline_train_0",
      "task_signature": "tau2:airline:train:0",
      "input": {
        "domain": "airline",
        "split": "train",
        "task_id": "0",
        "task_no": 0,
        "user_query": "...",
        "ground_truth": "..."
      },
      "rubric": {
        "name": "tau2_airline_train_0_rubric",
        "description": "...",
        "criteria": [
          {
            "name": "tau2_reward",
            "description": "The tau2 environment reward is 1.0.",
            "required": true,
            "weight": 1.0,
            "metadata": {}
          }
        ],
        "metadata": {}
      },
      "metadata": {
        "dataset": "tau2",
        "domain": "airline",
        "source": "tau2",
        "split": "train"
      }
    }
  ],
  "next_cursor": "100"
}
```

接入要求：

- `dataset/domain/split` 用於定位資料集切片。
- `cursor/limit` 用於分頁；沒有下一頁時 `next_cursor = null`。
- `Case.input` 只放 rollout 必需的任務輸入和場景元資訊，不要塞訓練框架已經能從
  上下文拿到的內容，例如完整 system prompt、完整 rollout metadata、evaluation
  結果或 policy snapshot。
- `Case.rubric` 必須能描述評測目標；如果環境能直接給 reward，也仍然要提供
  rubric，便於訓練側把 reward 轉成統一的 `RubricEvaluation`。

tau2 中對應實現是：

```text
benchmark/tau2/train/service_app.py::query_cases
benchmark/tau2/train/case_loader.py::Tau2CaseLoader
```

#### 15.6.2 Rollout 提交接口

```text
POST /v1/rollouts/execute
```

請求：

```json
{
  "case": { "...": "Case JSON" },
  "policy_set": {
    "root_uri": "viking://user/default/memories/experiences",
    "policies": [],
    "metadata": {}
  },
  "execution_context": {
    "policy_snapshot_id": "tau2-policy-snapshot:...",
    "metadata": {
      "epoch": 0,
      "training": true
    }
  },
  "options": {
    "config_path": "/path/to/ov.conf",
    "max_iterations": 30,
    "keep_default_tools": true,
    "rollout_language": "default"
  }
}
```

響應：

```json
{
  "execution_id": "rollout_exec_...",
  "status": "running",
  "case_name": "tau2_airline_train_0",
  "created_at": 1781097747.0,
  "updated_at": 1781097747.0,
  "error": null
}
```

接入要求：

- 該介面只提交一個 case 的 rollout execution，不需要同步等待 rollout 完成。
- 客戶端會對多個 case 發起多個請求，service 端可以自行排隊、限流、排程到不同
  worker 或機器。
- `policy_set.root_uri` 告訴 runtime 當前 experiences 根目錄；tau2 rollout 期間
  VikingBot 會通過 Business Data Platform recall 讀取這裡的最新經驗。
- `execution_context.policy_snapshot_id` 必須原樣寫入返回的 `Rollout.policy_snapshot_id`，
  用於追蹤這次 rollout 使用的是哪次 policy snapshot。

tau2 中對應實現是：

```text
benchmark/tau2/train/service_app.py::execute_rollout
benchmark/tau2/train/service_app.py::_run_rollout_execution
benchmark/tau2/train/rollout_executor.py::Tau2RolloutExecutor
```

#### 15.6.3 Rollout 狀態輪詢介面

```text
GET /v1/rollouts/executions/{execution_id}
```

執行中響應：

```json
{
  "execution_id": "rollout_exec_...",
  "status": "running",
  "case_name": "tau2_airline_train_0",
  "created_at": 1781097747.0,
  "updated_at": 1781097750.0,
  "error": null
}
```

完成響應：

```json
{
  "execution_id": "rollout_exec_...",
  "status": "completed",
  "case_name": "tau2_airline_train_0",
  "created_at": 1781097747.0,
  "updated_at": 1781097760.0,
  "error": null,
  "rollout": {
    "case": { "...": "Case JSON" },
    "messages": [
      {
        "role": "user",
        "parts": [
          {
            "type": "text",
            "text": "..."
          }
        ]
      },
      {
        "role": "assistant",
        "parts": [
          {
            "type": "tool",
            "tool_id": "tau2-tool-0",
            "tool_name": "get_reservation_details",
            "tool_input": {"reservation_id": "EHGLP3"},
            "tool_output": "...",
            "tool_status": "completed"
          }
        ]
      }
    ],
    "policy_snapshot_id": "tau2-policy-snapshot:...",
    "evaluation": {
      "passed": false,
      "score": 0.0,
      "criterion_results": [
        {
          "criterion_name": "tau2_reward",
          "passed": false,
          "score": 0.0,
          "feedback": ["tau2 environment reward is below 1.0."],
          "evidence": [],
          "metadata": {"reward": 0.0}
        }
      ],
      "feedback": ["tau2 environment reward is below 1.0."],
      "metadata": {
        "source": "tau2_executor",
        "reward": 0.0
      }
    },
    "metadata": {
      "memory": "...",
      "tools_used": [],
      "iterations": 6
    }
  }
}
```

失敗響應：

```json
{
  "execution_id": "rollout_exec_...",
  "status": "failed",
  "case_name": "tau2_airline_train_0",
  "created_at": 1781097747.0,
  "updated_at": 1781097752.0,
  "error": "..."
}
```

接入要求：

- `status` 至少支持 `running/completed/failed`。
- `completed` 時必須返回完整 `rollout`。
- `failed` 時必須返回可讀 `error`，訓練側會把它歸入該 case 的 rollout 失敗。
- `Rollout.messages` 應使用 Business Data Platform `Message` / `Part` 結構；工具呼叫和工具結果
  用 `ToolPart`，不要把 `tool-call:\nname: ...` 塞進普通 text content。
- `Rollout.evaluation` 在 eval 階段是必需欄位；如果沒有 evaluation，
  `OfflinePolicyOptimizationPipeline.eval(...)` 會失敗。

#### 15.6.4 RolloutExecutor 內部職責

新場景自己的 rollout executor 需要完成這些事情：

1. 根據 `Case.input` 初始化環境和使用者模擬器。
2. 根據 `policy_set.root_uri` / Business Data Platform 配置讓 agent 讀取當前 experiences。
3. 執行 agent loop，記錄 user/assistant/tool messages。
4. 把環境 reward 或 judge 結果轉成 `RubricEvaluation`。
5. 返回統一 `Rollout`：

```python
Rollout(
    case=case,
    messages=messages,
    policy_snapshot_id=context.policy_snapshot_id,
    evaluation=RubricEvaluation(...),
    metadata={
        "tools_used": [...],
        "iterations": ...,
        "memory": "...",
    },
)
```

tau2 的 `Tau2RolloutExecutor` 就是這個適配層：它一側依賴 tau2/VikingBot runtime，
另一側只輸出訓練框架理解的 `Rollout`。

#### 15.6.5 最小接入清單

接入一個新場景，最少需要實現：

| 介面/元件 | 必需 | 作用 |
|---|---:|---|
| `POST /v1/cases/query` | 是 | 分頁返回 `Case[]` |
| `POST /v1/rollouts/execute` | 是 | 提交單個 rollout execution |
| `GET /v1/rollouts/executions/{execution_id}` | 是 | 輪詢 rollout 狀態並取回 `Rollout` |
| `RubricEvaluation` 轉換 | eval 必需 | 把場景 reward/judge 結果轉成統一 evaluation |
| `Message` / `ToolPart` 轉換 | 訓練必需 | 保留 agent 行為和工具證據，供 session.commit 抽取 trajectory/experience |
| `GET /health` | 建議 | 方便 runner 或部署系統做 preflight |

如果新場景不想提供 HTTP service，也可以在同進程內直接實現
`CaseLoader` / `RolloutExecutor` Protocol；但跨程序、多機或重 runtime 依賴的場景，
推薦採用 tau2 這種 service 方式。

## 16. 當前主要元件清單

| 元件 | 檔案 | 說明 |
|---|---|---|
| `OfflinePolicyOptimizationPipeline` | `pipeline.py` | 離線 train/eval 編排 |
| `PolicyTrainingEngine` | `engine.py` | 共享 analyze/estimate/plan/apply 核心 |
| `ListCaseLoader` | `components/case_loader.py` | 記憶體 case loader |
| `RemoteCaseLoader` | `components/remote.py` | HTTP case loader |
| `RemoteRolloutExecutor` | `components/remote.py` | HTTP rollout executor |
| `SingleTurnLLMRolloutExecutor` | `components/rollout_executor.py` | 簡單單輪 LLM rollout |
| `TrajectoryRolloutAnalyzer` | `components/trajectory_analyzer.py` | 抽取 trajectory memory |
| `ExperienceGradientEstimator` | `components/gradient_estimator.py` | trajectory -> PatchSemanticGradient |
| `PatchMergePolicyOptimizer` | `components/policy_optimizer.py` | 多 gradient 全局 merge |
| `DryRunPolicyUpdater` | `components/policy_updater.py` | dry-run apply |
| `MemoryFilePolicyUpdater` | `components/policy_updater.py` | VikingFS 寫回 experiences |
| `BatchPolicyTrainer` | `components/policy_trainer.py` | batch rollout 訓練 |
| `StreamingPolicyTrainer` | `components/policy_trainer.py` | 即時攢批訓練 |
| `SessionCommitPolicyTrainer` | `components/session_commit.py` | 通過 session.commit 遠端訓練 |
| `ContentHashPolicySnapshotter` | `components/snapshotter.py` | 內容 hash snapshot id |
| `ExperienceSetLoader` | `components/memory_store.py` | 從 experiences 目錄載入 policy set |

## 17. 端到端本地訓練虛擬碼

```python
policy_set = await ExperienceSetLoader(viking_fs).load(
    "viking://user/default/memories/experiences",
    ctx=request_context,
)

pipeline = OfflinePolicyOptimizationPipeline(
    snapshotter=ContentHashPolicySnapshotter(),
    rollout_executor=SomeRolloutExecutor(),
    rollout_analyzer=TrajectoryRolloutAnalyzer(viking_fs=viking_fs, vikingdb=vikingdb),
    gradient_estimator=ExperienceGradientEstimator(viking_fs=viking_fs),
    policy_optimizer=PatchMergePolicyOptimizer(viking_fs=viking_fs),
    policy_updater=MemoryFilePolicyUpdater(viking_fs=viking_fs),
)

result = await pipeline.train(
    case_loader=ListCaseLoader(cases, batch_size=8),
    policy_set=policy_set,
    context=PipelineContext(
        max_epochs=1,
        analysis_context=TrajectoryAnalyzerContext(request_context=request_context),
        gradient_context=ExperienceGradientContext(
            request_context=request_context,
            messages=[],
        ),
        optimization_context=PatchMergePolicyOptimizerContext(
            request_context=request_context,
        ),
        apply_context=request_context,
    ),
)
```

## 18. 設計原則

- `Case` 是訓練/評測樣本，不再使用 `Outcome` 概念。
- `Rubric` 定義驗收標準；`RubricEvaluation` 是一次 rollout 的評估結果。
- `Rollout` 保留原始執行訊息和可選 evaluation；`Trajectory` 是從 rollout 中抽取的可訓練樣本。
- `SemanticGradient` 是 memory-file before/after 級別的語義更新訊號。
- `PolicyOptimizer` 只規劃，不寫檔案；`PolicyUpdater` 才是寫入邊界。
- batch 和 streaming 共用同一個 `PolicyTrainingEngine`。
- 併發寫入通過 `ExperienceSet.lock() + reload()` 序列化 optimizer/apply 階段。
- 遠端 benchmark 整合應走 `RemoteCaseLoader / RemoteRolloutExecutor`，不要讓訓練框架直接依賴 benchmark runtime。
