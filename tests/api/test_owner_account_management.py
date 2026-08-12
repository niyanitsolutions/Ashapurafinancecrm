"""Owner Account Management (Primary + Secondary Owner) — covers the required test
scenarios: Primary Owner creating/managing Secondary Owners, Secondary Owner security
boundaries (cannot manage Owners), password lifecycle, deactivation, and backward
compatibility with existing Employee/Owner login flows.
"""

from app.constants.roles import EMPLOYEE
from app.features.auth.models import ACCOUNT_STATUS_ACTIVE, User
from app.security.password import hash_password

PRIMARY_MOBILE = "9111111111"
PRIMARY_PASSWORD = "PrimaryPass1!"
SECONDARY_MOBILE = "9222222222"
SECONDARY_INITIAL_PASSWORD = "SecondaryPass1!"
SECONDARY_NEW_PASSWORD = "SecondaryPass2!"


async def _register_primary_owner(client) -> dict:
    payload = {
        "company_name": "Test Co",
        "owner_name": "Primary Owner",
        "mobile": PRIMARY_MOBILE,
        "email": "primary@example.com",
        "password": PRIMARY_PASSWORD,
        "accept_terms": True,
    }
    r = await client.post("/api/v1/owner/register", json=payload)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    return {"Authorization": f"Bearer {data['access_token']}"}


async def _create_secondary_owner(client, primary_headers, *, mobile=SECONDARY_MOBILE, email="secondary@example.com") -> dict:
    r = await client.post(
        "/api/v1/owner/accounts",
        json={"full_name": "Secondary Owner", "mobile": mobile, "email": email, "initial_password": SECONDARY_INITIAL_PASSWORD},
        headers=primary_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _login(client, mobile: str, password: str):
    return await client.post("/api/v1/auth/login", json={"mobile": mobile, "password": password})


# ---------------------------------------------------------------------- TEST 1: Primary Owner flow


async def test_primary_owner_creates_secondary_owner_who_appears_in_list_and_can_log_in(client):
    primary_headers = await _register_primary_owner(client)

    r = await client.get("/api/v1/owner/me", headers=primary_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["owner_type"] == "primary"

    secondary = await _create_secondary_owner(client, primary_headers)
    assert secondary["owner_type"] == "secondary"
    assert secondary["status"] == "active"

    r = await client.get("/api/v1/owner/accounts", headers=primary_headers)
    assert r.status_code == 200, r.text
    by_mobile = {o["mobile"]: o["owner_type"] for o in r.json()["data"]}
    assert by_mobile[PRIMARY_MOBILE] == "primary"
    assert by_mobile[SECONDARY_MOBILE] == "secondary"

    r = await _login(client, SECONDARY_MOBILE, SECONDARY_INITIAL_PASSWORD)
    assert r.status_code == 200, r.text
    login_data = r.json()["data"]
    assert login_data["role"] == "owner"
    assert login_data["must_change_password"] is True


async def test_secondary_owner_can_create_employee_and_referral_partner(client, master_data):
    primary_headers = await _register_primary_owner(client)
    secondary = await _create_secondary_owner(client, primary_headers)
    r = await _login(client, SECONDARY_MOBILE, SECONDARY_INITIAL_PASSWORD)
    secondary_headers = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

    r = await client.post(
        "/api/v1/employees",
        json={
            "mobile": "9333333333", "initial_password": "EmployeePass1!", "first_name": "Jane", "last_name": "Doe",
            "email": "jane@example.com", "department_id": master_data["department_id"],
            "designation_id": master_data["designation_id"], "branch_id": master_data["branch_id"],
            "joining_date": "2026-01-01", "employment_type": "full_time",
        },
        headers=secondary_headers,
    )
    assert r.status_code == 200, r.text

    r = await client.post(
        "/api/v1/referral-partners",
        json={"full_name": "Partner One", "mobile": "9444444444", "email": "partner@example.com"},
        headers=secondary_headers,
    )
    assert r.status_code == 200, r.text
    assert secondary["owner_type"] == "secondary"


# ---------------------------------------------------------------------- TEST 2: Secondary Owner security


async def test_secondary_owner_cannot_create_another_secondary_owner(client):
    primary_headers = await _register_primary_owner(client)
    await _create_secondary_owner(client, primary_headers)
    r = await _login(client, SECONDARY_MOBILE, SECONDARY_INITIAL_PASSWORD)
    secondary_headers = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

    r = await client.post(
        "/api/v1/owner/accounts",
        json={"full_name": "Another Owner", "mobile": "9555555555", "email": "another@example.com", "initial_password": "AnotherPass1!"},
        headers=secondary_headers,
    )
    assert r.status_code == 403, r.text


async def test_secondary_owner_cannot_edit_or_deactivate_primary_owner(client):
    primary_headers = await _register_primary_owner(client)
    await _create_secondary_owner(client, primary_headers)
    r = await _login(client, SECONDARY_MOBILE, SECONDARY_INITIAL_PASSWORD)
    secondary_headers = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

    primary_profile = (await client.get("/api/v1/owner/me", headers=primary_headers)).json()["data"]
    primary_id = primary_profile["id"]

    r = await client.patch(f"/api/v1/owner/accounts/{primary_id}", json={"full_name": "Hacked"}, headers=secondary_headers)
    assert r.status_code == 403, r.text

    r = await client.patch(f"/api/v1/owner/accounts/{primary_id}/deactivate", headers=secondary_headers)
    assert r.status_code == 403, r.text

    r = await client.get("/api/v1/owner/accounts", headers=secondary_headers)
    assert r.status_code == 403, r.text


async def test_primary_owner_cannot_deactivate_self_via_secondary_owner_action(client):
    primary_headers = await _register_primary_owner(client)
    primary_profile = (await client.get("/api/v1/owner/me", headers=primary_headers)).json()["data"]

    r = await client.patch(f"/api/v1/owner/accounts/{primary_profile['id']}/deactivate", headers=primary_headers)
    assert r.status_code == 403, r.text


async def test_employee_cannot_create_owner_account(client, master_data):
    primary_headers = await _register_primary_owner(client)
    r = await client.post(
        "/api/v1/employees",
        json={
            "mobile": "9666666666", "initial_password": "EmployeePass1!", "first_name": "Sam", "last_name": "Lee",
            "email": "sam@example.com", "department_id": master_data["department_id"],
            "designation_id": master_data["designation_id"], "branch_id": master_data["branch_id"],
            "joining_date": "2026-01-01", "employment_type": "full_time",
        },
        headers=primary_headers,
    )
    assert r.status_code == 200, r.text
    r = await _login(client, "9666666666", "EmployeePass1!")
    employee_headers = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

    r = await client.post(
        "/api/v1/owner/accounts",
        json={"full_name": "Sneaky Owner", "mobile": "9777777777", "email": "sneaky@example.com", "initial_password": "SneakyPass1!"},
        headers=employee_headers,
    )
    assert r.status_code == 403, r.text


async def test_unauthenticated_request_cannot_create_owner_account(client):
    await _register_primary_owner(client)
    r = await client.post(
        "/api/v1/owner/accounts",
        json={"full_name": "Ghost", "mobile": "9888888888", "email": "ghost@example.com", "initial_password": "GhostPass1!"},
    )
    assert r.status_code == 401, r.text


# ---------------------------------------------------------------------- TEST 3: password lifecycle


async def test_secondary_owner_password_change_invalidates_old_password(client):
    primary_headers = await _register_primary_owner(client)
    await _create_secondary_owner(client, primary_headers)

    r = await _login(client, SECONDARY_MOBILE, SECONDARY_INITIAL_PASSWORD)
    assert r.status_code == 200, r.text
    secondary_headers = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

    r = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": SECONDARY_INITIAL_PASSWORD, "new_password": SECONDARY_NEW_PASSWORD},
        headers=secondary_headers,
    )
    assert r.status_code == 200, r.text

    r = await _login(client, SECONDARY_MOBILE, SECONDARY_INITIAL_PASSWORD)
    assert r.status_code != 200

    r = await _login(client, SECONDARY_MOBILE, SECONDARY_NEW_PASSWORD)
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------- TEST 4: deactivation


async def test_primary_owner_deactivates_secondary_owner_blocks_login(client):
    primary_headers = await _register_primary_owner(client)
    secondary = await _create_secondary_owner(client, primary_headers)

    r = await client.patch(f"/api/v1/owner/accounts/{secondary['id']}/deactivate", headers=primary_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "inactive"

    r = await _login(client, SECONDARY_MOBILE, SECONDARY_INITIAL_PASSWORD)
    assert r.status_code != 200

    r = await client.patch(f"/api/v1/owner/accounts/{secondary['id']}/activate", headers=primary_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "active"

    r = await _login(client, SECONDARY_MOBILE, SECONDARY_INITIAL_PASSWORD)
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------- TEST 5/6: data integrity / backward compat


async def test_cannot_register_a_second_primary_owner(client):
    await _register_primary_owner(client)
    r = await client.post(
        "/api/v1/owner/register",
        json={
            "company_name": "Other Co", "owner_name": "Other Owner", "mobile": "9999999999",
            "email": "other@example.com", "password": "OtherPass1!", "accept_terms": True,
        },
    )
    assert r.status_code == 409, r.text


async def test_secondary_owner_duplicate_mobile_and_email_rejected(client):
    primary_headers = await _register_primary_owner(client)
    await _create_secondary_owner(client, primary_headers)

    r = await client.post(
        "/api/v1/owner/accounts",
        json={"full_name": "Dup Mobile", "mobile": SECONDARY_MOBILE, "email": "unique@example.com", "initial_password": "DupPass1!"},
        headers=primary_headers,
    )
    assert r.status_code == 409, r.text

    r = await client.post(
        "/api/v1/owner/accounts",
        json={"full_name": "Dup Email", "mobile": "9000000009", "email": "secondary@example.com", "initial_password": "DupPass1!"},
        headers=primary_headers,
    )
    assert r.status_code == 409, r.text


async def test_legacy_owner_with_no_profile_row_is_treated_as_primary(client, mock_db):
    """Regression test for the pre-Owner-Account-Management bootstrap path (a bare
    `users` insert with no owner_profiles row — see the old scripts/seed.py behavior).
    Such an Owner must still be recognized as Primary, not locked out."""
    user = User(mobile=PRIMARY_MOBILE, role="owner", status=ACCOUNT_STATUS_ACTIVE, password_hash=hash_password(PRIMARY_PASSWORD))
    await mock_db["users"].insert_one(user.model_dump(by_alias=True, exclude={"id"}))
    r = await _login(client, PRIMARY_MOBILE, PRIMARY_PASSWORD)
    assert r.status_code == 200, r.text
    legacy_headers = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

    r = await client.get("/api/v1/owner/me", headers=legacy_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["owner_type"] == "primary"

    secondary = await _create_secondary_owner(client, legacy_headers)
    assert secondary["owner_type"] == "secondary"


async def test_existing_employee_login_still_works_after_owner_module_changes(client, master_data):
    primary_headers = await _register_primary_owner(client)
    r = await client.post(
        "/api/v1/employees",
        json={
            "mobile": "9123456780", "initial_password": "EmployeePass1!", "first_name": "Ann", "last_name": "Lee",
            "email": "ann@example.com", "department_id": master_data["department_id"],
            "designation_id": master_data["designation_id"], "branch_id": master_data["branch_id"],
            "joining_date": "2026-01-01", "employment_type": "full_time",
        },
        headers=primary_headers,
    )
    assert r.status_code == 200, r.text
    r = await _login(client, "9123456780", "EmployeePass1!")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["role"] == EMPLOYEE
