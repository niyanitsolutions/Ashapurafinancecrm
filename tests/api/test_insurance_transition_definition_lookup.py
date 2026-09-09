"""Regression: the Insurance "Move to Policy Document" (and every other) transition must
work after the redesign was deployed via `migrate_redesign_insurance_pipeline.py`.

Root cause it guards: that migration wrote the brand-new `fresh_lead` / `policy_document`
/ ... `workflow_definitions` rows with a hand-built `$set` payload that omitted the
`is_deleted` field. `WorkflowDefinitionRepository.find_by_case_type_status` filters on
`is_deleted` (the codebase-wide soft-delete convention), so those rows were invisible and
`WorkflowEngine.get_definition` raised `NotFoundError` -> HTTP 404
("The requested resource could not be found.") on every transition.
"""

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from migrate_redesign_insurance_pipeline import _rewrite_definitions
from test_insurance_policy_leads import _case_for, _insurance_product_with_schema
from test_workflow import _seed_workflow_definitions, _submitted_application


async def _apply_pipeline_migration_definitions(mock_db) -> None:
    """Simulate a real deploy: drop the seeded insurance workflow-definition rows and let
    the redesign migration recreate them the way it does in production (`$set` upsert)."""
    await mock_db["workflow_definitions"].delete_many({"case_type": "insurance"})
    await _rewrite_definitions(mock_db)


async def test_move_to_policy_document_works_after_the_pipeline_migration(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    product = await _insurance_product_with_schema(mock_db, product_name="Family Health Plus", docs=["PAN"])
    _headers, application_id = await _submitted_application(client, mock_db, product, mobile="9640007001")
    case_id = await _case_for(client, owner_headers, application_id)

    await _apply_pipeline_migration_definitions(mock_db)

    r = await client.post(f"/api/v1/insurance-cases/{case_id}/move-to-policy-document", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "policy_document"

    # Existing audit/history behaviour preserved.
    timeline = (await client.get(f"/api/v1/insurance-cases/{case_id}/timeline", headers=owner_headers)).json()["data"]
    assert any(e.get("to_status") == "policy_document" for e in timeline)


async def test_migration_definition_rows_are_visible_to_the_repository_lookup(mock_db):
    """The direct unit-level check: every row the migration writes must be found by the
    same `is_deleted`-filtered query the engine uses at transition time."""
    from app.features.workflow_engine.repository import WorkflowDefinitionRepository

    await _rewrite_definitions(mock_db)
    repo = WorkflowDefinitionRepository(mock_db)
    for status in ("fresh_lead", "policy_document", "policy_login", "policy_issued", "re_eligible", "rejected", "on_hold"):
        assert await repo.find_by_case_type_status("insurance", status) is not None, status
