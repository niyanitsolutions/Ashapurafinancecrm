"""Centralized Bin / Trash — Owner-only soft-delete with a 30-day automatic purge.

The Bin is a genuinely cross-module feature (one page, one purge job, every business
record type), so it lives in its own feature module rather than being copied into each
one. It reuses infrastructure that already exists: `BaseDocument`'s
`is_deleted`/`deleted_at`/`deleted_by` fields, `BaseRepository`'s `soft_delete`/
`soft_delete_many`/`restore` and its automatic `is_deleted: false` read filter (so a
binned record disappears from every normal list with zero per-feature changes), the
shared `audit_logs` writer, and the existing Arq cron scheduler for the purge.
"""

RETENTION_DAYS = 30


class BinAuditEvent:
    RECORD_DELETED = "bin_record_deleted"
    RECORDS_BULK_DELETED = "bin_records_bulk_deleted"
    RECORD_RESTORED = "bin_record_restored"
    RECORD_PURGED = "bin_record_purged"
