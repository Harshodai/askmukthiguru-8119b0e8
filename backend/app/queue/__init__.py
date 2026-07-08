from app.queue.request_queue import BaseRequestQueue, QueueItem, QueueStatus, RequestPriority
from app.queue.in_process_queue import InProcessQueue

__all__ = ["BaseRequestQueue", "InProcessQueue", "QueueItem", "QueueStatus", "RequestPriority"]


if __name__ == "__main__":
    import asyncio

    q = InProcessQueue()
    asyncio.run(q.start())
    jid, depth = asyncio.run(q.enqueue({"test": True}, "selfcheck"))
    print(f"InProcessQueue: enqueued {jid}, depth={depth}")
    item = asyncio.run(q.dequeue("selfcheck"))
    assert item is None
    health = asyncio.run(q.health())
    print(f"Health: {health}")
    asyncio.run(q.stop())
    print("Queue self-check: OK")
