"""Suppress dependency wire logs only inside an Airtel secret-bearing request.

httpx logs complete request URLs at INFO; recording tokens are query parameters
in the guide's curl example. Changing global log levels would affect other CRM
requests and race with concurrent work. A ContextVar-backed filter scopes this
suppression to the current async task, including cleanup/error paths.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_private: ContextVar[bool] = ContextVar("airtel_private_transport", default=False)


class _PrivateTransportFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not _private.get()


_filter = _PrivateTransportFilter()


@contextmanager
def private_transport_logs() -> Iterator[None]:
    # Cover httpx/httpcore's installed transport logger names, including lazy
    # HTTP/2/SOCKS imports, and any already-loaded dependency child loggers.
    names = {
        "httpx",
        "httpcore",
        "httpcore.connection",
        "httpcore.http11",
        "httpcore.http2",
        "httpcore.proxy",
        "httpcore.socks",
        "httpcore.pool",
        "httpcore.connection_pool",
    }
    names.update(
        name
        for name in list(logging.Logger.manager.loggerDict)
        if name.startswith(("httpx.", "httpcore."))
    )
    for name in names:
        logging.getLogger(name).addFilter(_filter)
    token = _private.set(True)
    try:
        yield
    finally:
        _private.reset(token)
