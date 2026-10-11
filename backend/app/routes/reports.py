from fastapi import APIRouter, Response, HTTPException, status, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import os
import datetime

from ..services.report import generate_qr_image, generate_pdf_report, get_reports_dir
from ..security.auth import get_current_user
from ..security.permissions import require_role, UserRole
from .cases import CASES_STORE
from .evidence import EVIDENCE_STORE
from .custody import AUDIT_LOGS_STORE

router = APIRouter(prefix="/reports", tags=["Forensic Reports"])

# In-memory store preserving all generated report records without destructive overwrites
REPORTS_REGISTRY: list[dict] = []

class ReportGenerateRequest(BaseModel):
    case_id: Optional[str] = "CV-2026-001"
    title: Optional[str] = "Forensic Investigation Report"

@router.get("/qr/{evidence_id}")
async def get_evidence_qr(evidence_id: str):
    """
    Generate and stream tamper-evident QR verification code for an evidence record.
    Publicly accessible for physical forensic tags and mobile verification badges.
    Returns HTTP 200 with image/png MIME type.
    """
    png_bytes = generate_qr_image(evidence_id)
    return Response(content=png_bytes, media_type="image/png", status_code=status.HTTP_200_OK)

@router.post("/generate", status_code=status.HTTP_200_OK)
async def generate_forensic_report(
    req: ReportGenerateRequest,
    current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.INVESTIGATOR, UserRole.ANALYST]))
):
    """
    Generate tamper-evident, signed forensic PDF report containing:
    - Case details
    - Registered evidence items with cryptographic SHA-256 digests
    - Complete chain-of-custody transfer history
    Allowed roles: ADMIN, INVESTIGATOR, ANALYST.
    """
    cid = req.case_id or "CV-2026-001"

    # Retrieve case metadata
    case_data = CASES_STORE.get(cid, {"case_id": cid, "title": req.title or "Forensic Investigation"})

    # Retrieve relevant evidence
    evidence_list = [ev for ev in EVIDENCE_STORE.values() if ev.get("case_id") == cid]
    if not evidence_list and EVIDENCE_STORE:
        evidence_list = list(EVIDENCE_STORE.values())

    # Retrieve relevant audit logs
    all_logs = []
    for logs in AUDIT_LOGS_STORE.values():
        all_logs.extend(logs)

    try:
        report_path, _, report_hash = generate_pdf_report(
            case_id=cid,
            case_data=case_data,
            evidence_items=evidence_list,
            audit_logs=all_logs,
            preserve_existing=True
        )
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        rep_id = f"REP-{cid}-{len(REPORTS_REGISTRY) + 1:03d}"
        report_record = {
            "report_id": rep_id,
            "case_id": cid,
            "report_filename": os.path.basename(report_path),
            "report_path": report_path,
            "report_hash": report_hash,
            "generated_at": now,
            "status": "success"
        }
        REPORTS_REGISTRY.append(report_record)

        return {
            "status": "success",
            "message": f"Forensic report for case {cid} generated successfully",
            "case_id": cid,
            "report_id": rep_id,
            "report_filename": os.path.basename(report_path),
            "report_hash": report_hash,
            "report_path": report_path
        }
    except Exception as e:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        err_record = {
            "report_id": f"REP-ERR-{len(REPORTS_REGISTRY) + 1:03d}",
            "case_id": cid,
            "status": "failed",
            "error": str(e),
            "generated_at": now
        }
        REPORTS_REGISTRY.append(err_record)
        raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)}")


@router.get("/download/{filename}")
async def download_report(
    filename: str,
    current_user: dict = Depends(get_current_user)
):
    """Download generated forensic report PDF with path traversal defense. Allowed roles: All authenticated."""
    if not filename or ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=404, detail="Invalid report filename")

    reports_dir = get_reports_dir()
    file_path = (reports_dir / os.path.basename(filename)).resolve()

    if not str(file_path).startswith(str(reports_dir.resolve())):
        raise HTTPException(status_code=404, detail="Access denied")

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Report not found")
    return FileResponse(path=str(file_path), filename=file_path.name, media_type="application/pdf")


@router.get("/history/{case_id}")
async def get_report_history(
    case_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Retrieve history of all generated forensic reports for a case. Preserves versioning."""
    return [r for r in REPORTS_REGISTRY if r.get("case_id") == case_id]
