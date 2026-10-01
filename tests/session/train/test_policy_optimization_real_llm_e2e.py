# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from test_fakes import InMemoryVikingFS

from openviking.message import Message
from openviking.models.vlm.llm import parse_json_from_response
from openviking.server.config import load_server_config
from openviking.session.train import (
    Case,
    ContentHashPolicySnapshotter,
    ExperienceGradientContext,
    ExperienceSetLoader,
    ListCaseLoader,
    MemoryFilePolicyUpdater,
    OfflinePolicyOptimizationPipeline,
    PatchMergePolicyOptimizer,
    PatchMergePolicyOptimizerContext,
    PipelineContext,
    Rubric,
    RubricCriterion,
    SingleTurnLLMRolloutExecutor,
    TrajectoryAnalyzerContext,
    TrajectoryRolloutAnalyzer,
)
from openviking.session.train.components.gradient_estimator import ExperienceGradientEstimator
from openviking.telemetry import start_current_span, tracer
from openviking.telemetry.tracer import init_tracer_from_server_config
from openviking_cli.utils.config import get_openviking_config


@pytest.fixture(scope="module", autouse=True)
def _init_real_llm_e2e_tracer():
    """Initialize tracer from server.observability.traces in ~/.openviking/ov.conf."""

    init_tracer_from_server_config(load_server_config())


class RealRubricTrajectoryAnalyzer:
    """Evaluate a rollout with the real LLM and emit one trajectory for training.

    This keeps the train pipeline shape as one native epoch:
    rollout -> evaluation/trajectory extraction -> gradient -> plan -> apply.
    """

    def __init__(self, trajectory_uri: str, viking_fs: InMemoryVikingFS, vlm):
        self.trajectory_uri = trajectory_uri
        self.viking_fs = viking_fs
        self.vlm = vlm
        self.calls = []
        self.unlocked_count = 1

    @tracer(
        "train.test.real_llm_e2e.real_rubric_trajectory_analyzer",
        ignore_result=True,
        ignore_args=True,
    )
    async def analyze(self, rollout, context):
        from openviking.session.train import (
            CriterionResult,
            RolloutAnalysis,
            RubricEvaluation,
            Trajectory,
        )

        self.calls.append((rollout, context))
        evaluation_payload = await _evaluate_rollout_with_real_llm(
            vlm=self.vlm,
            case=rollout.case,
            rollout_messages=rollout.messages,
            active_criteria=[
                criterion.name for criterion in rollout.case.rubric.criteria[: self.unlocked_count]
            ],
        )
        active_passed = len(_passed_criterion_names(evaluation_payload)) >= self.unlocked_count
        if active_passed and self.unlocked_count < len(rollout.case.rubric.criteria):
            self.unlocked_count += 1
        evaluation = RubricEvaluation(
            passed=bool(evaluation_payload["passed"]),
            score=float(evaluation_payload["score"]),
            criterion_results=[
                CriterionResult(
                    criterion_name=str(item.get("criterion_name") or "unknown"),
                    passed=bool(item.get("passed")),
                    score=float(item.get("score") or 0.0),
                    feedback=[str(value) for value in item.get("feedback", [])],
                    evidence=[str(value) for value in item.get("evidence", [])],
                )
                for item in evaluation_payload.get("criterion_results", [])
                if isinstance(item, dict)
            ],
            feedback=[str(value) for value in evaluation_payload.get("feedback", [])],
            metadata={"raw_payload": evaluation_payload},
        )
        assistant_text = "\n".join(
            message.content for message in rollout.messages if message.role == "assistant"
        )
        trajectory_outcome = "success" if evaluation.passed else "failure"
        next_failed_name, next_failed_feedback = _first_failed_criterion_feedback(
            evaluation_payload,
            rollout.case,
        )
        learning_target = next_failed_name or "all_passed"
        trajectory_content = (
            "# 複雜重複預訂處理軌跡\n"
            f"評估得分：{evaluation.score:.2f}\n"
            f"評估結論：{'通過' if evaluation.passed else '未通過'}\n"
            f"當前解鎖階段：{', '.join(evaluation_payload.get('active_criteria', []))}\n"
            f"本輪學習目標：{learning_target}\n"
            f"本輪反饋：{next_failed_feedback}\n\n"
            "## 關鍵訓練訊號\n"
            f"- 只根據本輪學習目標改進經驗：{learning_target}\n"
            f"- 修正建議：{next_failed_feedback}\n\n"
            "## 助手輸出\n"
            f"{assistant_text}\n"
        )
        self.viking_fs.files[self.trajectory_uri] = (
            trajectory_content
            + "\n<!-- MEMORY_FIELDS\n"
            + json.dumps(
                {
                    "memory_type": "trajectories",
                    "trajectory_name": "complex_duplicate_booking_case",
                    "outcome": trajectory_outcome,
                    "retrieval_anchor": f"階段：{learning_target}；能力：複雜重複預訂處理",
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n-->"
        )
        return RolloutAnalysis(
            evaluation=evaluation,
            trajectories=[
                Trajectory(
                    name="complex_duplicate_booking_case",
                    uri=self.trajectory_uri,
                    content=trajectory_content.strip(),
                    outcome=trajectory_outcome,
                    retrieval_anchor=f"階段：{learning_target}；能力：複雜重複預訂處理",
                    metadata={"memory_type": "trajectories"},
                )
            ],
            metadata={
                "rollout_messages": rollout.messages,
                "policy_snapshot_id": rollout.policy_snapshot_id,
            },
        )


def _case() -> Case:
    return Case(
        name="complex_duplicate_booking_case",
        task_signature="complex_booking_duplicate",
        input={
            "user_request": (
                "我好像重複訂了酒店，但不確定哪一筆重複。請幫我處理，如果確實重複就取消多餘的那筆。"
            ),
            "booking_records": [
                {
                    "booking_id": "A-100",
                    "hotel": "上海中心酒店",
                    "check_in": "2026-07-01",
                    "check_out": "2026-07-03",
                    "room_type": "豪華大床房",
                    "guest": "張三",
                    "price_cny": 1800,
                    "created_at": "2026-05-01T10:00:00",
                    "cancellation_fee_cny": 0,
                    "refund_cny": 1800,
                    "status": "confirmed",
                },
                {
                    "booking_id": "A-101",
                    "hotel": "上海中心酒店",
                    "check_in": "2026-07-01",
                    "check_out": "2026-07-03",
                    "room_type": "豪華大床房",
                    "guest": "張三",
                    "price_cny": 1800,
                    "created_at": "2026-05-01T10:05:00",
                    "cancellation_fee_cny": 0,
                    "refund_cny": 1800,
                    "status": "confirmed",
                },
                {
                    "booking_id": "A-102",
                    "hotel": "上海中心酒店",
                    "check_in": "2026-07-01",
                    "check_out": "2026-07-03",
                    "room_type": "行政雙床房",
                    "guest": "張三",
                    "price_cny": 2200,
                    "created_at": "2026-05-01T10:08:00",
                    "cancellation_fee_cny": 300,
                    "refund_cny": 1900,
                    "status": "confirmed",
                },
            ],
            "policy_constraints": [
                "沒有使用者二次確認前，不能真正執行取消動作。",
                "如果要取消，需要先告知退款金額和取消費。",
            ],
        },
        rubric=Rubric(
            name="complex_booking_duplicate_hidden_rubric",
            description=("分階段處理複雜重複預訂：識別重複、選對目標、檢查取消成本、請求確認。"),
            criteria=[
                RubricCriterion(
                    name="identify_duplicate",
                    description=(
                        "必須核驗酒店、入住/離店日期、房型、入住人、價格等關鍵資訊，"
                        "識別 A-100 和 A-101 是重複候選。"
                    ),
                    required=True,
                    weight=0.25,
                ),
                RubricCriterion(
                    name="select_correct_target",
                    description=(
                        "必須選擇取消建立時間更晚的 A-101，保留 A-100，"
                        "且不能誤取消同酒店同日期但房型不同的 A-102。"
                    ),
                    required=True,
                    weight=0.25,
                ),
                RubricCriterion(
                    name="check_cancellation_cost",
                    description="取消前必須說明 A-101 的退款金額和取消費，並提醒 A-102 有取消費。",
                    required=True,
                    weight=0.25,
                ),
                RubricCriterion(
                    name="request_confirmation",
                    description="不能直接執行取消；必須先給出建議並請求使用者確認後再取消。",
                    required=True,
                    weight=0.25,
                ),
            ],
        ),
    )


def _strict_policy_prompt(case, policy_set, context) -> str:
    del context
    experiences = "\n\n".join(
        f"### {policy.name} v{policy.version} [{policy.status}]\n{policy.content}"
        for policy in policy_set.policies
    )
    if not experiences:
        experiences = "(no experience policies available)"
    return "\n".join(
        [
            "你正在執行一個受經驗策略控制的離線案例。",
            "必須優先遵循 Experience Policies；如果經驗策略與常識衝突，也先按經驗策略輸出。",
            "這裡不會向你展示隱藏評分 Rubric。請只根據使用者輸入和經驗策略完成任務。",
            "請給出你會執行的最終處理動作，不要只複述原則。",
            "",
            "# Experience Policies",
            experiences,
            "",
            "# Case Input",
            json.dumps(case.input, ensure_ascii=False, indent=2, sort_keys=True),
        ]
    )


def _passed_criterion_names(payload: dict) -> set[str]:
    return {
        str(item.get("criterion_name"))
        for item in payload.get("criterion_results", [])
        if isinstance(item, dict) and item.get("passed")
    }


def _first_failed_criterion_feedback(payload: dict, case: Case) -> tuple[str | None, str]:
    results = {
        str(item.get("criterion_name")): item
        for item in payload.get("criterion_results", [])
        if isinstance(item, dict)
    }
    for criterion in case.rubric.criteria:
        item = results.get(criterion.name)
        if item is None or not item.get("passed"):
            feedback = item.get("feedback") if isinstance(item, dict) else None
            if isinstance(feedback, list) and feedback:
                return criterion.name, "; ".join(str(value) for value in feedback)
            return criterion.name, criterion.description
    return None, "所有階段都已通過。"


def _staged_score(payload: dict, case: Case) -> float:
    passed = _passed_criterion_names(payload)
    score = 0.0
    for criterion in case.rubric.criteria:
        if criterion.name not in passed:
            break
        score += float(criterion.weight)
    return max(0.0, min(1.0, score))


async def _evaluate_rollout_with_real_llm(
    *,
    vlm,
    case: Case,
    rollout_messages: list[Message],
    active_criteria: list[str] | None = None,
):
    assistant_text = "\n".join(
        message.content for message in rollout_messages if message.role == "assistant"
    )
    active_criteria = active_criteria or [criterion.name for criterion in case.rubric.criteria]
    active_criterion_set = set(active_criteria)
    visible_criteria = [
        criterion for criterion in case.rubric.criteria if criterion.name in active_criterion_set
    ]
    prompt = "\n".join(
        [
            "你是 OpenViking 離線訓練的嚴格評估器。",
            "請評估助手是否真正完成了當前已解鎖的 hidden Rubric。只根據助手輸出評分。",
            "不要因為 Case Input 中出現了約束就給分；必須看助手是否實際執行了該要求。",
            "",
            "# Case Input",
            json.dumps(case.input, ensure_ascii=False, indent=2, sort_keys=True),
            "",
            "# Active Hidden Rubric",
            f"{case.rubric.name}: {case.rubric.description}",
            *[
                f"- {criterion.name} ({'required' if criterion.required else 'optional'}, "
                f"weight={criterion.weight}): {criterion.description}"
                for criterion in visible_criteria
            ],
            "",
            "# Assistant Output",
            assistant_text,
            "",
            "# 評分規則",
            "- 每個 active criterion 獨立判斷 passed/score。",
            "- 總分 score = active criteria 中通過項數量 / active criteria 數量。",
            "- 非 active criterion 不參與本輪評分，也不要出現在 criterion_results 中。",
            "- 只輸出 JSON，不要輸出 markdown。",
            json.dumps(
                {
                    "passed": False,
                    "score": 0.0,
                    "feedback": ["string"],
                    "criterion_results": [
                        {
                            "criterion_name": "identify_duplicate",
                            "passed": False,
                            "score": 0.0,
                            "feedback": ["string"],
                            "evidence": ["string"],
                        },
                        {
                            "criterion_name": "select_correct_target",
                            "passed": False,
                            "score": 0.0,
                            "feedback": ["string"],
                            "evidence": ["string"],
                        },
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
        ]
    )
    response = await vlm.get_completion_async(prompt=prompt, thinking=False)
    payload = parse_json_from_response(response)
    if not isinstance(payload, dict):
        return {
            "passed": False,
            "score": 0.0,
            "feedback": ["評估器輸出無法解析為 JSON。"],
            "criterion_results": [],
            "raw_response": getattr(response, "content", str(response)),
        }
    payload.setdefault("feedback", [])
    payload.setdefault("criterion_results", [])
    payload["criterion_results"] = [
        item
        for item in payload["criterion_results"]
        if isinstance(item, dict) and item.get("criterion_name") in active_criterion_set
    ]
    if not payload["criterion_results"]:
        payload["criterion_results"] = [
            {
                "criterion_name": criterion.name,
                "passed": False,
                "score": 0.0,
                "feedback": ["評估器沒有返回該階段的結構化結果。"],
                "evidence": [],
            }
            for criterion in visible_criteria
        ]
    for item in payload["criterion_results"]:
        item["passed"] = bool(item.get("passed"))
        try:
            item["score"] = max(0.0, min(1.0, float(item.get("score", 0.0))))
        except (TypeError, ValueError):
            item["score"] = 0.0
    passed_count = sum(1 for item in payload["criterion_results"] if item["passed"])
    payload["score"] = _staged_score(payload, case)
    payload["passed"] = bool(payload.get("passed")) and passed_count == len(visible_criteria)
    payload["active_criteria"] = active_criteria
    return payload


def _print_real_llm_e2e_summary(
    *,
    assistant_text: str,
    trajectory_content: str,
    gradient,
    written_experience: str | None = None,
) -> None:
    lines = [
        "\n========== Real LLM Policy Optimization E2E =========",
        f"[TraceID] {tracer.get_trace_id()}",
        "[Rollout Assistant]",
        assistant_text,
        "",
        "[Extracted Trajectory]",
        trajectory_content,
        "",
        "[Semantic Gradient]",
        f"target_name: {gradient.target_name}",
        f"target_uri: {gradient.target_uri}",
        f"base_version: {gradient.base_version}",
        f"confidence: {gradient.confidence}",
        "",
        "[Gradient before_content]",
        gradient.before_file.plain_content() if gradient.before_file is not None else "None",
        "",
        "[Gradient after_content]",
        gradient.after_file.plain_content(),
    ]
    if written_experience is not None:
        lines.extend(["", "[Written Experience File]", written_experience])
    lines.append("=====================================================\n")
    tracer.info("\n".join(lines), console=True)


def _print_iterative_real_llm_summary(
    *,
    result,
    final_evaluation,
    fs: InMemoryVikingFS,
    experience_uri: str,
) -> None:
    lines = [
        "\n========== Real LLM Iterative Policy Optimization =========",
        f"[TraceID] {tracer.get_trace_id()}",
        f"epochs: {len(result.epochs)}",
        f"final_evaluation_score: {final_evaluation.metadata.get('score')}",
        f"first_score: {result.metadata.get('first_score')}",
        f"final_score: {result.metadata.get('final_score')}",
        f"score_delta: {result.metadata.get('score_delta')}",
        f"last_optimizer: {result.plan.metadata.get('optimizer')}",
        f"last_merge_errors: {result.plan.metadata.get('merge_errors')}",
    ]
    for epoch in result.epochs:
        lines.extend(
            [
                "",
                f"[Epoch {epoch.epoch}]",
                f"score: {epoch.metadata.get('score')}",
                f"snapshot_ids: {epoch.policy_snapshot_ids}",
                f"gradient_count: {epoch.metadata.get('gradient_count')}",
                f"written_uris: {epoch.apply_result.written_uris}",
                f"errors: {epoch.apply_result.errors}",
            ]
        )
        if epoch.gradients:
            for gradient_idx, gradient in enumerate(epoch.gradients):
                lines.extend(
                    [
                        f"[Epoch {epoch.epoch} Gradient {gradient_idx}]",
                        f"target_name: {gradient.target_name}",
                        f"target_uri: {gradient.target_uri}",
                        f"confidence: {gradient.confidence}",
                    ]
                )
                lines.extend(
                    [
                        "gradient_after_content:",
                        gradient.after_file.plain_content(),
                    ]
                )
        for analysis in epoch.analyses:
            messages = analysis.metadata.get("rollout_messages", [])
            assistant_text = "\n".join(
                message.content for message in messages if message.role == "assistant"
            )
            lines.extend(
                [
                    f"case: {analysis.trajectories[0].name if analysis.trajectories else 'n/a'}",
                    f"passed: {analysis.evaluation.passed}",
                    f"feedback: {'; '.join(analysis.evaluation.feedback)}",
                    "assistant:",
                    assistant_text,
                ]
            )
    lines.extend(
        [
            "",
            f"[Final Evaluation {final_evaluation.epoch}]",
            f"score: {final_evaluation.metadata.get('score')}",
            f"snapshot_ids: {final_evaluation.policy_snapshot_ids}",
        ]
    )
    for analysis in final_evaluation.analyses:
        messages = analysis.metadata.get("rollout_messages", [])
        assistant_text = "\n".join(
            message.content for message in messages if message.role == "assistant"
        )
        lines.extend(
            [
                f"passed: {analysis.evaluation.passed}",
                f"feedback: {'; '.join(analysis.evaluation.feedback)}",
                "assistant:",
                assistant_text,
            ]
        )
    lines.extend(["", "[Updated Experience File]", fs.files.get(experience_uri, "")])
    lines.append("==========================================================\n")
    tracer.info("\n".join(lines), console=True)


def _patch_experience_prefetch(monkeypatch, fs: InMemoryVikingFS, experience_uri: str) -> None:
    """Patch experience prefetch so the test reads from the in-memory filesystem."""

    async def search_files(self, query, search_uris=None, limit=5):
        del self, query, search_uris, limit
        return [experience_uri]

    async def read_file(self, uri):
        raw = fs.files.get(uri)
        if raw is None:
            target_name = uri.rstrip("/").split("/")[-1].removesuffix(".md")
            for candidate_uri, candidate_raw in fs.files.items():
                supersedes = f'"supersedes":"{target_name}"'
                if candidate_uri.endswith(".md") and supersedes in candidate_raw:
                    raw = candidate_raw
                    uri = candidate_uri
                    break
        if raw is None:
            raw = fs.files[experience_uri]
            uri = experience_uri
        from openviking.session.memory.utils.memory_file_utils import MemoryFileUtils

        memory_file = MemoryFileUtils.read(raw, uri=uri)
        self.read_file_contents[uri] = memory_file
        result = memory_file.to_metadata()
        result["content"] = memory_file.content
        result["uri"] = uri
        return result

    monkeypatch.setattr(
        "openviking.session.memory.session_extract_context_provider.SessionExtractContextProvider.search_files",
        search_files,
    )
    monkeypatch.setattr(
        "openviking.session.memory.session_extract_context_provider.SessionExtractContextProvider.read_file",
        read_file,
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_policy_optimization_pipeline_real_config_llm_e2e_writes_updated_experience(
    monkeypatch,
):
    with start_current_span("train.test.real_llm_e2e.pipeline"):
        await _run_policy_optimization_pipeline_real_config_llm_e2e_writes_updated_experience(
            monkeypatch
        )


async def _run_policy_optimization_pipeline_real_config_llm_e2e_writes_updated_experience(
    monkeypatch,
):
    root = "viking://user/u/memories/experiences"
    experience_uri = f"{root}/booking_duplicate_handling.md"
    trajectory_uri = "viking://user/u/memories/trajectories/complex_duplicate_booking_case.md"
    fs = InMemoryVikingFS(
        {
            experience_uri: (
                "## Situation\n- 處理使用者取消預訂請求\n\n"
                "## Approach\n"
                "- 如果使用者說可能重複預訂，只對比酒店和入住日期。\n"
                "- 如果酒店和入住日期相同，就直接取消所有相關預訂，不需要檢查房型、退款或二次確認。\n\n"
                "<!-- MEMORY_FIELDS\n"
                '{"memory_type":"experiences","experience_name":"booking_duplicate_handling",'
                '"version":1,"status":"production"}\n'
                "-->"
            )
        }
    )
    request_context = SimpleNamespace(
        user=SimpleNamespace(account_id="default", user_id="u"),
        account_id="default",
    )
    policy_set = await ExperienceSetLoader(viking_fs=fs).load(root, ctx=request_context)
    vlm = get_openviking_config().vlm
    _patch_experience_prefetch(monkeypatch, fs, experience_uri)

    pipeline = OfflinePolicyOptimizationPipeline(
        snapshotter=ContentHashPolicySnapshotter(),
        rollout_executor=SingleTurnLLMRolloutExecutor(
            vlm=vlm,
            prompt_builder=_strict_policy_prompt,
            thinking=False,
        ),
        rollout_analyzer=RealRubricTrajectoryAnalyzer(
            trajectory_uri=trajectory_uri,
            viking_fs=fs,
            vlm=vlm,
        ),
        gradient_estimator=ExperienceGradientEstimator(
            viking_fs=fs,
            vlm=vlm,
        ),
        policy_optimizer=PatchMergePolicyOptimizer(
            viking_fs=fs,
            vlm=vlm,
        ),
        policy_updater=MemoryFilePolicyUpdater(viking_fs=fs),
    )

    result = await pipeline.train(
        case_loader=ListCaseLoader([_case()]),
        policy_set=policy_set,
        context=PipelineContext(
            analysis_context=TrajectoryAnalyzerContext(request_context=request_context),
            gradient_context=ExperienceGradientContext(
                request_context=request_context,
                messages=[],
            ),
            optimization_context=PatchMergePolicyOptimizerContext(request_context=request_context),
            apply_context=request_context,
            max_epochs=4,
        ),
    )
    final_evaluation = await pipeline.eval(
        case_loader=ListCaseLoader([_case()]),
        policy_set=result.apply_result.updated_policy_set,
        context=PipelineContext(
            analysis_context=TrajectoryAnalyzerContext(request_context=request_context),
            execution_metadata={"epoch": 4},
        ),
    )

    rollout_messages = result.analyses[0].metadata["rollout_messages"]
    assistant_text = rollout_messages[1].content
    trajectory_content = result.analyses[0].trajectories[0].content
    gradient = result.gradients[0]
    _print_iterative_real_llm_summary(
        result=result,
        final_evaluation=final_evaluation,
        fs=fs,
        experience_uri=experience_uri,
    )
    assert assistant_text.strip()
    assert trajectory_content.strip()
    assert gradient.after_file.plain_content().strip()
    assert all(epoch.apply_result.errors == [] for epoch in result.epochs)
    written_uris = [uri for epoch in result.epochs for uri in epoch.apply_result.written_uris]
    assert experience_uri in written_uris
    assert result.plan.metadata["optimizer"] == "patch_merge"
    assert any(epoch.plan.metadata.get("optimizer") == "patch_merge" for epoch in result.epochs)
    assert len(result.epochs) == 4
    assert result.evaluation_passes == []
    assert final_evaluation.metadata["score"] > result.metadata["first_score"]
    assert result.metadata["score_delta"] > 0
    assert len({epoch.metadata["score"] for epoch in result.epochs}) >= 3
    assert "重複" in fs.files[experience_uri]
    assert "房型" in fs.files[experience_uri]
    assert "確認" in fs.files[experience_uri]


@pytest.mark.asyncio
@pytest.mark.integration
@tracer(
    "train.test.real_llm_e2e.gradient_estimator",
    ignore_result=True,
    ignore_args=True,
    is_new_trace=True,
)
async def test_experience_gradient_estimator_real_config_llm_generates_gradient(
    monkeypatch,
):
    root = "viking://user/u/memories/experiences"
    experience_uri = f"{root}/booking_duplicate_handling.md"
    trajectory_uri = "viking://user/u/memories/trajectories/duplicate_booking_case.md"
    fs = InMemoryVikingFS(
        {
            experience_uri: (
                "## Situation\n- 重複預訂處理\n\n"
                "<!-- MEMORY_FIELDS\n"
                '{"memory_type":"experiences","experience_name":"booking_duplicate_handling",'
                '"version":1,"status":"production"}\n'
                "-->"
            ),
            trajectory_uri: (
                "# 重複預訂處理軌跡\n"
                "使用者要求取消重複預訂。助手先核驗兩筆預訂是否確實重複，"
                "然後只取消重複的那一筆，避免誤取消原始有效預訂。\n\n"
                "<!-- MEMORY_FIELDS\n"
                '{"memory_type":"trajectories","trajectory_name":"duplicate_booking_case",'
                '"outcome":"success","retrieval_anchor":"階段：最終處理；能力：重複預訂處理"}\n'
                "-->"
            ),
        }
    )
    request_context = SimpleNamespace(
        user=SimpleNamespace(account_id="default", user_id="u"),
        account_id="default",
    )
    policy_set = await ExperienceSetLoader(viking_fs=fs).load(root, ctx=request_context)

    _patch_experience_prefetch(monkeypatch, fs, experience_uri)

    rollout_executor = SingleTurnLLMRolloutExecutor(
        vlm=get_openviking_config().vlm,
        thinking=False,
    )
    analyzer = TrajectoryRolloutAnalyzer(viking_fs=fs)
    snapshotter = ContentHashPolicySnapshotter()
    snapshot_id = await snapshotter.snapshot(policy_set)
    rollouts = await rollout_executor.execute(
        [_case()],
        policy_set,
        SimpleNamespace(policy_snapshot_id=snapshot_id, metadata={}),
    )
    analysis = await analyzer.analyze(
        rollouts[0],
        TrajectoryAnalyzerContext(request_context=request_context),
    )

    estimator = ExperienceGradientEstimator(
        viking_fs=fs,
        vlm=get_openviking_config().vlm,
    )
    gradients = await estimator.estimate(
        analysis,
        policy_set,
        ExperienceGradientContext(request_context=request_context, messages=[]),
    )

    assert gradients
    gradient = gradients[0]
    _print_real_llm_e2e_summary(
        assistant_text=analysis.metadata["rollout_messages"][1].content,
        trajectory_content=analysis.trajectories[0].content,
        gradient=gradient,
    )
    assert gradient.target_name
    assert gradient.after_file.plain_content().strip()
    assert gradient.links
    assert gradient.links[0].to_uri in fs.files
    assert "/memories/trajectories/" in gradient.links[0].to_uri
