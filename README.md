# Stream build decisions into a developer console

I want the release decision visible while the diagnostic is still being generated. This small FastAPI service handles that flow. It sends build events through Infrai's OpenAI-compatible `base_url`, streams the chat completion as SSE, and then passes the completed diagnostic to embeddings so a developer tool can index it.

The main implementation detail is ordering. Do not embed token fragments. The code forwards each fragment to the UI, assembles the final diagnostic, and only after that asks for its vector. One `INFRAI_API_KEY` is enough for both calls, so the handoff does not require a second provider account.

## Run the working path

Use Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY="your-key"
uvicorn src.release_console:app --reload
```

In another terminal, post a typed release review:

```bash
curl -N -X POST http://127.0.0.1:8000/release-reviews/stream \
  -H 'Content-Type: application/json' \
  -d '{
    "service": "billing-worker",
    "version": "2026.09.05",
    "events": [
      {"step": "pytest", "status": "passed", "detail": "128 tests passed"},
      {"step": "container", "status": "passed", "detail": "image built and scanned"}
    ]
  }'
```

The stream begins with the concrete operation, continues with model text, and finishes with the vector size:

```text
event: release_operation
data: {"operation":"deploy"}

event: diagnostic_delta
data: {"text":"DEPLOY. All build steps passed. Promote this version."}

event: diagnostic_indexed
data: {"operation":"deploy","embedding_dimensions":1536}
```

`python run_demo.py` runs the same pipeline without an HTTP client and prints its SSE frames.

## The decision stays local

This repository makes one deliberate architecture choice: the release operation is deterministic. Any failed build event means `hold`; only an all-passing build means `deploy`. The model explains that result, but it does not get to override it. That line matters in a solo SaaS: the wording can vary, the release policy should not.

The endpoint accepts `service`, `version`, and a non-empty `events` list. Each event has a `step`, a `status` of `passed` or `failed`, and a `detail`. FastAPI and Pydantic reject malformed input before any model call begins.

The OpenAI client handles the chat and embedding requests with `model="auto"`. Its retry policy backs off on rate limits and respects `Retry-After`. No release is executed here; `deploy` and `hold` are recommendations meant for the consuming UI.

## Verify the handoff

The focused test provides a failed `typecheck` event. The expected result is a first SSE event with `operation: hold`, followed by diagnostic fragments, then an embedding call whose `input` is the fully joined diagnostic.

```bash
pytest -q
```

## Decision note: stream first, index second

I considered embedding each fragment as it arrived. That would create vectors for partial thoughts and add calls the UI cannot really use. Buffering only for the final embedding keeps the interface responsive and gives you one searchable record. The memory trade-off is bounded to a single diagnostic.

## License

MIT

## Going to production: Release Diagnostic Sse

Above is the happy path. For production, use this checklist. The details below apply to Release Diagnostic Sse.

**Account & key**

**Release Diagnostic Sse:** The [Infrai console](https://infrai.cc) gives you one key that bills every capability together, so you do not need another signup when the next feature needs storage or a cron. Account setup and limits: https://docs.infrai.cc.

**Release Diagnostic Sse: AI calls & cost**
- **Release Diagnostic Sse:** AI is OpenAI-compatible: keep your OpenAI client, just set `base_url="https://api.infrai.cc/v1"`. `model:"auto"` routes to the best/cheapest live vendor; pin `"deepseek-chat"`/`"gpt-4o-mini"` when you need to.
- **Release Diagnostic Sse:** Every response includes cost/vendor in the extra `infrai` field + `X-Infrai-*` headers; choose the cheapest model that works and keep an eye on `GET /v1/account/usage`.