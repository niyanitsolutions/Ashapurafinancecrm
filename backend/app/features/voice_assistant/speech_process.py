"""Fixed POSIX child launcher: OS limits before exec, no shell or app imports."""

import ctypes
import os
import signal
import sys


def main() -> None:
    if sys.platform != "linux":
        raise SystemExit(2)
    import resource

    timeout, memory = int(sys.argv[1]), int(sys.argv[2])
    if not 5 <= timeout <= 120 or not 256 <= memory <= 16384 or len(sys.argv) < 5:
        raise SystemExit(2)
    # Kill the engine if its worker dies, including the race before prctl setup.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0 or os.getppid() != int(sys.argv[3]):
        raise SystemExit(2)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (timeout, timeout))
    resource.setrlimit(resource.RLIMIT_FSIZE, (3_000_000, 3_000_000))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    resource.setrlimit(resource.RLIMIT_AS, (memory * 1024**2, memory * 1024**2))
    os.execv(sys.argv[4], sys.argv[4:])


if __name__ == "__main__":
    main()
