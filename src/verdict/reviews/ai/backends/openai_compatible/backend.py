"""Any server that speaks the OpenAI chat-completions protocol, as a backend."""

from __future__ import annotations

import json
import time

import httpx
from pydantic import ValidationError

from verdict.reviews.ai.backends.openai_compatible.endpoint import Endpoint
from verdict.reviews.ai.backends.openai_compatible.replies import Reply, json_or_none, reply_text
from verdict.reviews.ai.backends.openai_compatible.retry import RetryPolicy
from verdict.reviews.ai.backends.openai_compatible.stream import StreamReader
from verdict.reviews.ai.contract import AIError, BaseBackend, ModelUnavailable, clean, extract_json


class OpenAIBackend(BaseBackend):
    """Strategy: any server speaking the OpenAI chat-completions protocol (api.airforce, OpenRouter, Groq, Ollama, ...).

    These models have no schema-constrained output, so the schema goes into the prompt, the reply is
    validated with pydantic, and one corrective retry is allowed. When a model is unavailable the next
    fallback model is tried.
    """

    batch = 10
    OUTPUT_TOKENS = 8000

    def __init__(self, base_url: str, api_key: str, model: str, http: httpx.Client | None = None,
                 fallbacks: list[str] | None = None, sleep=None, stream: bool = False):
        super().__init__()
        self.endpoint = Endpoint(base_url).validated()
        self.url, self.key, self.model = self.endpoint.chat_completions, api_key, model
        self.fallbacks, self.stream = list(fallbacks or []), stream
        self.retry = RetryPolicy()
        self.sleep = sleep or (lambda seconds: self.job.cancel.wait(seconds))  # wakes up at once on cancel
        self.http = http or httpx.Client(timeout=httpx.Timeout(300.0, connect=15.0))

    def _redact(self, text: str) -> str:
        return text.replace(self.key, "***") if self.key else text

    # ---------------------------------------------------------------- one HTTP exchange

    def _request(self, body: dict, headers: dict) -> Reply:
        """One HTTP exchange (runs in a worker thread so that a cancel is noticed)."""
        if not self.stream:
            response = self.http.post(self.url, json=body, headers=headers)
            return Reply(response.status_code, response.headers, json_or_none(response))
        with self.http.stream("POST", self.url, json={**body, "stream": True}, headers=headers) as response:
            if response.status_code >= 400 or "event-stream" not in response.headers.get("content-type", ""):
                response.read()  # an error, or a server that ignores `stream` and answers in one piece
                return Reply(response.status_code, response.headers, json_or_none(response))
            return StreamReader(self.model, self._check, self.job.notify).read(response)

    def _exchange(self, body: dict, headers: dict, attempt: int) -> Reply:
        """One try, announced, with the transport failures explained."""
        self._check()
        self.job.notify(f"Asking {self.model} (try {attempt + 1} of {self.retry.ATTEMPTS})… waiting for its answer"
                        + (" (streaming)" if self.stream else ""))
        started = time.monotonic()
        try:
            reply = self._cancellable(lambda: self._request(body, headers))
        except httpx.TimeoutException as exc:
            raise AIError("The AI server did not answer in time.") from exc
        except httpx.HTTPError as exc:
            raise AIError(f"Could not reach the AI server ({self.endpoint.host}) from the container.") from exc
        self.job.notify(f"{self.model} answered HTTP {reply.status} after {time.monotonic() - started:.0f}s")
        return reply

    def _send(self, body: dict, headers: dict) -> Reply:
        """The reply, after as many tries as a temporary failure deserves."""
        for attempt in range(self.retry.ATTEMPTS):
            reply = self._exchange(body, headers, attempt)
            if not self.retry.again(reply.status, attempt):
                break
            wait = self.retry.wait(reply, attempt)
            self.job.notify(f"Temporary problem on the server; retrying in {wait:.0f}s")
            self.sleep(wait)
        return reply

    def _post(self, messages: list[dict], json_mode: bool) -> dict:
        body = {"model": self.model, "messages": messages, "max_tokens": self.OUTPUT_TOKENS, "temperature": 0.2, "stream": False}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        headers = {"Content-Type": "application/json", **({"Authorization": f"Bearer {self.key}"} if self.key else {})}
        reply = self._send(body, headers)
        if reply.status == 400 and json_mode:
            return self._post(messages, json_mode=False)  # some servers reject response_format
        self._refuse_failure(reply)
        if reply.data is None:
            raise AIError("The AI server answered with something that is not JSON (is LLM_BASE_URL correct?).")
        return reply.data

    def _refuse_failure(self, reply: Reply) -> None:
        """Turn an error status into the exception that says what to do about it."""
        status = reply.status
        if status in (401, 403):
            raise AIError("The AI server rejected the API key (check LLM_API_KEY).")
        if status < 400:
            return
        detail = ""
        if isinstance(reply.data, dict):
            err = reply.data.get("error", {})
            detail = err.get("message", "") if isinstance(err, dict) else str(err)
        detail = self._redact(clean(detail, 200))
        if status == 404:
            raise ModelUnavailable(f"The AI server does not know this endpoint or model {self.model!r} (check LLM_BASE_URL and LLM_MODEL).")
        if status == 402:
            raise ModelUnavailable(f"Model {self.model!r} needs a paid balance on this server" + (f": {detail}" if detail else "."))
        if status == 429:
            raise ModelUnavailable("Rate limited by the AI server. Wait a minute and try again.")
        message = f"The AI server returned an error (HTTP {status})" + (f": {detail}" if detail else ".")
        raise ModelUnavailable(message) if status in self.retry.STATUSES else AIError(message)

    # ---------------------------------------------------------------- the answer as a schema

    def structured(self, system, digest_text, task, schema, usage):
        """Ask the current model; if it is unavailable, move on to the next fallback model."""
        errors: list[str] = []
        while True:
            try:
                return self._structured(system, digest_text, task, schema, usage)
            except ModelUnavailable as exc:
                errors.append(f"{self.model}: {exc}")
                if not self.fallbacks:
                    if len(errors) == 1:
                        raise
                    raise AIError("No configured model could answer. " + " | ".join(errors)) from exc
                previous, self.model = self.model, self.fallbacks.pop(0)
                self.job.notify(f"{previous} is unavailable ({exc}); switching to {self.model}")

    def _structured(self, system, digest_text, task, schema, usage):
        instructions = (
            f"{task}\n\nReply with ONLY one JSON object that matches this JSON Schema. No prose, no code fences. "
            f"Copy ids exactly as given.\n{json.dumps(schema.model_json_schema())}"
        )
        messages = [{"role": "system", "content": system}, {"role": "user", "content": digest_text + "\n\n" + instructions}]
        problem = ""
        for attempt in range(2):
            data = self._post(messages, json_mode=True)
            counts = (data.get("usage") if isinstance(data, dict) else None) or {}
            usage.input_tokens += int(counts.get("prompt_tokens") or 0)
            usage.output_tokens += int(counts.get("completion_tokens") or 0)
            text, finish = reply_text(data, self._redact)
            try:
                return schema.model_validate_json(extract_json(text))
            except (ValidationError, ValueError) as exc:
                problem = str(exc).splitlines()[0][:200]
                if finish == "length":
                    raise AIError("The model's answer was cut off. Try a model with a larger output limit, or lower LLM_MAX_CHARS.") from exc
                self.job.notify("The answer was not valid JSON; asking once more")
                messages += [{"role": "assistant", "content": text[:4000]},
                             {"role": "user", "content": f"That was not valid ({problem}). Reply again with only the corrected JSON object."}]
        raise AIError(f"The model did not return valid JSON in the expected format ({problem}).")
