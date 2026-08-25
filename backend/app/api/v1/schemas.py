from pydantic import BaseModel, EmailStr


class MerchantOnboardingRequest(BaseModel):
    email: EmailStr
    name: str
    category: str
    description: str | None = None


class MerchantOnboardingResponse(BaseModel):
    user_id: str
    merchant_id: str
    name: str
    status: str