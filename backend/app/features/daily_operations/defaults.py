"""Owner-approved baseline: every active employee can maintain their own daily entries.

This grants no cross-employee access and no loan lifecycle or authentication mutations.
Deletion and session corrections remain Owner-only even if a role grants delete/edit.
"""

EMPLOYEE_ACTIONS: dict[str, tuple[str, ...]] = {
    "follow-ups": ("view", "create", "edit", "import", "export"),
    "progress": ("view", "create", "edit", "import", "export"),
    "issues": ("view", "create", "edit", "approve", "import", "export"),
    "sessions": ("view", "export"),
}
