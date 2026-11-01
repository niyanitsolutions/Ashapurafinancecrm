"""Same-number revision lifecycle and immutable snapshots; uses existing invoice fixtures."""

import asyncio

import pymupdf
import pytest
from bson import ObjectId
from test_invoices import configure, create, grant_employee, sample


async def enable_policy(client, headers):
    config = (await client.get("/api/v1/invoice-settings", headers=headers)).json()[
        "data"
    ]["config"]
    config.update(
        same_number_reissue_enabled=True,
        same_number_policy_reason="Synthetic owner approval for permitted same-number corrections",
    )
    response = await client.put(
        "/api/v1/invoice-settings", headers=headers, json=config
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def issued(client, headers):
    await configure(client, headers)
    draft = await create(client, headers)
    response = await client.post(
        "/api/v1/invoices/" + draft["id"] + "/status",
        headers=headers,
        json={"status": "issued", "version": 1},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def proposal(version, name="Corrected Customer", rate="100"):
    data = sample()
    data["customer"]["name"] = name
    data["items"][0].update(quantity="2", rate=rate)
    data["version"] = version
    return {
        "version": version,
        "reason": "Correct customer and amount",
        "invoice": data,
    }


async def test_same_number_policy_disabled_and_owner_metadata(
    client, owner_headers, employee_headers, mock_db
):
    doc = await issued(client, owner_headers)
    url = "/api/v1/invoices/" + doc["id"]
    assert (
        await client.post(
            url + "/revision", headers=owner_headers, json=proposal(doc["version"])
        )
    ).status_code == 409
    config = await enable_policy(client, owner_headers)
    assert config["same_number_policy_approved_by"] == doc["created_by"]
    assert config["same_number_policy_approved_at"]
    forged = dict(
        config,
        same_number_policy_approved_by="forged",
        same_number_policy_approved_at="2000-01-01T00:00:00Z",
    )
    saved = (
        await client.put("/api/v1/invoice-settings", headers=owner_headers, json=forged)
    ).json()["data"]
    assert (
        saved["same_number_policy_approved_by"]
        == config["same_number_policy_approved_by"]
    )
    assert (
        saved["same_number_policy_approved_at"]
        == config["same_number_policy_approved_at"]
    )
    assert (
        await client.put(
            "/api/v1/invoice-settings", headers=employee_headers, json=config
        )
    ).status_code == 403
    assert (
        await client.post(
            url + "/revision",
            headers=owner_headers,
            json=dict(proposal(doc["version"]), reason=" "),
        )
    ).status_code == 422


async def test_multiple_reissues_same_identity_counter_and_original_pdf(
    client, owner_headers, mock_db
):
    doc = await issued(client, owner_headers)
    await enable_policy(client, owner_headers)
    url = "/api/v1/invoices/" + doc["id"]
    original_snapshot = (
        await client.get(url + "/revisions/1", headers=owner_headers)
    ).json()["data"]
    original_pdf = pymupdf.open(
        stream=(await client.get(url + "/pdf", headers=owner_headers)).content,
        filetype="pdf",
    )[0].get_text()
    counter = await mock_db.counters.find_one({"_id": "INV"})
    for revision in [2, 3]:
        current = (await client.get(url, headers=owner_headers)).json()["data"]
        response = await client.post(
            url + "/revision",
            headers=owner_headers,
            json=proposal(
                current["version"],
                name=f"Corrected Customer {revision}",
                rate=str(revision * 100),
            ),
        )
        assert response.status_code == 200, response.text
        pending = response.json()["data"]
        assert pending["grand_total"] == current["grand_total"]
        assert (
            pending["invoice_number"] == doc["invoice_number"]
            and pending["id"] == doc["id"]
        )
        response = await client.post(
            url + "/reissue",
            headers=owner_headers,
            json={
                "version": pending["version"],
                "proposal_id": pending["revision_proposal"]["id"],
                "approval_reason": "Reviewed and approved for this invoice",
            },
        )
        assert response.status_code == 200, response.text
        latest = response.json()["data"]
        assert (
            latest["id"] == doc["id"]
            and latest["invoice_number"] == doc["invoice_number"]
        )
        assert (
            latest["issued_at"] == doc["issued_at"]
            and latest["effective_revision"] == revision
        )
        assert latest["revision_proposal"] is None
        assert latest["customer"]["name"] == f"Corrected Customer {revision}"
    assert await mock_db.invoices.count_documents({}) == 1
    assert (await mock_db.counters.find_one({"_id": "INV"}))["seq"] == counter["seq"]
    assert (await client.get(url + "/revisions/1", headers=owner_headers)).json()[
        "data"
    ] == original_snapshot
    historical_pdf = pymupdf.open(
        stream=(
            await client.get(url + "/revisions/1/pdf", headers=owner_headers)
        ).content,
        filetype="pdf",
    )[0].get_text()
    assert historical_pdf == original_pdf
    current_pdf = pymupdf.open(
        stream=(await client.get(url + "/pdf", headers=owner_headers)).content,
        filetype="pdf",
    )[0].get_text()
    assert (
        "Corrected Customer 3" in current_pdf
        and "Corrected Customer 3" not in historical_pdf
    )
    records = (await client.get(url + "/revisions", headers=owner_headers)).json()[
        "data"
    ]
    assert [r["revision_number"] for r in records] == [1, 2, 3]
    assert [r["current"] for r in records] == [False, False, True]
    assert records[-1]["approved_by"] == doc["created_by"]
    assert (
        await client.get(url + "/revisions/99", headers=owner_headers)
    ).status_code == 404


async def test_pending_proposal_concurrency_stale_approval_and_policy_revocation(
    client, owner_headers
):
    doc = await issued(client, owner_headers)
    await enable_policy(client, owner_headers)
    url = "/api/v1/invoices/" + doc["id"]
    responses = await asyncio.gather(
        *(
            client.post(
                url + "/revision",
                headers=owner_headers,
                json=proposal(doc["version"], name=f"Concurrent {i}"),
            )
            for i in range(4)
        )
    )
    assert sum(r.status_code == 200 for r in responses) == 1
    assert sum(r.status_code == 409 for r in responses) == 3
    pending = next(r.json()["data"] for r in responses if r.status_code == 200)
    old_id = pending["revision_proposal"]["id"]
    newer = (
        await client.post(
            url + "/revision", headers=owner_headers, json=proposal(pending["version"])
        )
    ).json()["data"]
    assert (
        await client.post(
            url + "/reissue",
            headers=owner_headers,
            json={
                "version": newer["version"],
                "proposal_id": old_id,
                "approval_reason": "Reviewed",
            },
        )
    ).status_code == 409
    config = (
        await client.get("/api/v1/invoice-settings", headers=owner_headers)
    ).json()["data"]["config"]
    config["same_number_reissue_enabled"] = False
    assert (
        await client.put("/api/v1/invoice-settings", headers=owner_headers, json=config)
    ).status_code == 200
    assert (
        await client.post(
            url + "/reissue",
            headers=owner_headers,
            json={
                "version": newer["version"],
                "proposal_id": newer["revision_proposal"]["id"],
                "approval_reason": "Reviewed",
            },
        )
    ).status_code == 409
    assert (await client.get(url, headers=owner_headers)).json()["data"][
        "grand_total"
    ] == doc["grand_total"]


async def test_revision_security_archive_and_legacy_compatibility(
    client, owner_headers, employee_headers, mock_db
):
    doc = await issued(client, owner_headers)
    await enable_policy(client, owner_headers)
    url = "/api/v1/invoices/" + doc["id"]
    assert (
        await client.post(url + "/revision", json=proposal(doc["version"]))
    ).status_code == 401
    assert (
        await client.post(
            url + "/revision", headers=employee_headers, json=proposal(doc["version"])
        )
    ).status_code == 403
    assert (
        await client.post(
            url + "/reissue",
            headers=employee_headers,
            json={
                "version": doc["version"],
                "proposal_id": "fake",
                "approval_reason": "Unapproved",
            },
        )
    ).status_code == 403
    await grant_employee(mock_db, ["view", "create", "edit"])
    for suffix in ["/revisions", "/revisions/1", "/revisions/1/pdf"]:
        assert (
            await client.get(url + suffix, headers=employee_headers)
        ).status_code == 404
    assert (
        await client.post(
            url + "/revision", headers=employee_headers, json=proposal(doc["version"])
        )
    ).status_code == 404
    assert (
        await client.request(
            "DELETE", url, headers=owner_headers, json={"version": doc["version"]}
        )
    ).status_code == 409
    legacy = (
        await client.post(
            url + "/replacement",
            headers=owner_headers,
            json={
                "reason": "Legacy explicit workflow",
                "request_key": "legacy-compatibility-request-001",
            },
        )
    ).json()["data"]
    saved = await client.post(
        url + "/revision", headers=owner_headers, json=proposal(doc["version"])
    )
    assert saved.status_code == 200, saved.text
    doc = saved.json()["data"]
    assert (
        await client.get("/api/v1/invoices/" + legacy["id"], headers=owner_headers)
    ).status_code == 200
    before = (await mock_db.invoices.find_one({"_id": ObjectId(doc["id"])}))[
        "revisions"
    ]
    assert (
        await client.post(
            url + "/issued-delete",
            headers=employee_headers,
            json={"version": doc["version"], "reason": "Archive"},
        )
    ).status_code == 403
    response = await client.post(
        url + "/issued-delete",
        headers=owner_headers,
        json={
            "version": doc["version"],
            "reason": "Owner approved archive, no cancellation",
        },
    )
    assert response.status_code == 200, response.text
    archived = response.json()["data"]
    assert archived["status"] == "issued" and archived["is_archived"]
    assert (
        archived["revisions"]
        == (await client.get(url, headers=owner_headers)).json()["data"]["revisions"]
    )
    assert (await mock_db.invoices.find_one({"_id": ObjectId(doc["id"])}))[
        "revisions"
    ] == before
    assert (
        await client.get(url + "/revisions/1/pdf", headers=owner_headers)
    ).status_code == 200


@pytest.mark.parametrize("state", ["paid", "partially_paid"])
async def test_settled_revisions_blocked(client, owner_headers, state):
    doc = await issued(client, owner_headers)
    await enable_policy(client, owner_headers)
    url = "/api/v1/invoices/" + doc["id"]
    response = await client.post(
        url + "/status",
        headers=owner_headers,
        json={
            "version": doc["version"],
            "status": state,
            "reason": "Approved lifecycle transition",
        },
    )
    assert response.status_code == 200
    assert (
        await client.post(
            url + "/revision",
            headers=owner_headers,
            json=proposal(response.json()["data"]["version"]),
        )
    ).status_code == 409
    assert (
        await client.get(url + "/revisions/1/pdf", headers=owner_headers)
    ).status_code == 200


async def test_assigned_employee_can_propose_but_only_owner_can_approve_or_remove(
    client, owner_headers, employee_headers, mock_db
):
    await grant_employee(mock_db, ["view", "create", "edit"])
    await configure(client, owner_headers)
    await enable_policy(client, owner_headers)
    doc = await create(client, employee_headers)
    url = "/api/v1/invoices/" + doc["id"]
    response = await client.post(
        url + "/status",
        headers=employee_headers,
        json={"status": "issued", "version": 1},
    )
    assert response.status_code == 200
    issued_doc = response.json()["data"]
    request = await client.post(
        url + "/revision",
        headers=employee_headers,
        json=proposal(issued_doc["version"]),
    )
    assert request.status_code == 200, request.text
    pending = request.json()["data"]
    approval = {
        "version": pending["version"],
        "proposal_id": pending["revision_proposal"]["id"],
        "approval_reason": "Owner approval",
    }
    assert (
        await client.post(url + "/reissue", headers=employee_headers, json=approval)
    ).status_code == 403
    for action in ["archive", "issued-delete", "cancel"]:
        assert (
            await client.post(
                url + "/" + action,
                headers=employee_headers,
                json={
                    "version": pending["version"],
                    "reason": "Attempt without owner approval",
                },
            )
        ).status_code == 403
    assert (
        await client.post(
            url + "/reissue",
            headers=owner_headers,
            json=dict(approval, approval_reason=" "),
        )
    ).status_code == 422
    tampered = proposal(pending["version"])
    tampered["invoice"]["invoice_number"] = "FORGED-NUMBER"
    assert (
        await client.post(url + "/revision", headers=employee_headers, json=tampered)
    ).status_code == 422
    assert (
        await client.put(url, headers=employee_headers, json=sample())
    ).status_code == 409
    approved = await client.post(url + "/reissue", headers=owner_headers, json=approval)
    assert approved.status_code == 200, approved.text
    final = approved.json()["data"]
    assert final["revisions"][-1]["changed_by"] == doc["created_by"]
    assert final["revisions"][-1]["approved_by"] != doc["created_by"]
    assert final["invoice_number"] == doc["invoice_number"]


async def test_cancelled_invoice_reissued_same_number_preserves_cancellation_and_pdfs(
    client, owner_headers, mock_db
):
    doc = await issued(client, owner_headers)
    await enable_policy(client, owner_headers)
    url = "/api/v1/invoices/" + doc["id"]
    original = (await client.get(url + "/revisions/1", headers=owner_headers)).json()[
        "data"
    ]
    counter = await mock_db.counters.find_one({"_id": "INV"})
    cancelled = (
        await client.post(
            url + "/cancel",
            headers=owner_headers,
            json={"version": doc["version"], "reason": "Cancelled by mistake"},
        )
    ).json()["data"]
    cancelled_pdf = pymupdf.open(
        stream=(await client.get(url + "/pdf", headers=owner_headers)).content,
        filetype="pdf",
    )[0].get_text()
    assert "CANCELLED" in cancelled_pdf
    response = await client.post(
        url + "/revision",
        headers=owner_headers,
        json=proposal(cancelled["version"], name="Restored Customer"),
    )
    assert response.status_code == 200, response.text
    pending = response.json()["data"]
    assert (
        pending["status"] == "cancelled"
        and pending["revision_proposal"]["base_status"] == "cancelled"
    )
    response = await client.post(
        url + "/reissue",
        headers=owner_headers,
        json={
            "version": pending["version"],
            "proposal_id": pending["revision_proposal"]["id"],
            "approval_reason": "Owner approved accidental cancellation recovery",
        },
    )
    assert response.status_code == 200, response.text
    restored = response.json()["data"]
    assert (
        restored["id"] == doc["id"]
        and restored["invoice_number"] == doc["invoice_number"]
    )
    assert restored["status"] == "issued" and restored["reissued_at"]
    assert (
        restored["issued_at"] == doc["issued_at"]
        and restored["customer"]["name"] == "Restored Customer"
    )
    assert restored["cancellation_reason"] == "Cancelled by mistake"
    assert restored["revisions"][-1]["previous_status"] == "cancelled"
    assert (
        restored["revisions"][-1]["cancellation"]["cancelled_at"]
        == cancelled["cancelled_at"]
    )
    assert restored["revisions"][-1]["snapshot"]["status"] == "issued"
    assert (await client.get(url + "/revisions/1", headers=owner_headers)).json()[
        "data"
    ] == original
    current_pdf = pymupdf.open(
        stream=(await client.get(url + "/pdf", headers=owner_headers)).content,
        filetype="pdf",
    )[0].get_text()
    assert "Restored Customer" in current_pdf and "CANCELLED" not in current_pdf
    historical_pdf = pymupdf.open(
        stream=(
            await client.get(url + "/revisions/2/pdf", headers=owner_headers)
        ).content,
        filetype="pdf",
    )[0].get_text()
    assert "CANCELLED" not in historical_pdf
    history = (await client.get(url + "/history", headers=owner_headers)).json()["data"]
    assert any(
        e["action"] == "cancelled" and e["reason"] == "Cancelled by mistake"
        for e in history
    )
    assert any(
        e["action"] == "same_number_reissued"
        and e["previous_status"] == "cancelled"
        and e["new_status"] == "issued"
        for e in history
    )
    assert await mock_db.invoices.count_documents({}) == 1
    assert (await mock_db.counters.find_one({"_id": "INV"}))["seq"] == counter["seq"]
    assert (
        await client.post(
            url + "/reissue",
            headers=owner_headers,
            json={
                "version": pending["version"],
                "proposal_id": pending["revision_proposal"]["id"],
                "approval_reason": "Retry",
            },
        )
    ).status_code == 409


async def test_cancelled_reissue_keeps_policy_archive_and_settlement_guards(
    client, owner_headers, mock_db
):
    doc = await issued(client, owner_headers)
    url = "/api/v1/invoices/" + doc["id"]
    cancelled = (
        await client.post(
            url + "/cancel",
            headers=owner_headers,
            json={"version": doc["version"], "reason": "Mistake"},
        )
    ).json()["data"]
    assert (
        await client.post(
            url + "/revision",
            headers=owner_headers,
            json=proposal(cancelled["version"]),
        )
    ).status_code == 409
    await enable_policy(client, owner_headers)
    # Representative legacy cancellation of a previously settled invoice remains blocked.
    await mock_db.invoices.update_one(
        {"_id": ObjectId(doc["id"])},
        {
            "$push": {
                "history": {"action": "partially_paid", "new_status": "partially_paid"}
            }
        },
    )
    assert (
        await client.post(
            url + "/revision",
            headers=owner_headers,
            json=proposal(cancelled["version"]),
        )
    ).status_code == 409
    second = await create(client, owner_headers)
    second_url = "/api/v1/invoices/" + second["id"]
    draft_cancelled = (
        await client.post(
            second_url + "/cancel",
            headers=owner_headers,
            json={"version": 1, "reason": "Unissued draft"},
        )
    ).json()["data"]
    assert (
        await client.post(
            second_url + "/revision",
            headers=owner_headers,
            json=proposal(draft_cancelled["version"]),
        )
    ).status_code == 409
    third = await issued(client, owner_headers)
    third_url = "/api/v1/invoices/" + third["id"]
    # configure() defaults the policy off, so explicitly restore owner approval.
    await enable_policy(client, owner_headers)
    cancelled = (
        await client.post(
            third_url + "/cancel",
            headers=owner_headers,
            json={"version": third["version"], "reason": "Mistake"},
        )
    ).json()["data"]
    archived = (
        await client.post(
            third_url + "/archive",
            headers=owner_headers,
            json={"version": cancelled["version"], "reason": "Retain archive"},
        )
    ).json()["data"]
    assert (
        await client.post(
            third_url + "/revision",
            headers=owner_headers,
            json=proposal(archived["version"]),
        )
    ).status_code == 409


async def test_cancelled_invoice_requires_fresh_proposal_after_cancellation(
    client, owner_headers
):
    doc = await issued(client, owner_headers)
    await enable_policy(client, owner_headers)
    url = "/api/v1/invoices/" + doc["id"]
    pending = (
        await client.post(
            url + "/revision", headers=owner_headers, json=proposal(doc["version"])
        )
    ).json()["data"]
    cancelled = (
        await client.post(
            url + "/cancel",
            headers=owner_headers,
            json={
                "version": pending["version"],
                "reason": "Accidental cancellation after proposing",
            },
        )
    ).json()["data"]
    response = await client.post(
        url + "/reissue",
        headers=owner_headers,
        json={
            "version": cancelled["version"],
            "proposal_id": pending["revision_proposal"]["id"],
            "approval_reason": "Old proposal",
        },
    )
    assert response.status_code == 409
    assert "status changed" in response.json()["error"]["message"]
    assert (await client.get(url, headers=owner_headers)).json()["data"][
        "status"
    ] == "cancelled"


async def legacy_recovery_fixture(client, owner_headers):
    doc = await issued(client, owner_headers)
    await enable_policy(client, owner_headers)
    url = "/api/v1/invoices/" + doc["id"]
    cancelled = (
        await client.post(
            url + "/cancel",
            headers=owner_headers,
            json={"version": doc["version"], "reason": "Cancelled by mistake"},
        )
    ).json()["data"]
    legacy = (
        await client.post(
            url + "/replacement",
            headers=owner_headers,
            json={
                "reason": "Earlier numbered correction attempt",
                "request_key": "legacy-recovery-fixture-0001",
            },
        )
    ).json()["data"]
    return url, cancelled, legacy


async def test_save_with_legacy_draft_then_explicit_retirement_and_reissue(
    client, owner_headers, mock_db
):
    url, original, legacy = await legacy_recovery_fixture(client, owner_headers)
    counter = await mock_db.counters.find_one({"_id": "INV"})
    response = await client.post(
        url + "/revision",
        headers=owner_headers,
        json=proposal(original["version"], name="Corrected Company"),
    )
    assert response.status_code == 200, response.text
    pending = response.json()["data"]
    assert pending["status"] == "cancelled"
    context = (
        await client.get(url + "/revision-conflicts", headers=owner_headers)
    ).json()["data"]
    assert [d["id"] for d in context["drafts"]] == [legacy["id"]] and not context[
        "blockers"
    ]
    payload = {
        "version": pending["version"],
        "proposal_id": pending["revision_proposal"]["id"],
        "approval_reason": "Owner approves same-number correction",
    }
    response = await client.post(url + "/reissue", headers=owner_headers, json=payload)
    assert (
        response.status_code == 409
        and "Confirm retirement" in response.json()["error"]["message"]
    )
    assert (
        await client.get("/api/v1/invoices/" + legacy["id"], headers=owner_headers)
    ).json()["data"]["status"] == "draft"
    assert (
        await client.post(
            "/api/v1/invoices/" + legacy["id"] + "/status",
            headers=owner_headers,
            json={"version": 1, "status": "issued"},
        )
    ).status_code == 409
    changed_copy = await client.post(
        url + "/reissue",
        headers=owner_headers,
        json=dict(
            payload,
            retire_legacy_drafts=True,
            legacy_draft_versions={legacy["id"]: legacy["version"] + 1},
        ),
    )
    assert (
        changed_copy.status_code == 409
        and "drafts changed" in changed_copy.json()["error"]["message"]
    )
    response = await client.post(
        url + "/reissue",
        headers=owner_headers,
        json=dict(
            payload,
            retire_legacy_drafts=True,
            legacy_draft_versions={legacy["id"]: legacy["version"]},
        ),
    )
    assert response.status_code == 200, response.text
    restored = response.json()["data"]
    assert (
        restored["id"] == original["id"]
        and restored["invoice_number"] == original["invoice_number"]
    )
    assert (
        restored["status"] == "issued"
        and restored["customer"]["name"] == "Corrected Company"
    )
    retired = (
        await client.get("/api/v1/invoices/" + legacy["id"], headers=owner_headers)
    ).json()["data"]
    assert retired["status"] == "cancelled" and retired["is_archived"]
    assert retired["retired_for_revision_of"] == original["id"]
    for field in [
        "invoice_number",
        "items",
        "grand_total",
        "customer",
        "replacement_for",
    ]:
        assert retired[field] == legacy[field]
    assert retired["history"][-1]["action"] == "legacy_draft_retired"
    assert restored["revisions"][-1]["retired_legacy_drafts"][0]["id"] == legacy["id"]
    assert await mock_db.invoices.count_documents({}) == 2
    assert (await mock_db.counters.find_one({"_id": "INV"}))["seq"] == counter["seq"]
    assert (
        await client.get(url + "/revision-conflicts", headers=owner_headers)
    ).json()["data"] == {"drafts": [], "blockers": []}


async def test_issued_legacy_replacement_does_not_block_save_but_blocks_reissue(
    client, owner_headers
):
    url, original, legacy = await legacy_recovery_fixture(client, owner_headers)
    legacy_url = "/api/v1/invoices/" + legacy["id"]
    response = await client.post(
        legacy_url + "/status",
        headers=owner_headers,
        json={"version": 1, "status": "issued"},
    )
    assert response.status_code == 200, response.text
    frozen = (await client.get(legacy_url, headers=owner_headers)).json()["data"]
    pending = (
        await client.post(
            url + "/revision", headers=owner_headers, json=proposal(original["version"])
        )
    ).json()["data"]
    context = (
        await client.get(url + "/revision-conflicts", headers=owner_headers)
    ).json()["data"]
    assert context["blockers"][0]["invoice_number"] == legacy["invoice_number"]
    response = await client.post(
        url + "/reissue",
        headers=owner_headers,
        json={
            "version": pending["version"],
            "proposal_id": pending["revision_proposal"]["id"],
            "approval_reason": "Attempt approval",
            "retire_legacy_drafts": True,
        },
    )
    assert (
        response.status_code == 409
        and legacy["invoice_number"] in response.json()["error"]["message"]
    )
    assert (await client.get(legacy_url, headers=owner_headers)).json()[
        "data"
    ] == frozen
    assert (await client.get(url, headers=owner_headers)).json()["data"][
        "status"
    ] == "cancelled"


async def test_stale_approval_cannot_retire_legacy_draft_and_staff_cannot_resolve(
    client, owner_headers, employee_headers
):
    url, original, legacy = await legacy_recovery_fixture(client, owner_headers)
    pending = (
        await client.post(
            url + "/revision", headers=owner_headers, json=proposal(original["version"])
        )
    ).json()["data"]
    newer = await client.post(
        url + "/revision",
        headers=owner_headers,
        json=proposal(pending["version"], name="Newer edit"),
    )
    assert newer.status_code == 200
    response = await client.post(
        url + "/reissue",
        headers=owner_headers,
        json={
            "version": pending["version"],
            "proposal_id": pending["revision_proposal"]["id"],
            "approval_reason": "Outdated approval",
            "retire_legacy_drafts": True,
        },
    )
    assert response.status_code == 409
    assert (
        await client.get("/api/v1/invoices/" + legacy["id"], headers=owner_headers)
    ).json()["data"]["status"] == "draft"
    assert (
        await client.get(url + "/revision-conflicts", headers=employee_headers)
    ).status_code == 403
