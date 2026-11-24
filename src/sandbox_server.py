"""Main of the sandbox (the `sandbox` container): runs commands for the review, with no network. Standard library only."""

import os

from sandbox.service.serve import serve

if __name__ == "__main__":
    serve(os.environ)
