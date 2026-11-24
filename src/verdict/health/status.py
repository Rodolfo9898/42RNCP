"""Is the app up, is the sandbox up, and which AI is configured."""

from __future__ import annotations

from verdict.reviews import ai as ai_mod


class HealthService:
    def __init__(self, sandbox) -> None:
        self.sandbox = sandbox

    def status(self) -> dict:
        return {"status": "ok", "sandbox": bool(self.sandbox and self.sandbox.healthy()),
                "llm": {"configured": ai_mod.configured(), "model": ai_mod.model_name(), "provider": ai_mod.provider(),
                        "host": ai_mod.endpoint_host()}}
