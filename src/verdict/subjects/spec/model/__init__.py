"""The records the parser works with (a line of the subject, a parsed subject) and how rules are made and merged."""

from verdict.subjects.spec.model.factory import make_rule
from verdict.subjects.spec.model.merge import merge_rules
from verdict.subjects.spec.model.records import Line, Spec

__all__ = ["Line", "Spec", "make_rule", "merge_rules"]
