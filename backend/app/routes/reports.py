from fastapi import APIRouter, Response, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import os

from ..services.report import generate_qr_image, generate_pdf_report, get_reports_dir
from .cases import CASES_STORE
from .evidence import EVIDENCE_STORE
from .custody import AUDIT_LOGS_STORE

router = APIRouter(prefix="/reports", tags=["Forensic Reports"])

class ReportGenerateRequest(BaseModel):
    case_id: Optional[str] = "CV-2026-001"
    title: Optional[str] = "Forensic Investigation Report"

@router.get("/qr/{evidence_id}")
async def get_evidence_qr(evidence_id: str):
    """
    Generate and stream tamper-evident QR verification code for an evidence record.
    Returns HTTP 200 with image/png MIME type.
    """
    png_bytes = generate_qr_image(evidence_id)
    return Response(content=png_bytes, media_type="image/png", status_code=status.HTTP_200_OK)

@router.post("/generate", status_code=status.HTTP_200_OK)
async def generate_forensic_report(req: ReportGenerateRequest):
    """
    Generate tamper-evident, signed forensic PDF report containing:
    - Case details
    - Registered evidence items with cryptographic SHA-256 digests
    - Complete chain-of-custody transfer history
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

    report_path, _ = generate_pdf_report(
        case_id=cid,
        case_data=case_data,
        evidence_items=evidence_list,
        audit_logs=all_logs
    )

    return {
        "status": "success",
        "message": f"Forensic report for case {cid} generated successfully",
        "case_id": cid,
        "report_filename": os.path.basename(report_path),
        "report_path": report_path
    }

@router.get("/download/{filename}")
async def download_report(filename: str):
    """Download generated forensic report PDF."""
    reports_dir = get_reports_dir()
    file_path = reports_dir / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Report not found")
    return FileResponse(path=str(file_path), filename=filename, media_type="application/pdf")
