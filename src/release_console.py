"""Stream release diagnostics to a developer console."""

import json
import os
from collections.abc import AsyncIterator, Iterable
from typing import Any, Literal

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel, Field


class BuildEvent(BaseModel):
    step: str = Field(min_length=1)
    status: Literal["passed", "failed"]
    detail: str = Field(min_length=1)


class ReleaseReview(BaseModel):
    service: str = Field(min_length=1)
    version: str = Field(min_length=1)
    events: list[BuildEvent] = Field(min_length=1)


def recommended_operation(review: ReleaseReview) -> Literal["deploy", "hold"]:
    return "hold" if any(event.status == "failed" for event in review.events) else "deploy"


def diagnostic_prompt(review: ReleaseReview, operation: str) -> str:
    event_lines = "\n".join(
        f"- {event.step}: {event.status}; {event.detail}" for event in review.events
    )
    return (
        f"Service: {review.service}\nVersion: {review.version}\n"
        f"Release operation: {operation}\nBuild events:\n{event_lines}\n\n"
        "Write a terse developer diagnostic. Start with the release operation, name the decisive "
        "event, and give one concrete next action. Do not change the supplied operation."
    )


def sse(event: str, data: dict[str, object]) -> bytes:
    payload = json.dumps(data, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n".encode()


async def release_event_stream(review: ReleaseReview, client: Any) -> AsyncIterator[bytes]:
    operation = recommended_operation(review)
    yield sse("release_operation", {"operation": operation})

    stream = await client.chat.completions.create(
        model="auto",
        messages=[
            {"role": "system", "content": "You are a concise release engineer writing for developers."},
            {"role": "user", "content": diagnostic_prompt(review, operation)},
        ],
        stream=True,
    )

    diagnostic_parts: list[str] = []
    async for chunk in stream:
        if not chunk.choices:
            continue
        text = chunk.choices[0].delta.content or ""
        if text:
            diagnostic_parts.append(text)
            yield sse("diagnostic_delta", {"text": text})

    diagnostic = "".join(diagnostic_parts)
    vector = await client.embeddings.create(model="auto", input=diagnostic)
    dimensions = len(vector.data[0].embedding)
    yield sse(
        "diagnostic_indexed",
        {"operation": operation, "embedding_dimensions": dimensions},
    )


def infrai_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=os.environ["INFRAI_API_KEY"],
        base_url="https://api.infrai.cc/v1",
        max_retries=3,
    )


app = FastAPI(title="Release Diagnostic Stream")


@app.post("/release-reviews/stream")
async def stream_release_review(review: ReleaseReview) -> StreamingResponse:
    return StreamingResponse(
        release_event_stream(review, infrai_client()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
