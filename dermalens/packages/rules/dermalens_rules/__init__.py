"""DermaLens rules package: triage cascade and deterministic routine builder.

Pure functions, no I/O. Versioned with the rule set.
"""
from .models import (  # noqa: F401
    GRADES, LABELS, ROUTES, ConflictRule, Contraindication, Inference, Ingredient, Intake, LabelResult,
    Product, RedFlag, ReportedConcern, Routine, RoutineItem, RuleSet, TriageResult,
)
from .recommend import Context, NoSafeProduct, UnsafeRoutine, build_routine, exclusion_reason  # noqa: F401
from .triage import RULE_SET_VERSION as TRIAGE_VERSION, triage  # noqa: F401
