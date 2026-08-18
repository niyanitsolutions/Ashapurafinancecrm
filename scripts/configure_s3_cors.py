"""Apply the S3 bucket CORS configuration the Customer Portal document upload flow needs.

Root cause of the production "Document upload failed" / browser CORS error: the presigned
PUT URL (app/services/storage/client.py:generate_presigned_upload_url) and the frontend's
direct-to-S3 PUT (features/customer/api.ts:putFileToStorage) are both correct — but the S3
BUCKET itself has never had a CORS configuration applied. FastAPI's own CORSMiddleware
(app/middleware/cors.py) only governs this API's own responses; it has zero effect on the
bucket the browser's PUT talks to directly, so the preflight OPTIONS request S3 receives
has nothing to match against and returns 403. This is a bucket-level AWS configuration
change, not an application bug — no code path can work around it, and none of this
project's other config (Terraform, CloudFormation, docker/) provisions it either, which is
why it was missed.

This script is the one place that CORS policy is defined, kept in sync with the exact
origins/methods/headers the real upload flow uses:
  - AllowedOrigins: `Settings.cors_origin_list` (the SAME origin list that already gates
    the API's own CORS) — the production frontend origin only needs to be set once, not
    duplicated into a second S3-specific env var.
  - AllowedMethods: GET (presigned document download), PUT (presigned document upload),
    HEAD. Never POST/DELETE — this app only ever mints presigned GET/PUT URLs
    (app/services/storage/client.py has no presigned POST-policy or DELETE helper).
  - AllowedHeaders: Content-Type only — the only header the frontend's PUT ever sends
    (features/customer/api.ts), and the only one `generate_presigned_upload_url` signs.
  - ExposeHeaders: none — the frontend only ever checks `response.ok`/status, never reads
    a response header back from S3, so nothing needs exposing (least-privilege CORS per
    the fix's own requirements).

Safe/idempotent: defaults to printing the policy that WOULD be applied (dry run) and
diffing it against whatever is on the bucket today; only writes when passed --apply. Never
touches bucket policy, IAM, object ACLs, or object contents — CORS is the one and only
thing this script changes.

Run from repo root, with real production AWS credentials in the environment/.env:
  python scripts/configure_s3_cors.py            # dry run — prints current vs desired
  python scripts/configure_s3_cors.py --apply     # actually applies the desired policy
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from botocore.exceptions import ClientError

from app.config.settings import get_settings
from app.services.storage.client import get_s3_client

ALLOWED_METHODS = ["GET", "PUT", "HEAD"]
ALLOWED_HEADERS = ["Content-Type"]
EXPOSE_HEADERS: list[str] = []
MAX_AGE_SECONDS = 3000


def build_desired_cors(origins: list[str]) -> dict[str, list[dict[str, object]]]:
    return {
        "CORSRules": [
            {
                "AllowedOrigins": origins,
                "AllowedMethods": ALLOWED_METHODS,
                "AllowedHeaders": ALLOWED_HEADERS,
                "ExposeHeaders": EXPOSE_HEADERS,
                "MaxAgeSeconds": MAX_AGE_SECONDS,
            }
        ]
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Actually write the CORS policy to the bucket (default: dry run/print only).")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.s3_bucket_name:
        raise SystemExit("S3_BUCKET_NAME is not set — refusing to guess a bucket to configure.")
    origins = settings.cors_origin_list
    if not origins:
        raise SystemExit("CORS_ORIGINS is empty — refusing to apply a CORS policy with no allowed origins.")
    if any(o == "*" for o in origins):
        raise SystemExit("CORS_ORIGINS contains '*' — refusing to configure the bucket with a wildcard origin. Set it to the exact production frontend origin(s).")

    desired = build_desired_cors(origins)
    client = get_s3_client()

    print(f"Bucket:  {settings.s3_bucket_name}")
    print(f"Region:  {settings.aws_region}")
    print(f"Origins: {origins}")

    try:
        current = client.get_bucket_cors(Bucket=settings.s3_bucket_name)
        current_rules = current.get("CORSRules", [])
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "NoSuchCORSConfiguration":
            current_rules = []
        else:
            raise

    print("\nCurrent CORS rules on the bucket:")
    print(json.dumps(current_rules, indent=2) if current_rules else "  (none — this is the production bug's root cause)")

    print("\nDesired CORS configuration:")
    print(json.dumps(desired["CORSRules"], indent=2))

    if not args.apply:
        print("\nDry run only — no changes made. Re-run with --apply to write this policy to the bucket.")
        return

    client.put_bucket_cors(Bucket=settings.s3_bucket_name, CORSConfiguration=desired)
    print("\nApplied. Verifying...")
    verified = client.get_bucket_cors(Bucket=settings.s3_bucket_name)
    print(json.dumps(verified.get("CORSRules", []), indent=2))


if __name__ == "__main__":
    main()
