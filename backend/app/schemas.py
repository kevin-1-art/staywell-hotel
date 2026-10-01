from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class UserView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    full_name: str
    role: str


class AdminUserView(UserView):
    is_active: bool
    created_at: datetime
    deleted_at: datetime | None


class LoginInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class LoginOutput(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserView


class AdminUserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    role: str
    password: str = Field(min_length=12, max_length=128)

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        from app.models import Role

        if value not in {role.value for role in Role}:
            raise ValueError("Select one of the available staff roles")
        return value

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        if not any(char.islower() for char in value) or not any(char.isupper() for char in value):
            raise ValueError("Password must include upper- and lower-case letters")
        if not any(char.isdigit() for char in value) or not any(not char.isalnum() for char in value):
            raise ValueError("Password must include a number and a symbol")
        return value


class AdminUserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    email: EmailStr | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=12, max_length=128)

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str | None) -> str | None:
        if value is None:
            return value
        from app.models import Role

        if value not in {role.value for role in Role}:
            raise ValueError("Select one of the available staff roles")
        return value

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not any(char.islower() for char in value) or not any(char.isupper() for char in value):
            raise ValueError("Password must include upper- and lower-case letters")
        if not any(char.isdigit() for char in value) or not any(not char.isalnum() for char in value):
            raise ValueError("Password must include a number and a symbol")
        return value

    @model_validator(mode="after")
    def require_update(self):
        if not any(getattr(self, field) is not None for field in ("full_name", "email", "role", "is_active", "password")):
            raise ValueError("Provide at least one account change")
        return self


class RoomTypeView(BaseModel):
    id: str
    code: str
    name: str
    capacity: int
    base_rate_ugx: int
    description: str


class RoomView(BaseModel):
    id: str
    number: str
    floor: int
    room_type_id: str
    room_type_name: str
    status: str
    notes: str


class RoomCreate(BaseModel):
    number: str = Field(min_length=1, max_length=12)
    floor: int = Field(ge=0, le=99)
    room_type_id: str
    notes: str = Field(default="", max_length=500)


class RoomStatusUpdate(BaseModel):
    status: str
    notes: str | None = Field(default=None, max_length=500)


class GuestCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    id_document_number: str | None = Field(default=None, max_length=80)


class GuestView(BaseModel):
    id: str
    first_name: str
    last_name: str
    email: EmailStr | None
    phone: str | None
    id_document_number: str | None
    is_vip: bool
    is_blacklisted: bool


class GuestFlagsUpdate(BaseModel):
    is_vip: bool | None = None
    is_blacklisted: bool | None = None


class ReservationCreate(BaseModel):
    guest_id: str
    room_id: str
    check_in: date
    check_out: date
    source: str = Field(default="direct", min_length=1, max_length=32)
    promo_code: str | None = Field(default=None, max_length=32)
    company_name: str | None = Field(default=None, max_length=120)
    nightly_rate_ugx: int | None = Field(default=None, ge=0, le=100_000_000)
    deposit_ugx: int = Field(default=0, ge=0, le=1_000_000_000)
    special_requests: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.check_out <= self.check_in:
            raise ValueError("Check-out must be after check-in")
        return self


class ReservationView(BaseModel):
    id: str
    confirmation_code: str
    guest_id: str
    guest_name: str
    room_id: str
    room_number: str
    check_in: date
    check_out: date
    status: str
    source: str
    promo_code: str | None = None
    company_name: str | None = None
    pricing_details: dict = {}
    nightly_rate_ugx: int
    deposit_ugx: int
    special_requests: str


class Page(BaseModel):
    items: list
    total: int
    limit: int
    offset: int


class CheckInInput(BaseModel):
    id_document_type: str = Field(min_length=2, max_length=32)
    id_document_number: str = Field(min_length=2, max_length=80)
    early_check_in_fee_ugx: int = Field(default=0, ge=0, le=10_000_000)


class CheckOutInput(BaseModel):
    late_check_out_fee_ugx: int = Field(default=0, ge=0, le=10_000_000)
    manager_override: bool = False
    override_reason: str | None = Field(default=None, min_length=5, max_length=500)


class ChargeCreate(BaseModel):
    description: str = Field(min_length=2, max_length=160)
    category: str = Field(default="service", min_length=2, max_length=32)
    quantity: int = Field(default=1, ge=1, le=1000)
    unit_amount_ugx: int = Field(ge=0, le=100_000_000)


class PaymentCreate(BaseModel):
    amount_ugx: int = Field(gt=0, le=1_000_000_000)
    method: str
    reference: str | None = Field(default=None, max_length=120)


class FolioEntryView(BaseModel):
    id: str
    description: str
    category: str | None = None
    quantity: int | None = None
    unit_amount_ugx: int | None = None
    amount_ugx: int
    method: str | None = None
    reference: str | None = None
    is_refund: bool = False
    created_at: str


class FolioView(BaseModel):
    id: str
    reservation_id: str
    invoice_number: int | None
    status: str
    guest_name: str
    room_number: str
    charges: list[FolioEntryView]
    payments: list[FolioEntryView]
    total_charges_ugx: int
    total_payments_ugx: int
    outstanding_ugx: int


class RateQuoteInput(BaseModel):
    room_type_id: str
    check_in: date
    check_out: date
    promo_code: str | None = Field(default=None, max_length=32)
    company_name: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.check_out <= self.check_in:
            raise ValueError("Check-out must be after check-in")
        return self


class RateQuoteView(BaseModel):
    room_type_id: str
    room_type_name: str
    base_rate_ugx: int
    nights: int
    average_nightly_rate_ugx: int
    subtotal_ugx: int
    service_charge_ugx: int
    tax_ugx: int
    total_ugx: int
    nightly_rates: list[dict]