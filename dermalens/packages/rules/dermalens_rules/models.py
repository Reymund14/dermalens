"""Plain data types shared by triage and the recommendation engine.

Everything here is immutable and free of I/O so the rules stay pure functions:
the API loads rows from the database, converts them to these types, and calls
`triage()` / `build_routine()`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

LABELS = ("acne", "hyperpigmentation", "erythema", "texture")
GRADES = ("none", "mild", "moderate", "marked")
GRADE_WEIGHT = {"none": 0, "mild": 1, "moderate": 2, "marked": 3}
ROUTES = ("urgent_care", "dermatologist", "iconic_clinic", "self_care")


# ----- Intake -----------------------------------------------------------------

@dataclass(frozen=True)
class RedFlag:
    code: str
    route: str  # "urgent_care" | "dermatologist"


@dataclass(frozen=True)
class ReportedConcern:
    code: str
    self_severity: int = 1  # 1..3
    duration_weeks: int = 0


@dataclass(frozen=True)
class Intake:
    concerns: tuple[ReportedConcern, ...] = ()
    red_flags_true: tuple[RedFlag, ...] = ()
    skin_type: str = "normal"  # dry | oily | combination | normal | sensitive
    pregnant_or_breastfeeding: bool = False
    on_isotretinoin: bool = False
    current_rx_topicals: bool = False
    allergen_ingredient_ids: frozenset[str] = frozenset()
    allergen_families: frozenset[str] = frozenset()
    reacted_product_ids: frozenset[str] = frozenset()
    current_product_ids: frozenset[str] = frozenset()
    uses_actives_without_reaction: bool = False

    def duration_weeks(self, code: str) -> int:
        for c in self.concerns:
            if c.code == code:
                return c.duration_weeks
        return 0

    def self_severity(self, code: str) -> int:
        for c in self.concerns:
            if c.code == code:
                return c.self_severity
        return 0


# ----- Inference --------------------------------------------------------------

@dataclass(frozen=True)
class LabelResult:
    p: float
    present: bool
    grade: str = "none"
    uncertain: bool = False


@dataclass(frozen=True)
class Inference:
    model_version_id: str
    quality_pass: bool
    ood_score: float
    ood_flag: bool
    refer_out_probability: float
    labels: dict[str, LabelResult]
    thresholds: dict[str, float] = field(default_factory=lambda: {"refer_out": 0.30})


# ----- Catalog and rules ------------------------------------------------------

@dataclass(frozen=True)
class Ingredient:
    id: str
    inci_name: str
    families: frozenset[str] = frozenset()
    irritancy_level: int = 0
    is_active: bool = False
    photosensitizing: bool = False
    pregnancy_avoid: bool = False
    benefits: tuple[tuple[str, float], ...] = ()  # (concern_code, weight)
    benefit_note: str = ""


@dataclass(frozen=True)
class Product:
    id: str
    brand: str
    name: str
    category: str  # cleanser | toner | serum | treatment | moisturizer | sunscreen | exfoliant
    suitable_skin_types: frozenset[str]
    ingredients: tuple[Ingredient, ...]
    spf: int | None = None
    pa_rating: str | None = None
    price_php: float = 0.0
    stocked_by_iconic: bool = False
    is_listed: bool = False
    fda_notification_no: str | None = None

    @property
    def families(self) -> frozenset[str]:
        out: set[str] = set()
        for i in self.ingredients:
            out |= i.families
        return frozenset(out)

    @property
    def ingredient_ids(self) -> frozenset[str]:
        return frozenset(i.id for i in self.ingredients)

    @property
    def is_wash_off(self) -> bool:
        return self.category == "cleanser"

    @property
    def actives(self) -> tuple[Ingredient, ...]:
        return tuple(i for i in self.ingredients if i.is_active)

    @property
    def max_irritancy(self) -> int:
        return max((i.irritancy_level for i in self.ingredients), default=0)

    @property
    def photosensitizing(self) -> bool:
        return any(i.photosensitizing for i in self.ingredients)


@dataclass(frozen=True)
class ConflictRule:
    family_a: str
    family_b: str
    scope: str  # same_application | same_routine | same_day
    resolution: str  # block | split_am_pm | alternate_nights
    rationale: str

    def matches(self, fams_x: frozenset[str], fams_y: frozenset[str]) -> bool:
        a, b = self.family_a, self.family_b
        return (a in fams_x and b in fams_y) or (a in fams_y and b in fams_x)


@dataclass(frozen=True)
class Contraindication:
    condition_code: str  # pregnancy | isotretinoin | rx_topical | sensitive_skin
    family_code: str | None
    ingredient_id: str | None
    action: str  # exclude | limit_wash_off | limit_low_irritancy


@dataclass(frozen=True)
class RuleSet:
    version: str
    conflicts: tuple[ConflictRule, ...]
    contraindications: tuple[Contraindication, ...]


# ----- Outputs ----------------------------------------------------------------

@dataclass(frozen=True)
class TriageResult:
    route: str
    reasons: tuple[str, ...]
    allow_actives: bool
    rule_set_version: str


@dataclass(frozen=True)
class RoutineItem:
    time_of_day: str  # am | pm
    step_order: int
    slot: str
    product: Product
    frequency: str  # daily | alternate_nights | 2x_week
    why: str
    patch_test: bool = False


@dataclass(frozen=True)
class Routine:
    items: tuple[RoutineItem, ...]
    rule_set_version: str
    input_hash: str
    notes: tuple[str, ...] = ()

    def at(self, tod: str) -> tuple[RoutineItem, ...]:
        return tuple(sorted((i for i in self.items if i.time_of_day == tod), key=lambda i: i.step_order))
