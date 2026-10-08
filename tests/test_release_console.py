from types import SimpleNamespace

import pytest

from src.release_console import BuildEvent, ReleaseReview, release_event_stream


class FakeChatCompletions:
    async def create(self, **kwargs: object) -> object:
        async def chunks():
            for text in ("HOLD. ", "The typecheck step failed. Fix the import and rebuild."):
                yield SimpleNamespace(choices=[])
                yield SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content=text))]
                )

        return chunks()


class FakeEmbeddings:
    def __init__(self) -> None:
        self.input_text = ""

    async def create(self, **kwargs: object) -> object:
        self.input_text = str(kwargs["input"])
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.2, 0.4, 0.6])])


class FakeClient:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=FakeChatCompletions())
        self.embeddings = FakeEmbeddings()


@pytest.mark.asyncio
async def test_failed_build_is_held_and_complete_diagnostic_is_embedded() -> None:
    review = ReleaseReview(
        service="web-console",
        version="sha-7ad9",
        events=[
            BuildEvent(step="unit tests", status="passed", detail="42 passed"),
            BuildEvent(step="typecheck", status="failed", detail="unresolved import in toolbar.py"),
        ],
    )
    client = FakeClient()

    frames = [frame.decode() async for frame in release_event_stream(review, client)]

    assert 'event: release_operation\ndata: {"operation":"hold"}' in frames[0]
    assert client.embeddings.input_text == (
        "HOLD. The typecheck step failed. Fix the import and rebuild."
    )
    assert 'event: diagnostic_indexed\ndata: {"operation":"hold","embedding_dimensions":3}' in frames[-1]
