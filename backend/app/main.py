from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.config.database import close_client, get_database
from app.config.redis import close_redis
from app.config.settings import get_settings
from app.core.exceptions import (
    AppError,
    app_error_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.features.access_control.indexes import ensure_access_control_indexes
from app.features.access_control.router import router as access_control_router
from app.features.auth.indexes import ensure_auth_indexes
from app.features.auth.router import router as auth_router
from app.features.communication.indexes import ensure_communication_indexes
from app.features.communication.router import public_router as communication_public_router
from app.features.communication.router import router as communication_router
from app.features.customer.indexes import ensure_customer_indexes
from app.features.customer.public_router import router as customer_public_router
from app.features.customer.router import router as customer_router
from app.features.dashboard.indexes import ensure_dashboard_indexes
from app.features.dashboard.router import router as dashboard_router
from app.features.employee.indexes import ensure_employee_indexes
from app.features.employee.router import master_data_router
from app.features.employee.router import router as employee_router
from app.features.geo_fencing.indexes import ensure_geo_fencing_indexes
from app.features.geo_fencing.router import router as geo_fencing_router
from app.features.health.router import router as health_router
from app.features.insurance_management.router import router as insurance_management_router
from app.features.integrations.indexes import ensure_integrations_indexes
from app.features.integrations.router import public_router as integrations_public_router
from app.features.integrations.router import router as integrations_router
from app.features.lead_capture.indexes import ensure_lead_capture_indexes
from app.features.lead_capture.router import public_router as lead_capture_public_router
from app.features.lead_capture.router import router as lead_capture_router
from app.features.leads.indexes import ensure_lead_indexes
from app.features.leads.router import router as leads_router
from app.features.loan_management.router import router as loan_management_router
from app.features.owner.indexes import ensure_owner_indexes
from app.features.owner.router import router as owner_router
from app.features.referral_partner_management.indexes import (
    ensure_referral_partner_management_indexes,
)
from app.features.referral_partner_management.router import (
    router as referral_partner_management_router,
)
from app.features.reminders.indexes import ensure_reminders_indexes
from app.features.reminders.router import router as reminders_router
from app.features.reporting.indexes import ensure_reporting_indexes
from app.features.reporting.router import router as reporting_router
from app.features.support.indexes import ensure_support_indexes
from app.features.support.router import router as support_router
from app.features.system_settings.indexes import ensure_system_settings_indexes
from app.features.system_settings.router import router as system_settings_router
from app.features.workflow_engine.indexes import ensure_workflow_engine_indexes
from app.logging_config import configure_logging
from app.middleware.cors import setup_cors
from app.middleware.logging import RequestLoggingMiddleware
from app.middleware.request_id import RequestIdMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging(process="app")
    await ensure_auth_indexes(get_database())
    await ensure_employee_indexes(get_database())
    await ensure_access_control_indexes(get_database())
    await ensure_geo_fencing_indexes(get_database())
    await ensure_system_settings_indexes(get_database())
    await ensure_dashboard_indexes(get_database())
    await ensure_lead_indexes(get_database())
    await ensure_customer_indexes(get_database())
    await ensure_workflow_engine_indexes(get_database())
    await ensure_reminders_indexes(get_database())
    await ensure_referral_partner_management_indexes(get_database())
    await ensure_reporting_indexes(get_database())
    await ensure_integrations_indexes(get_database())
    await ensure_lead_capture_indexes(get_database())
    await ensure_communication_indexes(get_database())
    await ensure_owner_indexes(get_database())
    await ensure_support_indexes(get_database())
    yield
    await close_client()
    await close_redis()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)

    setup_cors(app)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    # Rewrites request.client from X-Forwarded-For — but ONLY when the immediate TCP
    # peer is in trusted_hosts (Nginx on this same box by default). Without this, every
    # request behind a reverse proxy shows the same proxy IP to rate_limit.py and to
    # session/audit-log IP recording, collapsing every client into one shared bucket.
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=settings.trusted_proxy_ip_list)

    app.add_exception_handler(AppError, app_error_handler)
    # Both registered so every response — not just AppError's — uses the app's standard
    # envelope; see docs/api/ERROR_CODES.md and core/exceptions.py's own docstrings.
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    app.include_router(health_router, prefix=settings.api_v1_prefix)
    app.include_router(auth_router, prefix=settings.api_v1_prefix)
    app.include_router(owner_router, prefix=settings.api_v1_prefix)
    app.include_router(employee_router, prefix=settings.api_v1_prefix)
    app.include_router(master_data_router, prefix=settings.api_v1_prefix)
    app.include_router(access_control_router, prefix=settings.api_v1_prefix)
    app.include_router(geo_fencing_router, prefix=settings.api_v1_prefix)
    app.include_router(system_settings_router, prefix=settings.api_v1_prefix)
    app.include_router(dashboard_router, prefix=settings.api_v1_prefix)
    app.include_router(leads_router, prefix=settings.api_v1_prefix)
    app.include_router(customer_public_router, prefix=settings.api_v1_prefix)
    app.include_router(customer_router, prefix=settings.api_v1_prefix)
    app.include_router(loan_management_router, prefix=settings.api_v1_prefix)
    app.include_router(insurance_management_router, prefix=settings.api_v1_prefix)
    app.include_router(reminders_router, prefix=settings.api_v1_prefix)
    app.include_router(referral_partner_management_router, prefix=settings.api_v1_prefix)
    app.include_router(reporting_router, prefix=settings.api_v1_prefix)
    app.include_router(integrations_public_router, prefix=settings.api_v1_prefix)
    app.include_router(integrations_router, prefix=settings.api_v1_prefix)
    app.include_router(lead_capture_public_router, prefix=settings.api_v1_prefix)
    app.include_router(lead_capture_router, prefix=settings.api_v1_prefix)
    app.include_router(communication_public_router, prefix=settings.api_v1_prefix)
    app.include_router(communication_router, prefix=settings.api_v1_prefix)
    app.include_router(support_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
