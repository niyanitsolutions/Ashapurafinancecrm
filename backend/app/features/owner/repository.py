from app.features.owner.models import OwnerProfile
from app.shared.base_repository import BaseRepository


class OwnerProfileRepository(BaseRepository[OwnerProfile]):
    collection_name = "owner_profiles"
    model = OwnerProfile
