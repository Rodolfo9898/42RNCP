"""What the web app and the terminal container have to agree on: who the evaluator is, how the evaluator reads a subject, the text every
prompt shares, the marker of the files the review generates, and where a review's files are kept inside the terminal container."""

from shared.constants.evaluator import EVALUATOR, EVALUATOR_EMAIL, HEADER_AUTHOR
from shared.constants.fragments import OBEY, TEST_HERE, UPDATE_BLOCK, verdict_update_rules
from shared.constants.markers import GENERATED_VERDICT_NAMES, VERDICT_MARKER
from shared.constants.reading import STRICT_LAYOUT, evaluation_rules, strict_layout
from shared.constants.terminal import SKIPPED_NAMES, SUBJECT_NAME, TERMINAL_REPORTS_ROOT, TERMINAL_SUBJECTS_ROOT, is_subject_name
