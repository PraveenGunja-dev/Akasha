from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from auth_claims import AuthenticatedIdentity
from database import get_db
import models
from security import get_current_user


router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/artifacts/{artifact_id}/download")
def download_report_artifact(
    artifact_id: str,
    db: Session = Depends(get_db),
    user: AuthenticatedIdentity = Depends(get_current_user),
):
    artifact = db.query(models.ReportArtifact).filter(
        models.ReportArtifact.artifact_id == artifact_id,
        models.ReportArtifact.owner_subject == user.subject,
        models.ReportArtifact.tenant_id == user.tenant_id,
    ).first()
    if artifact is None:
        raise HTTPException(status_code=404, detail="Report artifact not found.")
    if artifact.expires_at <= datetime.utcnow():
        try:
            Path(artifact.file_path).unlink(missing_ok=True)
        except OSError:
            pass
        db.delete(artifact)
        db.commit()
        raise HTTPException(status_code=410, detail="Report artifact has expired.")
    path = Path(artifact.file_path)
    if not path.is_file():
        raise HTTPException(status_code=410, detail="Report artifact is no longer available.")
    return FileResponse(
        path,
        media_type=artifact.mime_type,
        filename=artifact.filename,
    )
