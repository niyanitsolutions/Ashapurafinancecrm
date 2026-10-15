from app.core.exceptions import ForbiddenError
from app.features.auth.models import User


def owner_only(actor: User) -> None:
    if actor.role != "owner":
        raise ForbiddenError("Voice service configuration and activation require the Owner.")
