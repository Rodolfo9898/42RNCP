"""The numbers the terminal service holds itself to."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Limits:
    # The PDFs of a review (its subjects, and the Norm when it applies) are handed over by the web app.
    max_subject_files: int = 25
    max_subject_file_bytes: int = 60 * 1024 * 1024
    max_subject_total_bytes: int = 250 * 1024 * 1024
    stale_subjects_seconds: int = 600                        # a folder nobody is using is dropped after this long
    # The scratch copy of a repository that the headless review reads.
    max_copy_bytes: int = 200 * 1024 * 1024
    max_copy_files: int = 20_000
    max_review_bytes: int = 200_000                          # claude's saved report
    review_timeout: int = 900                                # seconds for one headless review
