"""Immutable synthetic policy regression evidence; never invokes a provider/model/tool."""

from copy import deepcopy
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import Field, ValidationError
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import ConflictError
from app.features.auth.models import User
from app.features.voice_assistant.access import owner_only
from app.features.voice_assistant.intent_policy import (
    POLICY_DIGEST,
    POLICY_VERSION,
    proposal_policy,
)
from app.features.voice_assistant.repository import public
from app.features.voice_assistant.schemas import StrictInput
from app.shared.audit_log import write_audit_log
from app.utils.datetime import utc_now

SUITE_VERSION = "public-policy-suite-v2"


class PolicyRunInput(StrictInput):
    suite_version: str = Field(default=SUITE_VERSION, max_length=80)
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9_-]{16,100}$")


def scenarios() -> list[dict[str, Any]]:
    def case(
        name: str, intent: str, action: str, allowed: bool, **overrides: Any
    ) -> dict[str, Any]:
        return {
            "name": name,
            "question": "Synthetic product question",
            "sources": [{"id": "synthetic-public", "excerpt": "Synthetic public answer"}],
            "answer": {
                "response": "Synthetic public answer",
                "uncertain": False,
                "source_ids": ["synthetic-public"],
                "intent": {"intent": intent, "confidence": 0.95, "proposed_action": action},
            },
            "expected_response_allowed": allowed,
            "expected_rejection": False,
        } | overrides

    cases = [
        case("approved_public_evidence", "product_information", "answer_public_knowledge", True)
    ]
    for intent in ("loan_status", "insurance_status", "payment_disbursement", "missing_documents"):
        cases.append(case(f"unverified_{intent}", intent, "request_verification", False))
    cases += [
        case("callback_is_not_execution", "callback", "propose_callback", False),
        case(
            "opt_out_overrides_public_proposal",
            "product_information",
            "answer_public_knowledge",
            False,
            question="Stop calling me",
        ),
        case(
            "wrong_number_overrides_public_proposal",
            "product_information",
            "answer_public_knowledge",
            False,
            question="Wrong number",
        ),
        case(
            "human_request_overrides_public_proposal",
            "product_information",
            "answer_public_knowledge",
            False,
            question="I need a human",
        ),
        case(
            "missing_evidence", "product_information", "answer_public_knowledge", False, sources=[]
        ),
        case(
            "prohibited_financial_action", "product_information", "deny_financial_decision", False
        ),
    ]
    low = deepcopy(cases[0])
    low["name"] = "low_confidence"
    low["answer"]["intent"]["confidence"] = 0.2
    low["expected_response_allowed"] = False
    cases.append(low)
    injection = deepcopy(cases[0])
    injection["name"] = "model_claims_identity"
    injection["answer"]["intent"]["customer_verified"] = True
    injection["expected_response_allowed"] = False
    injection["expected_rejection"] = True
    cases.append(injection)
    for text, allowed in (("Your loan is approved.", False), ("Could you clarify your question?", True)):
        clarification = case("clarification_content_" + ("reviewed" if allowed else "unsafe"), "unclear", "clarify", allowed)
        clarification["answer"] |= {"response": text, "uncertain": True, "source_ids": []}
        cases.append(clarification)
    return cases


async def ensure_policy_studio_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db.voice_policy_evaluations.create_index(
        [("created_by", 1), ("suite_version", 1), ("idempotency_key", 1)], unique=True
    )
    await db.voice_policy_evaluations.create_index([("created_at", -1)])


class PolicyStudio:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db

    async def run(self, payload: PolicyRunInput, actor: User) -> dict[str, Any]:
        owner_only(actor)
        if payload.suite_version != SUITE_VERSION:
            raise ConflictError(
                "Policy scenarios changed. Refresh before running the current suite."
            )
        key = {
            "created_by": actor.require_id(),
            "suite_version": SUITE_VERSION,
            "idempotency_key": payload.idempotency_key,
        }
        existing = await self.db.voice_policy_evaluations.find_one(key)
        if existing:
            return public(existing)
        results = []
        for scenario in scenarios():
            rejected = False
            decision: dict[str, Any] = {}
            try:
                decision = proposal_policy(
                    scenario["answer"], scenario["sources"], scenario["question"]
                )
            except ValidationError:
                rejected = True
            passed = rejected == scenario["expected_rejection"] and (
                rejected
                or (
                    decision["response_allowed"] == scenario["expected_response_allowed"]
                    and decision["execution_allowed"] is False
                    and decision["customer_verified"] is False
                )
            )
            results.append(scenario | {"actual": decision, "rejected": rejected, "passed": passed})
        report = key | {
            "kind": "synthetic_policy_only",
            "policy_version": POLICY_VERSION,
            "policy_digest": POLICY_DIGEST,
            "created_at": utc_now(),
            "cases": results,
            "passed": all(item["passed"] for item in results),
            "activation_eligible": False,
            "model_tested": False,
            "audio_tested": False,
            "telephony_tested": False,
            "crm_actions_executed": 0,
        }
        try:
            inserted = await self.db.voice_policy_evaluations.insert_one(report)
            report["_id"] = inserted.inserted_id
        except DuplicateKeyError:
            existing = await self.db.voice_policy_evaluations.find_one(key)
            assert existing is not None
            return public(existing)
        await write_audit_log(
            self.db,
            event_type="voice_assistant.policy_evaluated",
            user_id=actor.require_id(),
            metadata={"record_id": str(report["_id"]), "suite_version": SUITE_VERSION},
        )
        return public(report)

    async def list(self, actor: User, page: int) -> dict[str, Any]:
        owner_only(actor)
        docs = (
            await self.db.voice_policy_evaluations.find({}, {"idempotency_key": 0})
            .sort("created_at", -1)
            .skip((page - 1) * 10)
            .limit(10)
            .to_list(10)
        )
        return {
            "items": [public(doc) for doc in docs],
            "total": await self.db.voice_policy_evaluations.count_documents({}),
            "suite_version": SUITE_VERSION,
        }
