"""Module 7 — Referral Partner Portal scheduled job (Arq).

`check_commission_triggers` reads Module 6C's `application_workflows` read-only — the
same "scan an existing, already-written collection" idiom as 6D's `check_re_eligible_
cases` (no live hook into a frozen module). It re-scans every case currently sitting in
a terminal "success" status each run rather than tracking a checkpoint — safe because
`CommissionEntryRepository.find_existing_for_case` (backed by a unique index on
`case_id`) makes entry creation idempotent, the same trade-off `check_re_eligible_cases`
already makes for its own daily rejected-case scan.
"""

from typing import Any

from app.config.database import get_database
from app.features.referral_partner_management.service import ReferralPartnerManagementService
from app.features.workflow_engine.constants import CaseType, InsuranceStatus, LoanStatus
from app.features.workflow_engine.repository import ApplicationWorkflowRepository


async def check_commission_triggers(_ctx: dict[Any, Any], *_args: Any, **_kwargs: Any) -> Any:
    db = get_database()
    workflows = ApplicationWorkflowRepository(db)
    service = ReferralPartnerManagementService(db)  # no OTP/invite path is exercised by this job, so no Redis client is needed

    for case_type, status in ((CaseType.LOAN, LoanStatus.DISBURSED), (CaseType.INSURANCE, InsuranceStatus.POLICY_ISSUED)):
        cases, _total = await workflows.search_and_filter(
            case_type=case_type, search=None, customer_id=None, assigned_to=None, unassigned_only=False,
            status=status, skip=0, limit=1000, sort=None,
        )
        for case in cases:
            await service.create_commission_entry_if_applicable(case)
