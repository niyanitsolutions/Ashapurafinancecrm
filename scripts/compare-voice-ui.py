"""Compare approved sidebar evidence; never rewrites screenshots or source images."""

import json
from pathlib import Path

from PIL import Image, ImageChops

root = Path("docs/screenshots/voice-upgrade")
before = json.loads((root / "before/evidence.json").read_text())
after = json.loads((root / "after/evidence.json").read_text())
results = []
for item in before:
    newer = next(row for row in after if row["name"] == item["name"] and row["width"] == item["width"])
    result = {"page": item["name"], "width": item["width"], "sidebar_metadata_equal": item["sidebar"] == newer["sidebar"]}
    if item["width"] == 1440:
        filename = f"{item['name']}-1440.png"
        a = Image.open(root / "before" / filename).convert("RGB").crop((0, 0, 280, 1000))
        b = Image.open(root / "after" / filename).convert("RGB").crop((0, 0, 280, 1000))
        result["sidebar_pixels_equal"] = ImageChops.difference(a, b).getbbox() is None
        result["changed_pixel_bounds"] = ImageChops.difference(a, b).getbbox()
    results.append(result)
(root / "sidebar-comparison.json").write_text(json.dumps(results, indent=2))
print(json.dumps(results))
if not all(row["sidebar_metadata_equal"] and row.get("sidebar_pixels_equal", True) for row in results):
    raise SystemExit("Sidebar changed; investigate before accepting visual refresh.")
