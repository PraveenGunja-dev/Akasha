from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import logging

from services.export_service import generate_docx_report, generate_pdf_report

router = APIRouter(prefix="/api/export", tags=["export"])
logger = logging.getLogger(__name__)


class ReportExportRequest(BaseModel):
    title: Optional[str] = "Akasha Executive Report"
    content: str
    metadata: Optional[Dict[str, Any]] = None
    images: Optional[List[str]] = []
    visualizations: Optional[List[Dict[str, Any]]] = []


@router.post("/docx")
def export_report_docx(req: ReportExportRequest):
    """
    Generates a branded Adani Word (.docx) report with watermark and embedded charts.
    """
    try:
        docx_bytes = generate_docx_report(
            title=req.title,
            content=req.content,
            metadata=req.metadata,
            images=req.images,
            visualizations=req.visualizations
        )
        return Response(
            content=docx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": 'attachment; filename="Akasha_Report.docx"'
            }
        )
    except Exception as e:
        logger.error(f"Failed to generate Word report: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate Word report: {str(e)}")


@router.post("/pdf")
def export_report_pdf(req: ReportExportRequest):
    """
    Generates a branded Adani PDF (.pdf) report with watermark and embedded charts.
    """
    try:
        pdf_bytes = generate_pdf_report(
            title=req.title,
            content=req.content,
            metadata=req.metadata,
            images=req.images,
            visualizations=req.visualizations
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'attachment; filename="Akasha_Report.pdf"'
            }
        )
    except Exception as e:
        logger.error(f"Failed to generate PDF report: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF report: {str(e)}")
