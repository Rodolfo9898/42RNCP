"""Stand-ins for an OpenAI-compatible server."""

import httpx

from verdict.reviews import ai
from verdict.reviews.digest import Digest


KEY = "sk-air-SECRET-1234567890"


def digest():
    return Digest(text="<repository>\n<file path=\"main.c\" lines=\"5\">\n    1| int main(void)\n</file>\n</repository>",
                  lines={"main.c": 5, "Makefile": 3}, included=["main.c"])


def backend(handler, base="https://api.airforce/v1", key=KEY, fallbacks=None, waits=None):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    record = waits if waits is not None else []
    return ai.OpenAIBackend(base, key, "deepseek-v3", http=http, fallbacks=fallbacks, sleep=record.append)


def completion(content, finish="stop", prompt=1200, out=300):
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": finish}],
                                     "usage": {"prompt_tokens": prompt, "completion_tokens": out}})


ANALYSIS = {
    "overview": {"purpose": "Prints ok.", "languages": ["C"], "build_and_run": "make", "components": [{"path": "main.c", "role": "entry"}],
                 "notable": [], "not_found": ["README.md"]},
    "improvements": [{"category": "logic", "priority": "high", "title": "Unchecked write", "detail": "d",
                      "evidence": [{"file": "main.c", "line": 1}, {"file": "invented.c", "line": 4}]}],
}


def run_analysis(b):
    usage = ai.Usage()
    overview, improvements = ai.analyze(b, digest(), subjects=["p.pdf"], summary="s", known_titles=[], usage=usage)
    return overview, improvements, usage


def reply(payload):
    return httpx.Response(200, json=payload)
