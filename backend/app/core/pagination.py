from dataclasses import dataclass

from fastapi import Query

from app.constants.api import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.core.response import PaginationMeta


@dataclass
class PageParams:
    page: int
    page_size: int
    sort_by: str | None
    sort_dir: str
    search: str | None

    @property
    def skip(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def sort(self) -> list[tuple[str, int]] | None:
        if not self.sort_by:
            return None
        return [(self.sort_by, 1 if self.sort_dir == "asc" else -1)]

    def build_meta(self, total: int) -> PaginationMeta:
        total_pages = max(1, (total + self.page_size - 1) // self.page_size)
        return PaginationMeta(page=self.page, page_size=self.page_size, total=total, total_pages=total_pages)


def page_params(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    sort_by: str | None = Query(None),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    search: str | None = Query(None),
) -> PageParams:
    return PageParams(page=page, page_size=page_size, sort_by=sort_by, sort_dir=sort_dir, search=search)
