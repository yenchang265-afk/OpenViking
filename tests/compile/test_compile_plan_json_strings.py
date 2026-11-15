"""Planner output whose nested objects arrive as JSON strings."""

import json

import pytest
from pydantic import ValidationError

from openviking.compile.plan import Contract, PlanProposal, ReviewDecision, Routing, parse_plan

PLAN = "drafts = p.map(sources, task=contract.extract)\np.finalize(drafts, into=target)"

CONTRACT = {
    "extract": {"instructions": "Extract facts.", "input_unit": "file"},
    "reduce": {"instructions": "Write topic pages."},
    "routing": {"mode": "semantic", "instructions": "Group records by topic."},
    "output_format": "wiki",
}


def test_plan_proposal_accepts_contract_json_string():
    proposal = PlanProposal.model_validate({"contract": json.dumps(CONTRACT), "plan": PLAN})
    assert proposal.contract.extract.instructions == "Extract facts."
    assert proposal.contract.reduce.instructions == "Write topic pages."
    assert proposal.contract.output_format == "wiki"
    assert parse_plan(proposal.plan, proposal.contract)[-1].op == "finalize"


def test_nested_json_strings_are_decoded():
    contract = Contract.model_validate(
        {
            "extract": json.dumps(CONTRACT["extract"]),
            "reduce": json.dumps(CONTRACT["reduce"]),
            "routing": json.dumps(CONTRACT["routing"]),
        }
    )
    assert contract.reduce.instructions == "Write topic pages."
    assert isinstance(contract.routing, Routing)
    assert contract.routing.instructions == "Group records by topic."


def test_review_decision_accepts_contract_json_string():
    decision = ReviewDecision.model_validate(
        {"action": "revise", "contract": json.dumps(CONTRACT), "plan": "p.finalize(x, into=target)"}
    )
    assert decision.contract.extract.input_unit == "file"


def test_unstructured_routing_is_rejected():
    with pytest.raises(ValidationError):
        Contract.model_validate({**CONTRACT, "routing": "Group by topic."})


def test_invalid_contract_string_still_fails():
    with pytest.raises(ValidationError):
        PlanProposal.model_validate({"contract": "{not json"})
