"""Who is using this app."""

from __future__ import annotations

# Who is using this app, so that claude knows whom it works for (its system prompt and the review prompt say so).
EVALUATOR = "rperez-t"
# The Norm wants the 42 header at the top of every C file, with the author as `By: login <email>`: this is what a new file gets.
EVALUATOR_EMAIL = "rperez-t@student.42belgium.be"
HEADER_AUTHOR = f"{EVALUATOR} <{EVALUATOR_EMAIL}>"
