"""Stand-ins for the Anthropic client and for a digest."""

from types import SimpleNamespace

from verdict.reviews import ai
from verdict.reviews.digest import Digest


def digest():
    return Digest(text="<repository>\n<file path=\"a.c\" lines=\"10\">\n    1| int x;\n</file>\n</repository>", lines={"a.c": 10, "Makefile": 3},
                  included=["a.c", "Makefile"])


def usage(i=100, o=50):
    return SimpleNamespace(input_tokens=i, output_tokens=o, cache_creation_input_tokens=0, cache_read_input_tokens=0)


def response(parsed, stop="end_turn", **kw):
    return SimpleNamespace(stop_reason=stop, parsed_output=parsed, usage=usage(), stop_details=kw.get("stop_details"))


class FakeClient:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []
        self.messages = self

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def overview(**kw):
    base = dict(purpose="Sorts stacks.", languages=["C"], build_and_run="make", components=[ai.ComponentOut(path="a.c", role="core")],
                notable=[], not_found=[])
    return ai.OverviewOut(**{**base, **kw})


def cite(file="a.c", line=3):
    return ai.CitationOut(file=file, line=line)
