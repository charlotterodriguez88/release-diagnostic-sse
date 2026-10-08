"""Print the live SSE feed for one release review."""

import asyncio
import sys

from src.release_console import BuildEvent, ReleaseReview, infrai_client, release_event_stream


async def main() -> None:
    review = ReleaseReview(
        service="billing-worker",
        version="2026.09.05",
        events=[
            BuildEvent(step="pytest", status="passed", detail="128 tests passed"),
            BuildEvent(step="container", status="passed", detail="image built and scanned"),
        ],
    )
    async for frame in release_event_stream(review, infrai_client()):
        sys.stdout.buffer.write(frame)
        sys.stdout.buffer.flush()


if __name__ == "__main__":
    asyncio.run(main())
