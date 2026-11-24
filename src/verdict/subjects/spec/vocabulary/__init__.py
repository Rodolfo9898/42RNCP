"""What the subjects say: table labels, requirement wording, the math library."""

from verdict.subjects.spec.vocabulary.labels import LABELS, SKIPPED_CHAPTERS, label_of
from verdict.subjects.spec.vocabulary.libm import MATH_FUNCTIONS
from verdict.subjects.spec.vocabulary.words import (
    ABOUT_THE_SUBJECT, DEFAULT_MAKEFILE_RULES, NOT_FUNCTIONS, REQUIREMENT_WORDS, identifiers)

__all__ = ["ABOUT_THE_SUBJECT", "DEFAULT_MAKEFILE_RULES", "LABELS", "MATH_FUNCTIONS", "NOT_FUNCTIONS", "REQUIREMENT_WORDS",
           "SKIPPED_CHAPTERS", "identifiers", "label_of"]
