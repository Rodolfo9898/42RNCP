"""The entry points: a subject, or the Norm, from its pages to its rules."""

from verdict.subjects.spec.parser.norm import NormParser, parse_norm
from verdict.subjects.spec.parser.subject import SubjectParser, parse_subject

__all__ = ["NormParser", "SubjectParser", "parse_norm", "parse_subject"]
