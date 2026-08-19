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
    provider: Optional[str] = None
    model: Optional[str] = None


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
    service = AIAnalystService(db, provider_name=payload.provider, model=payload.model)

    async def event_stream():
        try:
            async for chunk in service.query(
                repository_id=repository_id,
                question=payload.question,
                snapshot_id=payload.snapshot_id,
            ):
                if isinstance(chunk, dict):
                    yield f"data: {json.dumps(chunk)}\n\n"
                elif isinstance(chunk, str):
                    try:
                        parsed = json.loads(chunk)
                        if isinstance(parsed, dict) and ("trace" in parsed or "error" in parsed or "content" in parsed):
                            yield f"data: {json.dumps(parsed)}\n\n"
                            continue
                    except Exception:
                        pass
                    data = json.dumps({"content": chunk})
                    yield f"data: {data}\n\n"
        except Exception as e:
            yield f'data: {json.dumps({"error": str(e)})}\n\n'
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
