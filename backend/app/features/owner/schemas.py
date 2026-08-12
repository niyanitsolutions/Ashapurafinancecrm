from pydantic import BaseModel, EmailStr, Field

from app.features.auth.schemas import MobileStr


class RegisterOwnerRequest(BaseModel):
    company_name: str
    owner_name: str
    mobile: MobileStr
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    accept_terms: bool


class RegistrationStatusResponse(BaseModel):
    owner_exists: bool
