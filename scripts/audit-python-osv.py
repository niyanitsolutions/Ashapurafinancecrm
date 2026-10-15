"""Read installed public package versions and query OSV; never installs/upgrades.

Documented API: https://google.github.io/osv.dev/post-v1-querybatch/
Direct-URL/editable distributions are excluded, not reported as vulnerability-free.
Run with the backend virtualenv Python to audit that exact environment.
"""

import importlib.metadata
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

packages = []
excluded = []
for distribution in importlib.metadata.distributions():
    name = distribution.metadata.get("Name")
    if not name:
        continue
    if distribution.read_text("direct_url.json"):
        excluded.append(name)
        continue
    packages.append({"name": name, "version": distribution.version})
packages.sort(key=lambda item: item["name"].casefold())
findings = {index: set() for index in range(len(packages))}
pending = [(index, {"package": {"name": package["name"], "ecosystem": "PyPI"}, "version": package["version"]}) for index, package in enumerate(packages)]
if "--preview" in sys.argv:
    Path("docs/VOICE_PYTHON_ADVISORY_REQUEST.json").write_text(json.dumps({"queries": [query for _, query in pending]}, indent=2))
    print(f"Prepared {len(packages)} public package/version queries locally. No network request was sent. Destination if approved: https://api.osv.dev/v1/querybatch")
    sys.exit(0)
try:
    for _ in range(10):
        if not pending:
            break
        request = urllib.request.Request("https://api.osv.dev/v1/querybatch", data=json.dumps({"queries": [query for _, query in pending]}).encode(), headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = response.read(4 * 1024 * 1024 + 1)
        if len(payload) > 4 * 1024 * 1024:
            raise ValueError("Audit response exceeds the bound")
        results = json.loads(payload)["results"]
        follow_up = []
        for (index, query), result in zip(pending, results, strict=True):
            findings[index].update(vulnerability["id"] for vulnerability in result.get("vulns", []))
            if result.get("next_page_token"):
                follow_up.append((index, {**query, "page_token": result["next_page_token"]}))
        pending = follow_up
    if pending:
        raise ValueError("Audit pagination incomplete")
except (OSError, urllib.error.URLError, ValueError, KeyError, TypeError):
    print("Python advisory audit did not complete; no successful audit result is claimed.")
    sys.exit(2)

affected = [{**package, "advisory_ids": sorted(findings[index])} for index, package in enumerate(packages) if findings[index]]
report = {"source": "OSV documented querybatch API", "complete_for_queried_packages": True, "packages_queried": len(packages), "excluded_direct_url_packages": excluded, "affected": affected, "scope": "installed backend virtualenv, including dev dependencies; matching advisory IDs are not application exploitability findings"}
Path("docs/VOICE_PYTHON_ADVISORY_AUDIT.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report))
sys.exit(1 if affected else 0)
