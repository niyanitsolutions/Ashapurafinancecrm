from app.features.dashboard.models import DashboardLayoutPreference, DashboardWidget, NavItem
from app.shared.base_repository import BaseRepository


class DashboardWidgetRepository(BaseRepository[DashboardWidget]):
    collection_name = "dashboard_widgets"
    model = DashboardWidget

    async def find_by_key(self, key: str) -> DashboardWidget | None:
        doc = await self.collection.find_one({"key": key, "is_deleted": False})
        return self.model.model_validate(doc) if doc else None


class DashboardLayoutPreferenceRepository(BaseRepository[DashboardLayoutPreference]):
    collection_name = "dashboard_layout_preferences"
    model = DashboardLayoutPreference

    async def find_for_user(self, user_id: str) -> list[DashboardLayoutPreference]:
        return await self.find_many({"user_id": user_id}, limit=200)

    async def find_one_for_user_widget(self, user_id: str, widget_key: str) -> DashboardLayoutPreference | None:
        doc = await self.collection.find_one({"user_id": user_id, "widget_key": widget_key, "is_deleted": False})
        return self.model.model_validate(doc) if doc else None


class NavItemRepository(BaseRepository[NavItem]):
    collection_name = "nav_items"
    model = NavItem

    async def find_by_key(self, key: str) -> NavItem | None:
        doc = await self.collection.find_one({"key": key, "is_deleted": False})
        return self.model.model_validate(doc) if doc else None
