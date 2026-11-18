"""ORM models for the DermaLens schema.

Portable across PostgreSQL 16 (production) and SQLite (local dev / tests):
UUID columns use SQLAlchemy's `Uuid`, JSON becomes JSONB on PostgreSQL, and
case-insensitive text (CITEXT in the roadmap) is stored lower-cased by the
application. `migrations/001_init.sql` is generated from these models for the
PostgreSQL dialect (`python -m app.dump_schema`).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON, BigInteger, Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, LargeBinary,
    Numeric, SmallInteger, String, Text, TypeDecorator, UniqueConstraint, Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

JSONType = JSON().with_variant(JSONB(), "postgresql")


def now() -> datetime:
    return datetime.now(timezone.utc)


def uid() -> uuid.UUID:
    return uuid.uuid4()


def _in(col: str, values) -> str:
    return f"{col} IN ({', '.join(repr(v) for v in values)})"


class UTCDateTime(TypeDecorator):
    """TIMESTAMPTZ on PostgreSQL; on SQLite, values come back tz-aware in UTC."""
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


TS = UTCDateTime()
FOLLOW_UP = ("new", "contacted", "booked", "no_response", "closed")

# ===== Identity and consent ===================================================

class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)  # stored lower-case
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)              # argon2id
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="patient")
    display_name: Mapped[str | None] = mapped_column(Text)  # staff, dermatologist and admin accounts
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    disabled_at: Mapped[datetime | None] = mapped_column(TS)
    mfa_secret_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(TS, default=now, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(TS)
    __table_args__ = (CheckConstraint(_in("role", ("patient", "clinic_staff", "dermatologist", "admin"))),)

    profile: Mapped["PatientProfile | None"] = relationship(back_populates="user", uselist=False,
                                                            foreign_keys="PatientProfile.user_id")

    @property
    def active(self) -> bool:
        return self.deleted_at is None and self.disabled_at is None


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TS, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = mapped_column(TS, default=now, nullable=False)


class Consent(Base):
    __tablename__ = "consents"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(TS, default=now, nullable=False)
    __table_args__ = (CheckConstraint(_in("purpose", ("service", "image_storage", "share_with_clinic",
                                                       "model_improvement"))),)


class PatientProfile(Base):
    __tablename__ = "patient_profiles"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    full_name_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    birth_year: Mapped[int | None] = mapped_column(SmallInteger)
    sex_at_birth: Mapped[str | None] = mapped_column(String(16))
    self_fitzpatrick: Mapped[int | None] = mapped_column(SmallInteger)
    skin_type: Mapped[str | None] = mapped_column(String(16))
    is_pregnant_or_breastfeeding: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TS, default=now, onupdate=now, nullable=False)
    __table_args__ = (
        CheckConstraint("birth_year BETWEEN 1900 AND 2100"),
        CheckConstraint(_in("sex_at_birth", ("female", "male", "intersex", "prefer_not"))),
        CheckConstraint("self_fitzpatrick BETWEEN 1 AND 6"),
        CheckConstraint(_in("skin_type", ("dry", "oily", "combination", "normal", "sensitive"))),
    )
    user: Mapped[User] = relationship(back_populates="profile")


# ===== Catalog and rules (created before intake tables that reference them) ===

class IngredientFamily(Base):
    __tablename__ = "ingredient_families"
    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)


class Ingredient(Base):
    __tablename__ = "ingredients"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # stable slug, e.g. "niacinamide"
    inci_name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    irritancy_level: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    photosensitizing: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pregnancy_avoid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    __table_args__ = (CheckConstraint("irritancy_level BETWEEN 0 AND 3"),)


class IngredientSynonym(Base):
    __tablename__ = "ingredient_synonyms"
    synonym: Mapped[str] = mapped_column(String(120), primary_key=True)  # lower-case
    ingredient_id: Mapped[str] = mapped_column(ForeignKey("ingredients.id"), nullable=False)


class IngredientFamilyMember(Base):
    __tablename__ = "ingredient_family_members"
    family_code: Mapped[str] = mapped_column(ForeignKey("ingredient_families.code"), primary_key=True)
    ingredient_id: Mapped[str] = mapped_column(ForeignKey("ingredients.id"), primary_key=True)


class Concern(Base):
    __tablename__ = "concerns"
    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    model_label: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class IngredientConcernBenefit(Base):
    __tablename__ = "ingredient_concern_benefits"
    ingredient_id: Mapped[str] = mapped_column(ForeignKey("ingredients.id"), primary_key=True)
    concern_code: Mapped[str] = mapped_column(ForeignKey("concerns.code"), primary_key=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_note: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (CheckConstraint("weight BETWEEN 0 AND 1"),)


class IngredientConflict(Base):
    __tablename__ = "ingredient_conflicts"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uid)
    family_a: Mapped[str] = mapped_column(ForeignKey("ingredient_families.code"), nullable=False)
    family_b: Mapped[str] = mapped_column(ForeignKey("ingredient_families.code"), nullable=False)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    resolution: Mapped[str] = mapped_column(String(20), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    rule_set_version: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (
        CheckConstraint(_in("scope", ("same_application", "same_routine", "same_day"))),
        CheckConstraint(_in("resolution", ("block", "split_am_pm", "alternate_nights"))),
    )


class ContraindicationRow(Base):
    __tablename__ = "contraindications"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uid)
    condition_code: Mapped[str] = mapped_column(String(32), nullable=False)
    family_code: Mapped[str | None] = mapped_column(ForeignKey("ingredient_families.code"))
    ingredient_id: Mapped[str | None] = mapped_column(ForeignKey("ingredients.id"))
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    rule_set_version: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (CheckConstraint(_in("action", ("exclude", "limit_wash_off", "limit_low_irritancy"))),)


class Product(Base):
    __tablename__ = "products"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    brand: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    suitable_skin_types: Mapped[list] = mapped_column(JSONType, nullable=False)
    spf: Mapped[int | None] = mapped_column(SmallInteger)
    pa_rating: Mapped[str | None] = mapped_column(String(8))
    price_php: Mapped[float | None] = mapped_column(Numeric(10, 2))
    stocked_by_iconic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_listed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # only true when FDA check current
    __table_args__ = (CheckConstraint(_in("category", ("cleanser", "toner", "serum", "treatment", "moisturizer",
                                                        "sunscreen", "exfoliant"))),)
    fda: Mapped["ProductFdaNotification | None"] = relationship(uselist=False, lazy="joined")
    ingredients: Mapped[list["ProductIngredient"]] = relationship(order_by="ProductIngredient.position",
                                                                  cascade="all, delete-orphan", lazy="selectin")


class ProductFdaNotification(Base):
    __tablename__ = "product_fda_notifications"
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), primary_key=True)
    notification_no: Mapped[str] = mapped_column(Text, nullable=False)
    verified_on: Mapped[date] = mapped_column(Date, nullable=False)
    verified_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    evidence_uri: Mapped[str] = mapped_column(Text, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date)


class ProductIngredient(Base):
    __tablename__ = "product_ingredients"
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    ingredient_id: Mapped[str] = mapped_column(ForeignKey("ingredients.id"), primary_key=True)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    __table_args__ = (Index("ix_product_ingredients_ingredient", "ingredient_id"),)


class AppSetting(Base):
    """Key/value settings, e.g. the active rule-set version."""
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


# ===== Intake ================================================================

class IntakeRow(Base):
    __tablename__ = "intakes"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    questionnaire_version: Mapped[str] = mapped_column(Text, nullable=False)
    sleep_hours: Mapped[float | None] = mapped_column(Numeric(3, 1))
    daily_sun_exposure_min: Mapped[int | None] = mapped_column(SmallInteger)
    sunscreen_use: Mapped[str | None] = mapped_column(String(16))
    smoker: Mapped[bool | None] = mapped_column(Boolean)
    stress_level: Mapped[int | None] = mapped_column(SmallInteger)
    water_glasses_per_day: Mapped[int | None] = mapped_column(SmallInteger)
    current_rx_topicals: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    on_isotretinoin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    uses_actives_without_reaction: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    free_text_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(TS, default=now, nullable=False)
    __table_args__ = (
        CheckConstraint(_in("sunscreen_use", ("never", "sometimes", "daily"))),
        CheckConstraint("stress_level BETWEEN 1 AND 5"),
    )
    concerns: Mapped[list["IntakeConcern"]] = relationship(cascade="all, delete-orphan")
    red_flags: Mapped[list["IntakeRedFlag"]] = relationship(cascade="all, delete-orphan")
    routine_items: Mapped[list["CurrentRoutineItem"]] = relationship(cascade="all, delete-orphan")


class IntakeConcern(Base):
    __tablename__ = "intake_concerns"
    intake_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("intakes.id", ondelete="CASCADE"), primary_key=True)
    concern_code: Mapped[str] = mapped_column(ForeignKey("concerns.code"), primary_key=True)
    self_severity: Mapped[int | None] = mapped_column(SmallInteger)
    duration_weeks: Mapped[int | None] = mapped_column(SmallInteger)
    __table_args__ = (CheckConstraint("self_severity BETWEEN 1 AND 3"),)


class RedFlagDefinition(Base):
    __tablename__ = "red_flag_definitions"
    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    route: Mapped[str] = mapped_column(String(20), nullable=False)
    rule_set_version: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (CheckConstraint(_in("route", ("dermatologist", "urgent_care"))),)


class IntakeRedFlag(Base):
    __tablename__ = "intake_red_flags"
    intake_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("intakes.id", ondelete="CASCADE"), primary_key=True)
    red_flag_code: Mapped[str] = mapped_column(ForeignKey("red_flag_definitions.code"), primary_key=True)
    answer: Mapped[bool] = mapped_column(Boolean, nullable=False)


class UserAllergen(Base):
    __tablename__ = "user_allergens"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    ingredient_id: Mapped[str | None] = mapped_column(ForeignKey("ingredients.id"))
    family_code: Mapped[str | None] = mapped_column(ForeignKey("ingredient_families.code"))
    raw_text: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (CheckConstraint(
        "ingredient_id IS NOT NULL OR family_code IS NOT NULL OR raw_text IS NOT NULL"),)


class CurrentRoutineItem(Base):
    __tablename__ = "current_routine_items"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uid)
    intake_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("intakes.id", ondelete="CASCADE"), nullable=False)
    time_of_day: Mapped[str | None] = mapped_column(String(4))
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"))
    free_text_name: Mapped[str | None] = mapped_column(Text)
    reaction_reported: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    __table_args__ = (CheckConstraint(_in("time_of_day", ("am", "pm", "both"))),)


# ===== Capture and inference ==================================================

class CaptureSession(Base):
    __tablename__ = "capture_sessions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    intake_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("intakes.id"), nullable=False)
    device_model: Mapped[str | None] = mapped_column(Text)
    app_version: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    quality_failures: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TS, default=now, nullable=False)
    __table_args__ = (
        CheckConstraint(_in("status", ("open", "uploaded", "processing", "needs_retake", "complete", "failed"))),
        Index("ix_capture_sessions_user_created", "user_id", "created_at"),
    )
    images: Mapped[list["ImageRow"]] = relationship(cascade="all, delete-orphan")


class ImageRow(Base):
    __tablename__ = "images"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uid)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("capture_sessions.id", ondelete="CASCADE"),
                                                  nullable=False)
    view: Mapped[str] = mapped_column(String(10), nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    width_px: Mapped[int | None] = mapped_column(Integer)
    height_px: Mapped[int | None] = mapped_column(Integer)
    blur_score: Mapped[float | None] = mapped_column(Float)
    brightness_mean: Mapped[float | None] = mapped_column(Float)
    face_coverage: Mapped[float | None] = mapped_column(Float)
    device_checks: Mapped[dict | None] = mapped_column(JSONType)  # on-device check results
    server_checks: Mapped[dict | None] = mapped_column(JSONType)
    quality_pass: Mapped[bool] = mapped_column(Boolean, nullable=False)
    superseded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # replaced by a retake
    created_at: Mapped[datetime] = mapped_column(TS, default=now, nullable=False)
    __table_args__ = (CheckConstraint(_in("view", ("front", "left45", "right45", "closeup"))),)


class ModelVersion(Base):
    __tablename__ = "model_versions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    architecture: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    thresholds: Mapped[dict] = mapped_column(JSONType, nullable=False)
    temperature: Mapped[dict] = mapped_column(JSONType, nullable=False)
    eval_report_uri: Mapped[str] = mapped_column(Text, nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(TS)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class InferenceRow(Base):
    __tablename__ = "inferences"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uid)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("capture_sessions.id"), nullable=False)
    model_version_id: Mapped[str] = mapped_column(ForeignKey("model_versions.id"), nullable=False)
    quality_pass: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ood_score: Mapped[float] = mapped_column(Float, nullable=False)
    ood_flag: Mapped[bool] = mapped_column(Boolean, nullable=False)
    refer_out_probability: Mapped[float] = mapped_column(Float, nullable=False)
    raw: Mapped[dict] = mapped_column(JSONType, nullable=False)  # full contract response, for audit
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(TS, default=now, nullable=False)
    labels: Mapped[list["InferenceLabel"]] = relationship(cascade="all, delete-orphan")


class InferenceLabel(Base):
    __tablename__ = "inference_labels"
    inference_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("inferences.id", ondelete="CASCADE"),
                                                    primary_key=True)
    concern_code: Mapped[str] = mapped_column(ForeignKey("concerns.code"), primary_key=True)
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    present: Mapped[bool] = mapped_column(Boolean, nullable=False)
    grade: Mapped[str] = mapped_column(String(10), nullable=False, default="none")
    uncertain: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    __table_args__ = (
        CheckConstraint("probability BETWEEN 0 AND 1"),
        CheckConstraint(_in("grade", ("none", "mild", "moderate", "marked"))),
    )


# ===== Outputs, referrals, audit =============================================

class TriageDecision(Base):
    __tablename__ = "triage_decisions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uid)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("capture_sessions.id"), unique=True, nullable=False)
    inference_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("inferences.id"))
    route: Mapped[str] = mapped_column(String(20), nullable=False)
    reasons: Mapped[list] = mapped_column(JSONType, nullable=False)
    rule_set_version: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TS, default=now, nullable=False)
    __table_args__ = (CheckConstraint(_in("route", ("urgent_care", "dermatologist", "iconic_clinic",
                                                     "self_care"))),)


class Recommendation(Base):
    __tablename__ = "recommendations"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uid)
    triage_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("triage_decisions.id"), nullable=False)
    rule_set_version: Mapped[str] = mapped_column(Text, nullable=False)
    catalog_snapshot_at: Mapped[datetime] = mapped_column(TS, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")  # ok | no_safe_product | aborted
    notes: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(TS, default=now, nullable=False)
    items: Mapped[list["RecommendationItem"]] = relationship(
        cascade="all, delete-orphan", order_by="(RecommendationItem.time_of_day, RecommendationItem.step_order)")


class RecommendationItem(Base):
    __tablename__ = "recommendation_items"
    recommendation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recommendations.id", ondelete="CASCADE"),
                                                         primary_key=True)
    time_of_day: Mapped[str] = mapped_column(String(2), primary_key=True)
    step_order: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    slot: Mapped[str] = mapped_column(String(16), nullable=False)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False)
    frequency: Mapped[str] = mapped_column(String(20), nullable=False)
    why: Mapped[str] = mapped_column(Text, nullable=False)
    patch_test: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    __table_args__ = (
        CheckConstraint(_in("time_of_day", ("am", "pm"))),
        CheckConstraint(_in("frequency", ("daily", "alternate_nights", "2x_week"))),
    )
    product: Mapped[Product] = relationship(lazy="joined")


class ConsultationSummary(Base):
    __tablename__ = "consultation_summaries"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uid)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("capture_sessions.id"), nullable=False)
    pdf_object_key: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict] = mapped_column(JSONType, nullable=False)  # same content as the PDF, for import
    share_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    shared_with: Mapped[str | None] = mapped_column(String(20))
    expires_at: Mapped[datetime | None] = mapped_column(TS)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(TS)
    staff_note: Mapped[str | None] = mapped_column(Text)
    follow_up_status: Mapped[str] = mapped_column(String(16), nullable=False, default="new")
    created_at: Mapped[datetime] = mapped_column(TS, default=now, nullable=False)
    __table_args__ = (
        CheckConstraint(_in("shared_with", ("iconic_clinic", "patient_only"))),
        CheckConstraint(_in("follow_up_status", FOLLOW_UP)),
    )


class DermReview(Base):
    """A dermatologist's independent read of a shared case (Level 3 agreement data)."""
    __tablename__ = "derm_reviews"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uid)
    summary_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("consultation_summaries.id"), nullable=False)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    app_route: Mapped[str] = mapped_column(String(20), nullable=False)
    derm_route: Mapped[str] = mapped_column(String(20), nullable=False)
    concern_agreement: Mapped[dict] = mapped_column(JSONType, nullable=False)  # {"acne": true, ...}
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TS, default=now, nullable=False)
    __table_args__ = (
        UniqueConstraint("summary_id", "reviewer_id"),
        CheckConstraint(_in("derm_route", ("urgent_care", "dermatologist", "iconic_clinic", "self_care"))),
    )


class RuleSignoff(Base):
    """Dermatologist sign-off of a triage + recommendation rule-set version."""
    __tablename__ = "rule_signoffs"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uid)
    triage_version: Mapped[str] = mapped_column(Text, nullable=False)
    rule_set_version: Mapped[str] = mapped_column(Text, nullable=False)
    signed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    signed_at: Mapped[datetime] = mapped_column(TS, default=now, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True,
                                    autoincrement=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str] = mapped_column(Text, nullable=False)
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict | None] = mapped_column(JSONType)
    at: Mapped[datetime] = mapped_column(TS, default=now, nullable=False)
    __table_args__ = (Index("ix_audit_log_entity", "entity", "entity_id"),)
