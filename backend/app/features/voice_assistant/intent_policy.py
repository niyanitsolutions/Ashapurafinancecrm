"""Typed model proposals are data, never authority to disclose or execute CRM tools."""

import hashlib
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

POLICY_VERSION = "public-conversation-v2"
POLICY_DIGEST = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
# Only these non-disclosing questions may bypass public factual evidence. A question
# mark or a model-selected intent alone does not make arbitrary content safe.
SAFE_CLARIFICATIONS = frozenset({
    "Could you clarify your question?",
    "Which product would you like general information about?",
    "Would you like to speak to a member of staff?",
})
Intent = Literal[
    "loan_status",
    "insurance_status",
    "product_information",
    "missing_documents",
    "callback",
    "human_request",
    "complaint",
    "wrong_number",
    "opt_out",
    "payment_disbursement",
    "unclear",
]
Action = Literal[
    "answer_public_knowledge",
    "clarify",
    "request_verification",
    "propose_callback",
    "request_human",
    "request_suppression",
    "deny_financial_decision",
]


class IntentProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: Intent
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    proposed_action: Action
    product_category: Literal["loan", "insurance"] | None = None
    requested_language: str | None = Field(default=None, pattern=r"^[a-z]{2}$")


def priority_signal(question: str) -> str | None:
    """Conservative additional safety signals, not a general language classifier."""
    text = question.casefold()
    if re.search(r"\b(stop calling|do not call|don't call|opt out|unsubscribe)\b", text):
        return "opt_out"
    if re.search(r"\b(wrong number|not the right person)\b", text):
        return "wrong_number"
    if re.search(r"\b(human|real person|speak to an? (agent|employee))\b", text):
        return "human_request"
    return None


def proposal_policy(
    answer: dict[str, Any], sources: list[dict[str, Any]], question: str
) -> dict[str, Any]:
    """No caller identity, permission, consent or emergency flag is model-controlled.

    The current console has no authenticated voice customer or tool execution.
    Consequently every action remains a non-executable proposal, even for staff.
    This validates structure/action eligibility; semantic factuality needs review.
    """
    signal = priority_signal(question)
    proposal = IntentProposal.model_validate(answer["intent"]) if answer.get("intent") else None
    intent = signal or (proposal.intent if proposal else "unclear")
    action = "clarify"
    reason = "unclassified_or_low_confidence"
    allowed = False
    if signal or intent in {"opt_out", "wrong_number", "human_request", "complaint"}:
        action = "request_suppression" if intent in {"opt_out", "wrong_number"} else "request_human"
        reason = "staff_review_required_no_live_action_available"
    elif proposal and proposal.confidence >= 0.8:
        expected = {
            "loan_status": "request_verification",
            "insurance_status": "request_verification",
            "payment_disbursement": "request_verification",
            "missing_documents": "request_verification",
            "callback": "propose_callback",
            "product_information": "answer_public_knowledge",
            "unclear": "clarify",
        }
        action = expected.get(intent, "clarify")
        reason = "trusted_voice_identity_and_scoped_tools_unimplemented"
        if proposal.proposed_action == "deny_financial_decision":
            action, reason = "deny_financial_decision", "financial_decisions_are_not_ai_actions"
        elif proposal.proposed_action != action:
            reason = "model_action_conflicts_with_server_policy"
        elif intent == "product_information":
            cited = answer.get("source_ids", [])
            available = {source["id"] for source in sources}
            allowed = bool(cited) and set(cited) <= available and not answer.get("uncertain", True)
            reason = (
                "public_evidence_only_semantic_review_required"
                if allowed
                else "approved_citations_required"
            )
            if allowed:
                # Numeric consistency is additional defense, not semantic entailment.
                def numbers(value: str) -> set[str]:
                    return {
                        token.replace(",", "")
                        for token in re.findall(r"\d+(?:[.,]\d+)*(?:%)?", value)
                    }

                evidence = " ".join(
                    str(source.get("excerpt", "")) for source in sources if source["id"] in cited
                )
                if not numbers(str(answer.get("response", ""))) <= numbers(evidence):
                    allowed, reason = False, "uncited_numeric_claim_requires_review"
            if allowed:
                # Until an independently accepted semantic validator exists, only
                # a complete reviewed excerpt establishes factual support. Valid
                # citation IDs, overlapping numbers and model confidence cannot
                # authorize paraphrased claims or omission of source qualifiers.
                response = " ".join(str(answer.get("response", "")).split())
                excerpts = {
                    " ".join(str(source.get("excerpt", "")).split())
                    for source in sources if source["id"] in cited
                }
                allowed = bool(response) and response in excerpts
                reason = (
                    "complete_approved_public_excerpt_only"
                    if allowed else "unsupported_public_content_requires_review"
                )
        elif intent == "unclear" and answer.get("uncertain"):
            allowed = answer.get("response") in SAFE_CLARIFICATIONS
            reason = (
                "clarification_only_no_business_action"
                if allowed else "unreviewed_clarification_content_withheld"
            )
        elif intent == "callback":
            reason = "explicit_time_confirmation_and_existing_callback_api_required"
    return {
        "policy_version": POLICY_VERSION,
        "policy_digest": POLICY_DIGEST,
        "intent": intent,
        "confidence": proposal.confidence if proposal else None,
        "next_action": action,
        "reason": reason,
        "response_allowed": allowed,
        "execution_allowed": False,
        "customer_verified": False,
        "financial_accuracy_verified": False,
        "live_delivery_verified": False,
    }
