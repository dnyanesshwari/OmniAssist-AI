from datetime import date, datetime
from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=20)
    password: str = Field(min_length=8, max_length=72)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    conversation_id: int | None = None


class ProposeIn(BaseModel):
    service_code: str = Field(max_length=40)
    city: str = Field(max_length=60)
    start_at: datetime
    address: str = Field(min_length=5, max_length=300)
    idempotency_key: str = Field(min_length=8, max_length=80)


class CancelIn(BaseModel):
    confirmed: bool = False


class AvailabilityQ(BaseModel):
    service_code: str
    city: str
    day: date


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    conversation_id: int | None = None
    modality: str = Field(default="text", pattern="^(text|voice)$")
    simulate_failure: str | None = Field(default=None, pattern="^llm$")  # honoured only if ALLOW_FAILURE_INJECTION
