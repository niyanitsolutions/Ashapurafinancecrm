"""Read-only sidebar comparison against approved prior synthetic capture."""

import json
from pathlib import Path

from PIL import Image, ImageChops

root = Path(__file__).resolve().parents[1] / "docs" / "screenshots"
before = Image.open(root / "voice-upgrade" / "before" / "campaigns-1440.png").convert("RGB")
after = Image.open(root / "voice-platform-2026-10-16" / "platform-settings-1440.png").convert("RGB")
difference = ImageChops.difference(before.crop((0, 0, 280, 1000)), after.crop((0, 0, 280, 1000)))
result = {"synthetic": True, "comparison": "Prior desktop campaign versus current desktop settings, original 280px sidebar", "changed_pixel_bounds": difference.getbbox(), "sidebar_pixels_equal": difference.getbbox() is None}
(root / "voice-platform-2026-10-16" / "sidebar-comparison.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result))
