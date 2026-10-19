"""Print the model ids from an OpenAI-style /models response read on stdin (used by `make models`)."""

import json
import sys

HINT_FIELDS = ("free", "tier", "plan", "premium", "pricing", "price", "context_length", "context_window", "max_context")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        print("The server did not answer with JSON. Check LLM_BASE_URL and LLM_API_KEY in .env.", file=sys.stderr)
        return 1
    if isinstance(payload, dict) and "error" in payload:
        error = payload["error"]
        print("The server refused: " + str(error.get("message", error) if isinstance(error, dict) else error)[:200], file=sys.stderr)
        return 1
    models = payload.get("data", payload) if isinstance(payload, dict) else payload
    rows = []
    for model in models if isinstance(models, list) else []:
        if isinstance(model, str):
            rows.append((model, ""))
        elif isinstance(model, dict) and model.get("id"):
            extra = ", ".join(f"{k}={model[k]}" for k in HINT_FIELDS if k in model and model[k] not in (None, ""))
            rows.append((str(model["id"]), extra))
    if not rows:
        print("No models found in the answer.", file=sys.stderr)
        return 1
    for model_id, extra in sorted(rows):
        print(f"{model_id}   {extra}".rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
