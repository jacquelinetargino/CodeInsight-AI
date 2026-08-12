import io
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.analysis import Analysis
from app.models.enums import AnalysisStatus
from app.models.user import User
from app.services import pdf_service

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/{analysis_id}/pdf")
async def download_analysis_pdf(
    analysis_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    result = await db.execute(
        select(Analysis)
        .where(Analysis.id == analysis_id)
        .options(
            selectinload(Analysis.results),
            selectinload(Analysis.suggestions),
            selectinload(Analysis.repository),
        )
    )
    analysis = result.scalar_one_or_none()
    if analysis is None or analysis.repository.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Análise não encontrada")
    if analysis.status != AnalysisStatus.DONE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A análise ainda não foi concluída")

    pdf_bytes = pdf_service.render_analysis_pdf(analysis, analysis.repository.full_name)
    filename = f"codeinsight-{analysis.repository.full_name.replace('/', '-')}.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
