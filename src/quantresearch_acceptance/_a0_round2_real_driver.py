"""Driver: run a real, owner-authorized A0 second round against yosef-server's CPA.

Not a test module (no test_ functions). This is a one-shot script that makes a
real HTTP call to the user's own yosef-server CPA proxy (DeepSeek-V4.1-Flash),
reviews it against the real #443/#469/#470/round-1 evidence, and runs it
through run_a0_round_two exactly as any other caller would. The credential
(CPA's local bearer key) is read from CPA_LOCAL_KEY and never touches the
EngineAuthorization record or any published output.
"""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

from ._research_decision_test import _protocol, _question, _request, _run, _visibility
from .research_a0_round2 import ROUND2_DECLARATION_SCHEMA, run_a0_round_two
from .research_decision import DecisionLedger
from .research_exposure import ExposureLog

CPA_BASE_URL = "http://yosef-server:8317/v1/chat/completions"
CPA_MODEL = "deepseek-v4-1-flash"
CPA_KEY = os.environ["CPA_LOCAL_KEY"]  # never hardcode or default this credential here

REAL_SOURCE_ID = "a0-round1-real-study-20260918"
REAL_EVIDENCE_PATH = "docs/research/a0/a0_round1_real_study.json"


def _cpa_chat(prompt: str) -> dict[str, object]:
    body = json.dumps(
        {
            "model": CPA_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 400,
            "temperature": 0,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        CPA_BASE_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {CPA_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _build_declaration() -> dict[str, object]:
    real_root = Path(__file__).resolve().parents[2] / "apex-research"
    real_study = json.loads(
        (real_root / REAL_EVIDENCE_PATH).read_text(encoding="utf-8")
    )
    finding = real_study["research_finding"]["answer"]

    authorization = {
        "state": "authorized",
        "engine_ref": "yosef-server-cpa/deepseek-v4-1-flash",
        "transport": "real_process",
        "evidence_ref": "record:" + REAL_SOURCE_ID,
        "reason": (
            "owner explicitly authorized use of the user's own yosef-server CPA "
            "proxy with the deepseek-v4-1-flash model for A0 round-2, in chat, "
            "2026-09-18"
        ),
    }
    request = _request(
        approved_source_ids=[REAL_SOURCE_ID],
        question=_question(
            evidence_requirements=[REAL_SOURCE_ID],
            protocol=_protocol(),
        ),
        run=_run(),
    )
    declaration = {
        "schema": ROUND2_DECLARATION_SCHEMA,
        "knowledge_cutoff": "2026-09-18T00:00:00Z",
        "purpose": "research-brief",
        "consumer": "research-model",
        "required_closure": [REAL_SOURCE_ID],
        "optional_scope": [],
        "template_version": "template-v1",
        "model_version": "deepseek-v4-1-flash",
        "parameter_digest": "sha256:" + "0" * 64,
        "tool_input_version": "tool-input-v1",
        "allowed_actions": ["continue", "add_evidence", "stop"],
        "authorization": authorization,
        "decision_request": request,
        "envelope_request": _envelope(),
        "tool_return_request": None,
    }
    return declaration, finding


def _envelope() -> dict[str, object]:
    visibility = _visibility((REAL_SOURCE_ID,), authorized=True)
    visibility["stage"] = "final_envelope"
    visibility["context_material_ids"] = []
    return visibility


class RealCpaEngine:
    """A ResearchEngineSeam whose call_research_engine really reaches CPA."""

    def __init__(self) -> None:
        self.contexts: list[str] = []
        self.budgets: list[tuple[str, int]] = []
        self.runs: list[str] = []
        self.calls: list[dict[str, object]] = []
        self.raw_responses: list[dict[str, object]] = []

    def publish_context(self, record) -> str:
        identity = str(record["paginated_identity"])
        self.contexts.append(identity)
        return identity

    def reserve_budget(self, budget_id: str, units: int) -> str:
        self.budgets.append((budget_id, units))
        return f"reservation:{budget_id}"

    def execute_run(self, run_key: str, contract) -> str:
        self.runs.append(run_key)
        return f"run:{run_key}"

    def call_research_engine(self, request: dict[str, object]) -> str:
        self.calls.append(dict(request))
        prompt = (
            "This is an identity/idempotency ping for an A0 research-engine "
            "invocation, not a content request. Reply with exactly one word: ack."
        )
        raw = _cpa_chat(prompt)
        self.raw_responses.append(raw)
        return "invocation:" + str(raw.get("id", "unknown"))


def main() -> None:
    declaration, finding = _build_declaration()
    engine = RealCpaEngine()
    ledger = DecisionLedger()
    exposure = ExposureLog()

    review_prompt = (
        "You are reviewing round one of the A0 quantitative research study "
        "(first daily EMA Crossback, testing whether a volume-contraction "
        "filter adds value). This is the ONLY approved evidence you may cite; "
        "you may not invent or reference anything else:\n\n"
        f"{finding}\n\n"
        "Based only on this evidence, respond with a single JSON object with "
        "exactly these keys and nothing else:\n"
        '{"proposed_action": one of "continue"|"add_evidence"|"stop", '
        '"cited_source_ids": ["' + REAL_SOURCE_ID + '"] (only this id, or []), '
        '"proposed_step_ids": [], '
        '"assumptions": [a short string describing any assumption you relied on], '
        '"boundaries": [a short string describing the scope you are limiting your answer to]}\n'
        "Do not propose a new run, a new budget, or a new strategy -- if you "
        "believe more evidence is needed, use add_evidence, not continue."
    )
    raw_review = _cpa_chat(review_prompt)
    content = raw_review["choices"][0]["message"]["content"]
    print("=== raw model content ===")
    print(content)
    parsed = json.loads(content[content.index("{") : content.rindex("}") + 1])
    model_response = {
        "proposed_action": parsed["proposed_action"],
        "cited_source_ids": parsed.get("cited_source_ids", []),
        "proposed_step_ids": parsed.get("proposed_step_ids", []),
        "assumptions": parsed.get("assumptions", []),
        "boundaries": parsed.get("boundaries", []),
    }

    outcome = run_a0_round_two(
        declaration,
        ledger=ledger,
        exposure=exposure,
        engine=engine,
        model_response=model_response,
    )

    result = {
        "schema": "a0-round2-real-outcome.v1",
        "observed_at": "2026-09-18T16:00:00Z",
        "engine_calls": {
            "attempted": len(engine.calls),
            "raw_response_ids": [str(item.get("id")) for item in engine.raw_responses],
        },
        "review_call_response_id": raw_review.get("id"),
        "review_call_model": raw_review.get("model"),
        "review_call_usage": raw_review.get("usage"),
        "model_response": model_response,
        "outcome": {
            "delivery_state": outcome.delivery.state,
            "delivery_layer": outcome.delivery.layer,
            "proves_model_use": outcome.delivery.proves_model_use,
            "e02_status": outcome.delivery.e02_status,
            "review_verdict": outcome.review.verdict if outcome.review else None,
            "review_codes": list(outcome.review.codes) if outcome.review else None,
            "candidate_id": outcome.candidate_id,
            "no_candidate_reason": outcome.no_candidate_reason,
        },
    }
    out_path = (
        Path(__file__).resolve().parents[2]
        / "apex-research" / "docs" / "research" / "a0" / "a0_round2_real_outcome.json"
    )
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print("=== outcome ===")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("wrote", out_path)


if __name__ == "__main__":
    main()
