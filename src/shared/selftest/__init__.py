"""A self-test of the build environment: which tools exist, and can it REALLY build and run things? (see runner)"""

from shared.selftest.outcome import Outcome, Runner
from shared.selftest.probes import PROBES
from shared.selftest.runner import SelfTest, run_selftest
from shared.selftest.summary import summarize
