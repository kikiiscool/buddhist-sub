import uuid
from fastapi import APIRouter

from app.core.storage import presigned_put
from app.schemas.job import UploadInit, UploadInitOut

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post("/init", response_model=UploadInitOut)
async def init_upload(payload: UploadInit) -> UploadInitOut:
    """Issue a presigned PUT URL. Frontend uploads MP3 directly to S3/MinIO."""
    audio_key = f"audio/{uuid.uuid4()}/{payload.filename}"
    url = presigned_put(audio_key, payload.content_type)
    return UploadInitOut(audio_key=audio_key, upload_url=url)
