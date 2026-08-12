"""Wraps mongodump for local/manual backups.

TODO: this is a manual-run stub, not a backup strategy. Before production, decide and
document (in docs/KNOWN_LIMITATIONS.md until then): backup frequency, retention, where
dumps are stored (S3?), and whether AWS/GCP managed backup services should be used
instead of this script entirely.

Usage: python scripts/backup.py [output_dir]
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent.parent / "backups"


def main() -> None:
    output_root = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT_ROOT
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        ["mongodump", "--uri", "mongodb://localhost:27017/?replicaSet=rs0", "--out", str(output_dir)],
        check=True,
    )
    print(f"Backup written to {output_dir}")


if __name__ == "__main__":
    main()
