import os

os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017/?replicaSet=rs0")
os.environ.setdefault("MONGO_DB_NAME", "afs_crm_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest-only-do-not-use-in-prod")
# generate_presigned_url is pure local URL-signing (no network call) but boto3 still
# validates the bucket name shape client-side, so it needs a syntactically valid value.
os.environ.setdefault("S3_BUCKET_NAME", "afs-crm-test-bucket")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test-access-key-id")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test-secret-access-key")

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.config.database import get_database
from app.config.redis import get_redis
from app.features.auth.indexes import ensure_auth_indexes
from app.features.auth.models import ACCOUNT_STATUS_ACTIVE, User
from app.features.employee.indexes import ensure_employee_indexes
from app.features.employee.models import Branch, Department, Designation
from app.main import create_app
from app.security.password import hash_password


@pytest.fixture
def mock_db():
    # tz_aware=True matches the real client (app/config/database.py:get_client()) —
    # verified mongomock_motor honors this identically, decoding stored datetimes as
    # tz-aware UTC instead of naive.
    return AsyncMongoMockClient(tz_aware=True)["afs_crm_test"]


@pytest.fixture
def mock_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture(autouse=True)
def _stub_document_object_size(monkeypatch):
    # `CustomerService.confirm_document` HEADs the uploaded object in S3 to enforce a
    # Product Schema's `max_size_mb` for real (see docs on that method) — the one place
    # in the document-upload flow that would otherwise make a genuine network call, unlike
    # `generate_presigned_url` (pure local signing). Stubbed to a small, well-under-any-
    # schema-limit default so the existing "no real AWS calls in the test suite"
    # invariant holds; a test that specifically exercises the oversized-file rejection
    # path overrides this with its own `monkeypatch.setattr(customer_service, "get_object_size", ...)`.
    from app.features.customer import service as customer_service

    monkeypatch.setattr(customer_service, "get_object_size", lambda key: 1024)


@pytest.fixture
async def client(mock_db, mock_redis):
    await ensure_auth_indexes(mock_db)
    await ensure_employee_indexes(mock_db)
    app = create_app()
    app.dependency_overrides[get_database] = lambda: mock_db
    app.dependency_overrides[get_redis] = lambda: mock_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _seed_staff_user(mock_db, client, *, mobile: str, role: str, password: str) -> dict:
    """Inserts a pre-provisioned Owner/Employee (no signup path exists for these roles —
    see docs/decisions/DECISIONS.md #007) and logs in via the real API to get a bearer
    token, for tests that need to act as an authenticated inviter.
    """
    user = User(mobile=mobile, role=role, status=ACCOUNT_STATUS_ACTIVE, password_hash=hash_password(password))
    await mock_db["users"].insert_one(user.model_dump(by_alias=True, exclude={"id"}))
    r = await client.post("/api/v1/auth/login", json={"mobile": mobile, "password": password})
    assert r.status_code == 200, r.text
    token = r.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def owner_headers(mock_db, client):
    return await _seed_staff_user(mock_db, client, mobile="9000000001", role="owner", password="OwnerPass1!")


@pytest.fixture
async def employee_headers(mock_db, client):
    return await _seed_staff_user(mock_db, client, mobile="9000000002", role="employee", password="EmployeePass1!")


@pytest.fixture
async def master_data(mock_db) -> dict:
    department = Department(name="Loan")
    designation = Designation(name="Executive")
    branch = Branch(name="Head Office", code="HO")

    dept_id = (await mock_db["departments"].insert_one(department.model_dump(by_alias=True, exclude={"id"}))).inserted_id
    desig_id = (await mock_db["designations"].insert_one(designation.model_dump(by_alias=True, exclude={"id"}))).inserted_id
    branch_id = (await mock_db["branches"].insert_one(branch.model_dump(by_alias=True, exclude={"id"}))).inserted_id

    return {"department_id": str(dept_id), "designation_id": str(desig_id), "branch_id": str(branch_id)}
