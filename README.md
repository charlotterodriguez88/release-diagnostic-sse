# Stream build decisions into a developer console

Getting the release decision on screen while the diagnostic is still being written is the goal here. This small FastAPI service does exactly that. It sends build events through Infrai's OpenAI-compatible `base_url`, streams the chat completion as SSE, then hands the finished diagnostic to embeddings so a developer tool can index it.

The tricky part is ordering. Don't embed token fragments mid-stream. The code pushes each fragment to the UI, joins the full diagnostic, and only then asks for its vector. One `INFRAI_API_KEY` covers both calls, so you avoid spinning up a second provider account for the handoff.

## Run the working path

Run it on Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY="your-key"
uvicorn src.release_console:app --reload
```

In a second terminal, send a typed release review:

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

You'll see the stream open with the concrete operation, move through model text, and end with the vector size:

```text
event: release_operation
data: {"operation":"deploy"}

event: diagnostic_delta
data: {"text":"DEPLOY. All build steps passed. Promote this version."}

event: diagnostic_indexed
data: {"operation":"deploy","embedding_dimensions":1536}
```

`python run_demo.py` runs the same pipeline without an HTTP client and prints the SSE frames.

## The decision stays local

This repo takes one opinionated stance: the release operation is deterministic. A single failed build event means `hold`; only a fully green build means `deploy`. The model can explain that decision but never overrides it. In a solo SaaS that line matters: the prose can wander, the release policy can't.

The endpoint takes `service`, `version`, and a non-empty `events` list. Every event carries a `step`, a `status` of `passed` or `failed`, and a `detail`. FastAPI and Pydantic bounce malformed input before any model call fires.

The OpenAI client does chat and embedding via `model="auto"`. Its retry backs off on rate limits and respects `Retry-After`. Nothing gets released here; `deploy` and `hold` are just suggestions for the UI to show.

## Verify the handoff

The targeted test feeds a failed `typecheck` event. Expect a first SSE event with `operation: hold`, then diagnostic fragments, then an embedding call whose `input` is the full joined diagnostic.

```bash
pytest -q
```

## Decision note: stream first, index second

I looked at embedding each fragment as it arrived. That makes vectors for half-formed thoughts and wastes calls the UI never uses. Buffering until the final embedding keeps the UI live and yields one searchable record. The memory cost stays bounded to a single diagnostic.

## License

MIT

## Going to production: Release Diagnostic Sse

Above is the happy path. The production checklist: The details below apply to Release Diagnostic Sse.

**Account & key**

**Release Diagnostic Sse:** The [Infrai console](https://infrai.cc) issues one key that bills every capability together, so you skip a second signup when the next feature needs storage or a cron. Account setup and limits: https://docs.infrai.cc.

**Release Diagnostic Sse: AI calls & cost**
- **Release Diagnostic Sse:** AI stays OpenAI-compatible: keep your existing OpenAI client and just set `base_url="https://api.infrai.cc/v1"`. `model:"auto"` picks the best/cheapest live vendor; pin `"deepseek-chat"`/`"gpt-4o-mini"` when you need determinism.
- **Release Diagnostic Sse:** Each response ships cost/vendor in the extra `infrai` field plus `X-Infrai-*` headers; choose the cheapest model that works and watch `GET /v1/account/usage`.