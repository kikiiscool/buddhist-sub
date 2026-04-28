"""WebSocket progress endpoint.

Worker publishes JSON events to Redis pub/sub channel `job:{job_id}`.
This endpoint subscribes and forwards events to the connected client.
"""
import asyncio
import json
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

from app.core.config import get_settings

router = APIRouter()
settings = get_settings()


@router.websocket("/ws/jobs/{job_id}")
async def ws_job(ws: WebSocket, job_id: uuid.UUID):
    await ws.accept()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    pubsub = redis.pubsub()
    channel = f"job:{job_id}"
    await pubsub.subscribe(channel)

    async def reader():
        async for msg in pubsub.listen():
            if msg.get("type") != "message":
                continue
            try:
                await ws.send_text(msg["data"])
            except WebSocketDisconnect:
                return

    async def writer():
        while True:
            try:
                raw = await ws.receive_text()
            except WebSocketDisconnect:
                return
            # Forward client commands (pause/resume/edit) to a control channel.
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            await redis.publish(f"job:{job_id}:control", json.dumps(data))

    try:
        await asyncio.gather(reader(), writer())
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
        await redis.close()
