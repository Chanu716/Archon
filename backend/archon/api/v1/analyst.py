import uuid
import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from archon.api.deps import get_db
from archon.services.analyst import AIAnalystService

router = APIRouter()


class AnalystQueryRequest(BaseModel):
    question: str
    snapshot_id: Optional[uuid.UUID] = None


@router.post("/repositories/{repository_id}/analyst/query")
async def analyst_query(
    repository_id: uuid.UUID,
    payload: AnalystQueryRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Streams an AI analyst response grounded in deterministic evidence.
    Returns an SSE stream of JSON deltas.
    Each chunk is: data: {"content": "..."}\n\n  or  data: {"trace": "..."}\n\n
    """
    service = AIAnalystService(db)

    async def event_stream():
        try:
            async for chunk in service.query(
                repository_id=repository_id,
                question=payload.question,
                snapshot_id=payload.snapshot_id,
            ):
                if isinstance(chunk, str):
                    # Could be raw text or a JSON blob from the LLM
                    # Wrap it into SSE content event
                    data = json.dumps({"content": chunk})
                    yield f"data: {data}\n\n"
                elif isinstance(chunk, dict):
                    # Already a structured dict (trace, error, etc.)
                    yield f"data: {json.dumps(chunk)}\n\n"
        except Exception as e:
            yield f'data: {json.dumps({"error": str(e)})}\n\n'
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
