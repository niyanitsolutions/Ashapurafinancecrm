"""Compare the unchanged sidebar in two synthetic desktop captures, read-only."""

import json
import sys
from pathlib import Path

from PIL import Image, ImageChops

root = Path(__file__).resolve().parents[1] / "docs" / "screenshots"
if sys.argv[1:] == ["--integration"]:
    results = []
    for name, baseline_path in (
        ("callback-time", root / "voice-callbacks-2026-10-16" / "lead-callbacks-1440.png"),
        ("policy-studio", root / "voice-platform-2026-10-16" / "platform-settings-1440.png"),
    ):
        current_path = root / "voice-integration-2026-10-17" / f"{name}-1440.png"
        with Image.open(baseline_path) as before, Image.open(current_path) as after:
            difference = ImageChops.difference(before.convert("RGB").crop((0, 0, 280, 1000)), after.convert("RGB").crop((0, 0, 280, 1000)))
            results.append({"synthetic": True, "name": name, "sidebar_pixels_equal": difference.getbbox() is None, "changed_pixel_bounds": difference.getbbox()})
    (current_path.parent / "sidebar-comparison.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results))
    raise SystemExit(0)
if sys.argv[1:]:
    raise SystemExit("Use no arguments for historical callback comparison, or --integration.")
baseline = root / "voice-upgrade" / "after" / "leads-1440.png"
current = root / "voice-callbacks-2026-10-16" / "lead-callbacks-1440.png"
with Image.open(baseline) as before, Image.open(current) as after:
    difference = ImageChops.difference(
        before.convert("RGB").crop((0, 0, 280, 1000)),
        after.convert("RGB").crop((0, 0, 280, 1000)),
    )
    result = {
        "synthetic": True,
        "comparison": "Prior Lead list versus current Lead detail, original desktop sidebar",
        "changed_pixel_bounds": difference.getbbox(),
        "sidebar_pixels_equal": difference.getbbox() is None,
    }
(current.parent / "sidebar-comparison.json").write_text(
    json.dumps(result, indent=2), encoding="utf-8"
)
print(json.dumps(result))
