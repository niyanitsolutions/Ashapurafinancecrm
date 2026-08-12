"""Minimal User-Agent parsing for Session Management display purposes only (device/
browser/OS shown on a future "active sessions" screen) — not security-critical, so a
small regex-based parser is used instead of adding a heavy third-party dependency for a
best-effort label.
"""

import re
from dataclasses import dataclass

_BROWSER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Edge", re.compile(r"Edg/")),
    ("Opera", re.compile(r"OPR/|Opera/")),
    ("Chrome", re.compile(r"Chrome/")),
    ("Firefox", re.compile(r"Firefox/")),
    ("Safari", re.compile(r"Safari/")),
)

_OS_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Windows", re.compile(r"Windows")),
    ("macOS", re.compile(r"Mac OS X")),
    ("Android", re.compile(r"Android")),
    ("iOS", re.compile(r"iPhone|iPad|iPod")),
    ("Linux", re.compile(r"Linux")),
)

_MOBILE_PATTERN = re.compile(r"Mobi|Android|iPhone|iPad")


@dataclass(frozen=True)
class ParsedUserAgent:
    browser: str
    operating_system: str
    device: str


def parse_user_agent(user_agent: str | None) -> ParsedUserAgent:
    if not user_agent:
        return ParsedUserAgent(browser="Unknown", operating_system="Unknown", device="Unknown")

    browser = next((name for name, pattern in _BROWSER_PATTERNS if pattern.search(user_agent)), "Unknown")
    operating_system = next((name for name, pattern in _OS_PATTERNS if pattern.search(user_agent)), "Unknown")
    device = "Mobile" if _MOBILE_PATTERN.search(user_agent) else "Desktop"
    return ParsedUserAgent(browser=browser, operating_system=operating_system, device=device)
