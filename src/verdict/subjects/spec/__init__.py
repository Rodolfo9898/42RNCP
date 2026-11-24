"""Turn the text of a 42 subject into a list of checkable rules.

42 subjects share a layout: a table of fields (`Program Name`, `Files to Submit`,
`Makefile`, `External Function`, ...) for each deliverable, plus shared "general
rules" prose. The table is parsed structurally; the prose is matched against a
list of known rules, and any other requirement-looking sentence becomes a manual
rule so that nothing in the subject is silently dropped.
"""

from verdict.subjects.spec.files import expand_files
from verdict.subjects.spec.lines import read_lines
from verdict.subjects.spec.model import Line, Spec, merge_rules
from verdict.subjects.spec.parser import parse_norm, parse_subject
from verdict.subjects.spec.prose import cpp_module as _cpp_module
from verdict.subjects.spec.vocabulary import LABELS, MATH_FUNCTIONS, label_of

__all__ = ["LABELS", "Line", "MATH_FUNCTIONS", "Spec", "_cpp_module", "expand_files", "label_of", "merge_rules", "parse_norm",
           "parse_subject", "read_lines"]
