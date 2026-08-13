"""Read-only production diagnostic for "why can't the Primary Owner log in".

Connects using the SAME MONGO_URI/MONGO_DB_NAME the running application already uses
(whatever is set in the environment this script runs in — e.g. the actual AWS backend
host/container) and reports the facts needed to tell conditions A-L apart, without ever
printing a password or password hash. Makes NO writes to the database.

Usage (run on the same host/container that has the real production MONGO_URI configured):

    python scripts/diagnose_primary_owner.py --mobile 8431002626

Optional, only if you want to confirm a specific candidate password matches the stored
hash (never printed, never stored — checked in memory only for this one run):

    PRIMARY_OWNER_CANDIDATE_PASSWORD='...' python scripts/diagnose_primary_owner.py --mobile 8431002626

Run from backend/: python ../scripts/diagnose_primary_owner.py --mobile 8431002626
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config.database import get_database
from app.security.password import verify_password


def _looks_like_bcrypt_hash(value: str | None) -> bool:
    if not value:
        return False
    return value.startswith(("$2a$", "$2b$", "$2y$")) and len(value) == 60


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mobile", required=True, help="Mobile number to check, e.g. 8431002626")
    args = parser.parse_args()
    mobile = args.mobile.strip()

    db = get_database()
    users = db["users"]
    owner_profiles = db["owner_profiles"]

    print(f"Connected to database: {db.name!r}")
    print(f"Checking mobile: {mobile!r}\n")

    # ---------------------------------------------------------------- exact match
    user = await users.find_one({"mobile": mobile})

    if user is None:
        print("[A] No user with this exact mobile number exists.")

        # ---------------------------------------------------------------- format-mismatch probe
        # Catches condition E — e.g. a stored value with a country code prefix, spaces,
        # or dashes that would never exact-match a plain 10-digit lookup.
        digits_only = "".join(ch for ch in mobile if ch.isdigit())
        candidates = []
        async for doc in users.find({}, {"mobile": 1, "role": 1}):
            stored = str(doc.get("mobile", ""))
            if digits_only and digits_only in "".join(ch for ch in stored if ch.isdigit()):
                candidates.append((str(doc["_id"]), stored, doc.get("role")))
        if candidates:
            print(f"[E?] Found {len(candidates)} user(s) whose mobile digits contain {digits_only!r} but don't exact-match:")
            for uid, stored_mobile, role in candidates:
                print(f"      user_id={uid} mobile={stored_mobile!r} role={role!r}")
        else:
            print("     No user found even with a loose digit-substring search — this mobile number")
            print("     has never been inserted into this database at all. Most likely: the bootstrap")
            print("     was never run against THIS database (check condition J/K below too).")
    else:
        user_id = str(user["_id"])
        role = user.get("role")
        status = user.get("status")
        is_mobile_verified = user.get("is_mobile_verified")
        password_hash = user.get("password_hash")
        is_deleted = user.get("is_deleted", False)

        print(f"[user found] user_id={user_id}")
        print(f"  role                = {role!r}  {'OK' if role == 'owner' else '<-- NOT owner (condition D)'}")
        print(f"  status              = {status!r}  {'OK (active)' if status == 'active' else '<-- NOT active (condition I)'}")
        print(f"  is_mobile_verified  = {is_mobile_verified!r}")
        print(f"  is_deleted          = {is_deleted!r}  {'<-- soft-deleted!' if is_deleted else 'OK'}")
        print(f"  password_hash set   = {password_hash is not None}")
        if password_hash is not None:
            print(f"  password_hash looks like valid bcrypt = {_looks_like_bcrypt_hash(password_hash)}"
                  f"  {'' if _looks_like_bcrypt_hash(password_hash) else '<-- condition G (malformed hash)'}")
        else:
            print("  <-- no password_hash at all (condition G)")

        candidate = os.environ.get("PRIMARY_OWNER_CANDIDATE_PASSWORD")
        if candidate and password_hash:
            matches = verify_password(candidate, password_hash)
            print(f"  candidate password (from PRIMARY_OWNER_CANDIDATE_PASSWORD env var) matches stored hash: {matches}"
                  f"  {'' if matches else '<-- condition H'}")

        # ---------------------------------------------------------------- owner_profiles link
        profile = await owner_profiles.find_one({"user_id": user_id})
        if profile is None:
            print("\n[owner_profiles] NO matching document for this user_id (condition B).")
            print("  Backend note: require_primary_owner/get_own_account treat this as a legacy")
            print("  Primary Owner and grant Primary access anyway — login itself is unaffected by")
            print("  this gap, but Owner Management UI/list may not show this account correctly.")
        else:
            owner_type = profile.get("owner_type")
            profile_status = profile.get("status")
            print(f"\n[owner_profiles found] id={profile['_id']}")
            print(f"  owner_type = {owner_type!r}  {'OK' if owner_type == 'primary' else '<-- NOT primary (condition C)'}")
            print(f"  status     = {profile_status!r}")
            print(f"  full_name  = {profile.get('full_name')!r}")
            print(f"  email      = {profile.get('email')!r}")
            print(f"  mobile     = {profile.get('mobile')!r}  {'matches' if profile.get('mobile') == mobile else '<-- MISMATCH vs users.mobile'}")

    # ---------------------------------------------------------------- duplicate/other owners
    other_owners = [doc async for doc in users.find({"role": "owner"}, {"mobile": 1, "status": 1})]
    print(f"\n[all owner-role users in this database] count = {len(other_owners)}")
    for doc in other_owners:
        print(f"  user_id={doc['_id']} mobile={doc.get('mobile')!r} status={doc.get('status')!r}")
    if len(other_owners) == 0:
        print("  <-- Zero Owner accounts exist in this database at all. Strongly suggests the")
        print("      bootstrap script has never been run against this specific database")
        print("      (check condition J/K — is this backend actually pointed at the DB you think it is?).")

    print("\n[connection check] This script used MONGO_URI/MONGO_DB_NAME from its own environment.")
    print("  If this doesn't match what the running backend process uses, you're diagnosing the")
    print("  wrong database (condition J/K) — run this script ON the same host/container as the")
    print("  backend, or with the exact same env vars it's deployed with.")


if __name__ == "__main__":
    asyncio.run(main())
