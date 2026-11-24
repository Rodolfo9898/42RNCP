"""Suggestions for making a project better: structure, code, logic and readability.

Everything here is a heuristic read of the files (one Strategy class per kind of reading). It never affects the verdict.
"""

from verdict.reports.improve.code import CodeHeuristic
from verdict.reports.improve.functions import functions
from verdict.reports.improve.heuristic import Heuristic
from verdict.reports.improve.logic import LogicHeuristic
from verdict.reports.improve.readme import readme_required, readme_status
from verdict.reports.improve.structure import StructureHeuristic
from verdict.reports.improve.suggest import PRIORITY_ORDER, Suggester, suggest
