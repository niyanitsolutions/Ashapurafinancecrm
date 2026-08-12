"""Wraps mongorestore for a dump produced by backup.py. See backup.py for the TODO on
formalizing a real backup/restore strategy before production.

Usage: python scripts/restore.py <dump_dir>
"""

import subprocess
import sys


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/restore.py <dump_dir>")
        raise SystemExit(1)

    dump_dir = sys.argv[1]
    subprocess.run(
        ["mongorestore", "--uri", "mongodb://localhost:27017/?replicaSet=rs0", "--drop", dump_dir],
        check=True,
    )
    print(f"Restored from {dump_dir}")


if __name__ == "__main__":
    main()
