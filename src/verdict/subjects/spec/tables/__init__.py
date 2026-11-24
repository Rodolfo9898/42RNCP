"""The field tables of a subject (program tables, function tables, C++ exercises) turned into rules."""

from verdict.subjects.spec.tables.exercises import cpp_exercise_rules
from verdict.subjects.spec.tables.fields import read_table
from verdict.subjects.spec.tables.functions import FunctionTables, libft_part1
from verdict.subjects.spec.tables.parser import TableParser, parse_tables
from verdict.subjects.spec.tables.programs import ProgramRules

__all__ = ["FunctionTables", "ProgramRules", "TableParser", "cpp_exercise_rules", "libft_part1", "parse_tables", "read_table"]
