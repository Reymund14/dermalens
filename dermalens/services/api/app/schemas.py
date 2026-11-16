from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field

SkinType = Literal["dry", "oily", "combination", "normal", "sensitive"]
View = Literal["front", "left45", "right45", "closeup"]


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    accepted_boundary: bool  # the "I understand" tap on the boundary screen


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class TokensOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str


class ConsentIn(BaseModel):
    purpose: Literal["service", "image_storage", "share_with_clinic", "model_improvement"]
    granted: bool


class ProfileIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    birth_year: int | None = Field(default=None, ge=1900, le=2100)
    sex_at_birth: Literal["female", "male", "intersex", "prefer_not"] | None = None
    self_fitzpatrick: int | None = Field(default=None, ge=1, le=6)
    skin_type: SkinType | None = None
    is_pregnant_or_breastfeeding: bool = False


class ConcernIn(BaseModel):
    code: str
    self_severity: int = Field(ge=1, le=3)
    duration_weeks: int = Field(ge=0, le=520)


class AllergenIn(BaseModel):
    ingredient_id: str | None = None
    family_code: str | None = None
    raw_text: str | None = Field(default=None, max_length=200)


class RoutineItemIn(BaseModel):
    time_of_day: Literal["am", "pm", "both"]
    product_id: str | None = None
    free_text_name: str | None = Field(default=None, max_length=200)
    reaction_reported: bool = False


class LifestyleIn(BaseModel):
    sleep_hours: float | None = Field(default=None, ge=0, le=24)
    daily_sun_exposure_min: int | None = Field(default=None, ge=0, le=1440)
    sunscreen_use: Literal["never", "sometimes", "daily"] | None = None
    smoker: bool | None = None
    stress_level: int | None = Field(default=None, ge=1, le=5)
    water_glasses_per_day: int | None = Field(default=None, ge=0, le=40)


class IntakeIn(BaseModel):
    concerns: list[ConcernIn] = []
    red_flags: dict[str, bool]  # every defined red-flag question must be answered
    allergens: list[AllergenIn] = []
    current_routine: list[RoutineItemIn] = []
    lifestyle: LifestyleIn = LifestyleIn()
    on_isotretinoin: bool = False
    current_rx_topicals: bool = False
    uses_actives_without_reaction: bool = False
    free_text: str | None = Field(default=None, max_length=2000)


class SessionIn(BaseModel):
    intake_id: str
    app_version: str = "0.1.0"
    device_model: str | None = None


class ImageIn(BaseModel):
    view: View
    object_key: str
    sha256: str = Field(min_length=64, max_length=64)
    device_checks: dict[str, bool] | None = None


class SummaryIn(BaseModel):
    share_with_iconic: bool = False


class ReviewIn(BaseModel):
    reviewed: bool | None = None
    staff_note: str | None = Field(default=None, max_length=2000)
    follow_up_status: Literal["new", "contacted", "booked", "no_response", "closed"] | None = None


ROUTE = Literal["urgent_care", "dermatologist", "iconic_clinic", "self_care"]
STAFF_ROLE = Literal["clinic_staff", "dermatologist", "admin"]


class DermReviewIn(BaseModel):
    derm_route: ROUTE
    concern_agreement: dict[str, bool] = Field(default_factory=dict)
    note: str | None = Field(default=None, max_length=2000)


class SignoffIn(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class StaffUserIn(BaseModel):
    email: EmailStr
    role: STAFF_ROLE
    display_name: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=10, max_length=128)


class UserPatchIn(BaseModel):
    role: STAFF_ROLE | None = None
    display_name: str | None = Field(default=None, min_length=2, max_length=80)
    disabled: bool | None = None
    password: str | None = Field(default=None, min_length=10, max_length=128)


class ProductIn(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]{3,64}$")
    brand: str
    name: str
    category: Literal["cleanser", "toner", "serum", "treatment", "moisturizer", "sunscreen", "exfoliant"]
    suitable_skin_types: list[str]
    inci: list[str] = Field(min_length=1)  # label order; every term must map through the synonym table
    spf: int | None = None
    pa_rating: str | None = None
    price_php: float | None = None
    stocked_by_iconic: bool = False


class FdaVerifyIn(BaseModel):
    notification_no: str = Field(min_length=3)
    evidence_uri: str = Field(min_length=3)  # screenshot/PDF of the FDA verification portal result
    valid_until: str | None = None


class ConflictIn(BaseModel):
    family_a: str
    family_b: str
    scope: Literal["same_application", "same_routine", "same_day"]
    resolution: Literal["block", "split_am_pm", "alternate_nights"]
    rationale: str = Field(min_length=3)
