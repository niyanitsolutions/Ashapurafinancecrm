"""Centralized Bin routes — every one is Owner-only (`Depends(require_owner)`), the
backend enforcement the spec requires: an Employee gets a 403 even calling these
directly, not just a hidden button.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.pagination import PageParams, page_params
from app.core.response import ApiResponse, ResponseMeta
from app.features.auth.models import User
from app.features.bin.dependencies import get_bin_service
from app.features.bin.models import BinEntry
from app.features.bin.schemas import (
    BinEntryResponse,
    BulkDeleteRequest,
    BulkDeleteResponse,
    DeletableResourceResponse,
)
from app.features.bin.service import BinService
from app.features.employee.dependencies import require_owner

router = APIRouter(prefix="/bin", tags=["bin"])

ServiceDep = Annotated[BinService, Depends(get_bin_service)]
OwnerDep = Annotated[User, Depends(require_owner)]
PageParamsDep = Annotated[PageParams, Depends(page_params)]


def _entry_response(entry: BinEntry) -> BinEntryResponse:
    return BinEntryResponse(
        id=entry.require_id(), resource_key=entry.resource_key, module_label=entry.module_label,
        stage_label=entry.stage_label, record_code=entry.record_code, record_summary=entry.record_summary,
        document_id=entry.document_id, deleted_by=entry.deleted_by, deleted_by_name=entry.deleted_by_name,
        deleted_at=entry.deleted_at, purge_at=entry.purge_at,
    )


@router.get("/resources")
async def list_deletable_resources(service: ServiceDep, _owner: OwnerDep) -> ApiResponse[list[DeletableResourceResponse]]:
    return ApiResponse[list[DeletableResourceResponse]].ok([DeletableResourceResponse(**r) for r in service.resources()])


@router.get("")
async def list_bin(
    service: ServiceDep, _owner: OwnerDep, page: PageParamsDep, module: str | None = None
) -> ApiResponse[list[BinEntryResponse]]:
    entries, total = await service.list_bin(resource_key=module, search=page.search, skip=page.skip, limit=page.page_size)
    return ApiResponse[list[BinEntryResponse]].ok(
        [_entry_response(e) for e in entries], meta=ResponseMeta(pagination=page.build_meta(total))
    )


@router.delete("/{resource_key}/{document_id}")
async def delete_record(resource_key: str, document_id: str, service: ServiceDep, owner: OwnerDep) -> ApiResponse[BinEntryResponse]:
    entry = await service.delete(resource_key, document_id, owner)
    return ApiResponse[BinEntryResponse].ok(_entry_response(entry))


@router.post("/{resource_key}/bulk-delete")
async def bulk_delete_records(
    resource_key: str, payload: BulkDeleteRequest, service: ServiceDep, owner: OwnerDep
) -> ApiResponse[BulkDeleteResponse]:
    result = await service.bulk_delete(resource_key, payload.document_ids, owner)
    return ApiResponse[BulkDeleteResponse].ok(BulkDeleteResponse(**result))


@router.post("/{bin_entry_id}/restore")
async def restore_record(bin_entry_id: str, service: ServiceDep, owner: OwnerDep) -> ApiResponse[BinEntryResponse]:
    entry = await service.restore(bin_entry_id, owner)
    return ApiResponse[BinEntryResponse].ok(_entry_response(entry))
