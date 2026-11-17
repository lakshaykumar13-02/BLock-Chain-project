import os
import io
import re
import hashlib
import datetime
import time
import uuid
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Response, HTTPException, status, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..services.report import (
    generate_qr_image,
    generate_pdf_report,
    get_reports_dir,
    resolve_verification_url
)
from ..security.auth import get_current_user
from ..security.permissions import require_role, UserRole
from ..database.mongodb import db_client
from .cases import CASES_STORE
from .evidence import EVIDENCE_STORE
from .custody import AUDIT_LOGS_STORE
from .verification import verify_evidence_integrity, VerificationRequest
from ..services.audit_trail import verify_custody_audit_trail, get_stored_custody_events

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["Forensic Reports"])

# In-memory store preserving report records for hybrid/resilient fallback
REPORTS_REGISTRY: list[dict] = []

class ReportGenerateRequest(BaseModel):
    case_id: Optional[str] = "CV-2026-001"
    evidence_id: Optional[str] = None
    title: Optional[str] = "Forensic Investigation Report"
    allow_incomplete: Optional[bool] = False

class ReportVerifyRequest(BaseModel):
    report_id: Optional[str] = None
    filename: Optional[str] = None
    expected_hash: Optional[str] = None
    check_current_evidence: Optional[bool] = True

def _validate_safe_identifier(val: str, name: str = "Identifier") -> str:
    """Validate identifier against path traversal and forbidden characters."""
    if not val or not isinstance(val, str):
        raise HTTPException(status_code=400, detail=f"{name} must be provided")
    cleaned = val.strip()
    if not cleaned or len(cleaned) > 128:
        raise HTTPException(status_code=400, detail=f"Invalid {name} length")
    if ".." in cleaned or "/" in cleaned or "\\" in cleaned or "\0" in cleaned:
        raise HTTPException(status_code=400, detail=f"Invalid characters in {name} (path traversal prohibited)")
    if not re.match(r"^[A-Za-z0-9_\-\.]+$", cleaned):
        raise HTTPException(status_code=400, detail=f"Invalid characters in {name}")
    return cleaned

def _sanitize_report_record(rec: dict) -> dict:
    """Sanitize report record for public/client consumption (strip absolute paths & db internal IDs)."""
    clean = {k: v for k, v in rec.items() if k not in ("_id", "report_path")}
    clean["report_filename"] = os.path.basename(rec.get("report_filename", ""))
    return clean

# -----------------------------------------------------------------------------
# 1. QR CODE STREAMING ENDPOINTS
# -----------------------------------------------------------------------------

@router.get("/qr/{evidence_id}")
async def get_evidence_qr(evidence_id: str):
    """
    Generate and stream tamper-evident QR verification code for an evidence record.
    Publicly accessible for physical forensic tags and mobile verification badges.
    Returns HTTP 200 with image/png MIME type.
    """
    safe_eid = _validate_safe_identifier(evidence_id, "Evidence ID")
    png_bytes = generate_qr_image(safe_eid, is_report=False)
    return Response(content=png_bytes, media_type="image/png", status_code=status.HTTP_200_OK)

@router.get("/qr/report/{report_id}")
async def get_report_qr(report_id: str):
    """
    Generate and stream tamper-evident QR verification code for a specific report.
    Publicly accessible for printed report cover pages.
    Returns HTTP 200 with image/png MIME type.
    """
    safe_rid = _validate_safe_identifier(report_id, "Report ID")
    png_bytes = generate_qr_image(safe_rid, is_report=True)
    return Response(content=png_bytes, media_type="image/png", status_code=status.HTTP_200_OK)

# -----------------------------------------------------------------------------
# 2. FORENSIC PDF REPORT GENERATION
# -----------------------------------------------------------------------------

@router.post("/generate", status_code=status.HTTP_200_OK)
async def generate_forensic_report(
    req: ReportGenerateRequest,
    current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.INVESTIGATOR, UserRole.ANALYST]))
):
    """
    Generate a verifiable, reproducible forensic PDF report for an existing evidence record.
    Pre-Report Verification Workflow:
    1. Resolve evidence and case using persistent storage when required.
    2. Recalculate SHA-256 fresh from actual physical evidence file.
    3. Independently verify evidence ledger on blockchain contract.
    4. Independently validate custody audit trail continuity, sequence, and hashes.
    5. Faithfully represent outcomes in generated PDF.
    6. Roll back newly created PDF file if metadata persistence fails.
    Allowed roles: ADMIN, INVESTIGATOR, ANALYST.
    """
    # Step 0: Check persistent storage requirement
    if db_client.require_persistent_storage and not db_client.is_connected():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Persistent database storage is required but MongoDB is disconnected. Report generation refused."
        )

    cid = req.case_id or "CV-2026-001"
    if cid:
        cid = _validate_safe_identifier(cid, "Case ID")

    # Step 1: Resolve Case Metadata
    case_data = None
    if db_client.is_connected():
        try:
            case_data = await db_client.cases.find_one({"case_id": cid}, {"_id": 0})
        except Exception as e:
            if db_client.require_persistent_storage:
                raise HTTPException(status_code=503, detail=f"Database query failed: {e}")

    if not case_data and not db_client.require_persistent_storage:
        case_data = CASES_STORE.get(cid)

    if not case_data:
        case_data = {
            "case_id": cid,
            "title": req.title or "Forensic Investigation",
            "description": "Digital forensic investigation record",
            "lead_investigator": current_user.get("sub", "investigator1")
        }

    # Step 2: Resolve Evidence Items
    evidence_list = []
    target_evidence_id = None
    if req.evidence_id:
        target_evidence_id = _validate_safe_identifier(req.evidence_id, "Evidence ID")
        ev_record = None
        if db_client.is_connected():
            try:
                ev_record = await db_client.evidence.find_one({"evidence_id": target_evidence_id}, {"_id": 0})
            except Exception as e:
                if db_client.require_persistent_storage:
                    raise HTTPException(status_code=503, detail=f"Database query failed: {e}")

        if not ev_record and not db_client.require_persistent_storage:
            ev_record = EVIDENCE_STORE.get(target_evidence_id)

        if not ev_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Evidence '{target_evidence_id}' not found in registry"
            )

        evidence_list = [ev_record]
        if ev_record.get("case_id"):
            cid = ev_record.get("case_id")
    else:
        # Retrieve evidence associated with case
        if db_client.is_connected():
            try:
                cursor = db_client.evidence.find({"case_id": cid}, {"_id": 0})
                async for doc in cursor:
                    evidence_list.append(doc)
            except Exception as e:
                if db_client.require_persistent_storage:
                    raise HTTPException(status_code=503, detail=f"Database query failed: {e}")

        if not evidence_list and not db_client.require_persistent_storage:
            evidence_list = [ev for ev in EVIDENCE_STORE.values() if ev.get("case_id") == cid]
            if not evidence_list and EVIDENCE_STORE:
                evidence_list = list(EVIDENCE_STORE.values())

    primary_ev_id = evidence_list[0].get("evidence_id") if evidence_list else (target_evidence_id or cid)

    # Step 3: Run Tripartite Evidence Verification
    ev_verif = None
    if evidence_list:
        ev_verif = await verify_evidence_integrity(VerificationRequest(
            evidence_id=primary_ev_id,
            allow_offline_fallback=False
        ))
    else:
        ev_verif = {
            "verification_status": "NOT_FOUND",
            "verified": False,
            "tampered": False,
            "physical_file_hash": None,
            "database_hash": None,
            "blockchain_hash": None,
            "technical_error": "NO_EVIDENCE_ATTACHED",
            "explanation": f"No registered evidence items found for case {cid}"
        }

    # Step 4: Run Custody Audit Trail Verification & Event Retrieval
    custody_verif = await verify_custody_audit_trail(
        evidence_id=primary_ev_id,
        require_blockchain=False,
        allow_offline_fallback=False,
        allow_in_memory_fallback=(not db_client.require_persistent_storage)
    )

    all_logs = await get_stored_custody_events(
        primary_ev_id,
        allow_in_memory_fallback=(not db_client.require_persistent_storage)
    )
    if not all_logs and not db_client.require_persistent_storage:
        for logs in AUDIT_LOGS_STORE.values():
            all_logs.extend(logs)

    # Step 5: Synthesize Verification Outcomes & Discrepancies
    discrepancies: List[str] = []
    ev_stat = ev_verif.get("verification_status", "UNAVAILABLE")
    cust_stat = custody_verif.get("verification_status", "UNAVAILABLE")

    if ev_stat == "TAMPERED":
        discrepancies.append(f"Evidence Tampering: {ev_verif.get('explanation') or 'File hash differs from blockchain anchor.'}")
    elif ev_stat == "INCONSISTENT":
        discrepancies.append(f"Evidence Inconsistency: {ev_verif.get('explanation') or 'Database hash disagrees with blockchain.'}")
    elif ev_stat == "UNAVAILABLE":
        discrepancies.append(f"Evidence Verification Source Unavailable: {ev_verif.get('technical_error') or 'Blockchain RPC offline.'}")
    elif ev_stat == "NOT_FOUND":
        discrepancies.append(f"Evidence Not Found: {ev_verif.get('explanation') or 'Evidence record absent.'}")

    if cust_stat == "TAMPERED":
        discrepancies.append(f"Custody Audit Tampering: {custody_verif.get('failure_reason') or 'Custody event hash modified or broken link.'}")
    elif cust_stat == "INCONSISTENT":
        discrepancies.append(f"Custody Audit Inconsistency: {custody_verif.get('failure_reason') or 'Custody sequence gap or unanchored history.'}")
    elif cust_stat == "UNAVAILABLE":
        discrepancies.append(f"Custody Audit Source Unavailable: {custody_verif.get('failure_reason') or 'Audit verification infrastructure offline.'}")

    # Determine overall status: Never convert TAMPERED, INCONSISTENT, NOT_FOUND, or UNAVAILABLE into VERIFIED
    if ev_stat == "TAMPERED" or cust_stat == "TAMPERED":
        overall_status = "TAMPERED"
    elif ev_stat == "INCONSISTENT" or cust_stat == "INCONSISTENT":
        overall_status = "INCONSISTENT"
    elif ev_stat == "UNAVAILABLE" or cust_stat == "UNAVAILABLE":
        overall_status = "UNAVAILABLE"
    elif ev_stat == "NOT_FOUND" or cust_stat == "NOT_FOUND":
        overall_status = "NOT_FOUND"
    elif ev_stat == "VERIFIED" and cust_stat == "VERIFIED":
        overall_status = "VERIFIED"
    else:
        overall_status = "UNVERIFIED"

    report_status_label = "VERIFIED" if overall_status == "VERIFIED" else f"INCOMPLETE / UNVERIFIED ({overall_status})"

    # Step 6: Generate Unique Report ID & Resolve QR Destination
    rand_suffix = uuid.uuid4().hex[:6].upper()
    seq_num = len(REPORTS_REGISTRY) + 1
    rep_id = f"REP-{cid}-{seq_num:03d}-{rand_suffix}"

    qr_url, is_local_qr, _ = resolve_verification_url(rep_id, is_report=True)

    blockchain_metadata = {
        "chain_id": ev_verif.get("chain_id") or "1337",
        "contract_address": ev_verif.get("contract_address") or "UNAVAILABLE",
        "tx_hash": ev_verif.get("tx_hash") or (evidence_list[0].get("blockchain_tx") if evidence_list else None) or "NOT FOUND",
        "block_number": (evidence_list[0].get("block_number") if evidence_list else None) or "UNAVAILABLE",
        "receipt_status": "Confirmed (0x1)" if overall_status == "VERIFIED" else (ev_verif.get("technical_error") or "UNCONFIRMED")
    }

    # Step 7: Generate PDF Report with ReportLab
    report_path = None
    try:
        report_path, _, report_hash = generate_pdf_report(
            case_id=cid,
            case_data=case_data,
            evidence_items=evidence_list,
            audit_logs=all_logs,
            preserve_existing=True,
            report_id=rep_id,
            schema_version="1.0.0",
            verification_results=ev_verif,
            custody_verification=custody_verif,
            blockchain_metadata=blockchain_metadata,
            discrepancies=discrepancies,
            report_status=report_status_label,
            qr_url=qr_url,
            is_local_qr=is_local_qr
        )
    except Exception as e:
        logger.error(f"PDF generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")

    # Step 8: Persist Metadata with Rollback Safety
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    report_record = {
        "report_id": rep_id,
        "schema_version": "1.0.0",
        "case_id": cid,
        "evidence_id": primary_ev_id,
        "report_filename": os.path.basename(report_path),
        "report_path": report_path,
        "report_hash": report_hash,
        "verification_status": overall_status,
        "report_label": report_status_label,
        "evidence_verification": ev_verif,
        "custody_verification": custody_verif,
        "blockchain_metadata": blockchain_metadata,
        "discrepancies": discrepancies,
        "generated_at": now,
        "generated_by": current_user.get("sub", "investigator1"),
        "status": "success"
    }

    try:
        if db_client.is_connected():
            await db_client.reports.insert_one(dict(report_record))
        elif db_client.require_persistent_storage:
            raise RuntimeError("Persistent database storage is required but MongoDB is disconnected")
    except Exception as e:
        # Atomic Rollback: Clean up ONLY the newly created report file; NEVER delete evidence!
        if report_path and os.path.exists(report_path):
            try:
                os.remove(report_path)
                logger.info(f"Cleaned up orphaned report file after DB persistence error: {report_path}")
            except Exception as cleanup_err:
                logger.warning(f"Failed to clean up report file {report_path}: {cleanup_err}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE if db_client.require_persistent_storage else status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Report metadata persistence failed: {str(e)}"
        )

    # In-memory synchronization for hybrid/offline testing
    clean_memory_record = {k: v for k, v in report_record.items() if k != "_id"}
    REPORTS_REGISTRY.append(clean_memory_record)

    return {
        "status": "success",
        "message": f"Forensic report for case {cid} generated successfully",
        "case_id": cid,
        "evidence_id": primary_ev_id,
        "report_id": rep_id,
        "schema_version": "1.0.0",
        "verification_status": overall_status,
        "report_label": report_status_label,
        "report_filename": os.path.basename(report_path),
        "report_hash": report_hash,
        "discrepancies_count": len(discrepancies),
        "generated_at": now
    }

# -----------------------------------------------------------------------------
# 3. INDEPENDENT REPORT VERIFICATION
# -----------------------------------------------------------------------------

async def _perform_report_verification(
    report_id: str,
    check_current_evidence: bool = True
) -> dict:
    """
    Core independent report verification logic.
    1. Validates report_id.
    2. Resolves persisted report record from MongoDB or REPORTS_REGISTRY.
    3. Recomputes fresh SHA-256 checksum from PDF file on disk.
    4. Evaluates PDF file integrity against stored report_hash.
    5. Re-checks current evidence & blockchain integrity if requested.
    6. Distinguishes PDF bitstream integrity from evidence integrity.
    """
    safe_rid = _validate_safe_identifier(report_id, "Report ID")

    # Step 0: Check persistent storage if required
    if db_client.require_persistent_storage and not db_client.is_connected():
        return {
            "status": "error",
            "report_verification_status": "UNAVAILABLE",
            "report_id": safe_rid,
            "report_found": False,
            "verified": False,
            "tampered": False,
            "technical_error": "DATABASE_UNAVAILABLE",
            "explanation": "Persistent database storage is required but currently unavailable.",
            "verified_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }

    # Step 1: Locate report record
    rep_record = None
    if db_client.is_connected():
        try:
            rep_record = await db_client.reports.find_one({"report_id": safe_rid}, {"_id": 0})
        except Exception as e:
            if db_client.require_persistent_storage:
                return {
                    "status": "error",
                    "report_verification_status": "UNAVAILABLE",
                    "report_id": safe_rid,
                    "report_found": False,
                    "verified": False,
                    "tampered": False,
                    "technical_error": "DATABASE_ERROR",
                    "explanation": f"Database query failed: {str(e)}",
                    "verified_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                }

    if not rep_record and not db_client.require_persistent_storage:
        rep_record = next(
            (r for r in REPORTS_REGISTRY if r.get("report_id") == safe_rid or r.get("report_filename") == safe_rid),
            None
        )

    if not rep_record:
        return {
            "status": "success",
            "report_verification_status": "NOT_FOUND",
            "report_id": safe_rid,
            "report_found": False,
            "verified": False,
            "tampered": False,
            "technical_error": "REPORT_RECORD_NOT_FOUND",
            "explanation": f"Report identifier '{safe_rid}' not found in report registry.",
            "pdf_integrity": {
                "file_exists": False,
                "file_status": "NOT_FOUND",
                "recorded_sha256": None,
                "current_sha256": None,
                "checksum_matches": False,
                "is_digitally_signed": False,
                "integrity_type": "SHA-256 Bitstream Checksum",
                "disclaimer": "No report record found to compare against."
            },
            "evidence_integrity": None,
            "verified_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }

    # Step 2: Validate PDF file integrity on disk
    filename = rep_record.get("report_filename")
    reports_dir = get_reports_dir()
    file_path = (reports_dir / os.path.basename(filename)).resolve()

    # Path traversal guard
    if not str(file_path).startswith(str(reports_dir.resolve())):
        raise HTTPException(status_code=400, detail="Invalid report file path traversal")

    pdf_file_exists = file_path.exists() and file_path.is_file()
    current_pdf_hash = None
    checksum_matches = False
    pdf_tampered = False
    file_integrity_status = "MISSING"

    if pdf_file_exists:
        try:
            pdf_bytes = file_path.read_bytes()
            current_pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()
            recorded_hash = rep_record.get("report_hash")
            checksum_matches = bool(recorded_hash and current_pdf_hash.lower() == recorded_hash.lower())
            pdf_tampered = not checksum_matches
            file_integrity_status = "INTACT" if checksum_matches else "TAMPERED"
        except Exception:
            pdf_tampered = True
            file_integrity_status = "READ_ERROR"
    else:
        pdf_tampered = True
        file_integrity_status = "FILE_MISSING"

    # Step 3: Re-verify current evidence and blockchain state
    ev_id = rep_record.get("evidence_id")
    cid = rep_record.get("case_id")
    current_ev_verif = None
    findings_match = True
    evidence_changed = False

    if check_current_evidence and ev_id:
        current_ev_verif = await verify_evidence_integrity(VerificationRequest(
            evidence_id=ev_id,
            allow_offline_fallback=False
        ))

        recorded_ev_verif = rep_record.get("evidence_verification") or {}
        rec_phys_hash = recorded_ev_verif.get("physical_file_hash")
        curr_phys_hash = current_ev_verif.get("physical_file_hash")
        rec_chain_hash = recorded_ev_verif.get("blockchain_hash")
        curr_chain_hash = current_ev_verif.get("blockchain_hash")
        rec_status = recorded_ev_verif.get("verification_status")
        curr_status = current_ev_verif.get("verification_status")

        if rec_phys_hash and curr_phys_hash and rec_phys_hash.lower() != curr_phys_hash.lower():
            evidence_changed = True
            findings_match = False
        if rec_chain_hash and curr_chain_hash and rec_chain_hash.lower() != curr_chain_hash.lower():
            evidence_changed = True
            findings_match = False
        if rec_status and curr_status and rec_status != curr_status:
            findings_match = False

    # Step 4: Determine Overall Report Verification Status
    explanation = ""
    technical_error = None
    overall_status = "INCONSISTENT"

    if pdf_tampered:
        overall_status = "TAMPERED"
        technical_error = "PDF_CHECKSUM_MISMATCH" if pdf_file_exists else "PDF_FILE_MISSING"
        explanation = "The PDF report file bitstream has been modified or does not match its recorded SHA-256 checksum."
    elif current_ev_verif and current_ev_verif.get("verification_status") == "TAMPERED":
        overall_status = "TAMPERED"
        technical_error = "EVIDENCE_TAMPERED_POST_REPORT"
        explanation = "The PDF checksum is intact, but the physical evidence file on disk was modified/tampered after report generation."
    elif current_ev_verif and current_ev_verif.get("verification_status") == "UNAVAILABLE":
        overall_status = "UNAVAILABLE"
        technical_error = current_ev_verif.get("technical_error") or "BLOCKCHAIN_UNAVAILABLE"
        explanation = "The PDF checksum is intact, but independent evidence ledger verification is currently unavailable."
    elif current_ev_verif and current_ev_verif.get("verification_status") == "INCONSISTENT":
        overall_status = "INCONSISTENT"
        technical_error = "EVIDENCE_INCONSISTENT"
        explanation = "The PDF checksum is intact, but the current evidence record has inconsistencies with the blockchain ledger."
    elif checksum_matches and (not current_ev_verif or current_ev_verif.get("verified")):
        overall_status = "VERIFIED"
        explanation = "Both PDF report bitstream checksum and current evidence integrity are independently confirmed."
    else:
        overall_status = rep_record.get("verification_status", "UNVERIFIED")
        explanation = "Report checksum verified, but underlying evidence was recorded with unverified or incomplete status."

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    return {
        "status": "success",
        "report_id": safe_rid,
        "case_id": cid,
        "evidence_id": ev_id,
        "report_filename": filename,
        "report_verification_status": overall_status,
        "verified": (overall_status == "VERIFIED"),
        "tampered": (overall_status == "TAMPERED"),
        "report_found": True,
        "technical_error": technical_error,
        "explanation": explanation,
        "pdf_integrity": {
            "file_exists": pdf_file_exists,
            "file_status": file_integrity_status,
            "recorded_sha256": rep_record.get("report_hash"),
            "current_sha256": current_pdf_hash,
            "checksum_matches": checksum_matches,
            "is_digitally_signed": False,
            "integrity_type": "SHA-256 Bitstream Checksum",
            "disclaimer": (
                "A matching PDF checksum verifies solely that the PDF file bitstream matches the recorded "
                "SHA-256 hash at generation time. It does NOT prove author identity or constitute an "
                "asymmetric X.509 PKCS#7 digital signature or court certification."
            )
        },
        "evidence_integrity": {
            "evidence_id": ev_id,
            "current_status": current_ev_verif.get("verification_status") if current_ev_verif else "NOT_CHECKED",
            "evidence_verified": current_ev_verif.get("verified") if current_ev_verif else False,
            "blockchain_verified": current_ev_verif.get("blockchain_verified") if current_ev_verif else False,
            "findings_match_report": findings_match,
            "evidence_changed_post_report": evidence_changed
        } if current_ev_verif else None,
        "generated_at": rep_record.get("generated_at"),
        "verified_at": now
    }

@router.post("/verify", status_code=status.HTTP_200_OK)
async def verify_report_post(
    req: ReportVerifyRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Independent report verification endpoint (POST).
    Verifies PDF checksum against recorded digest and independently checks current evidence & blockchain status.
    Distinguishes PDF file integrity from evidence integrity.
    Allowed roles: All authenticated.
    """
    target = req.report_id or req.filename
    if not target:
        raise HTTPException(status_code=400, detail="Either report_id or filename must be provided")

    return await _perform_report_verification(
        report_id=target,
        check_current_evidence=bool(req.check_current_evidence)
    )

@router.get("/verify/{report_id}", status_code=status.HTTP_200_OK)
async def verify_report_get(
    report_id: str,
    check_current_evidence: bool = True,
    current_user: dict = Depends(get_current_user)
):
    """
    Independent report verification endpoint (GET).
    Allows direct lookup by report ID.
    Allowed roles: All authenticated.
    """
    return await _perform_report_verification(
        report_id=report_id,
        check_current_evidence=check_current_evidence
    )

# -----------------------------------------------------------------------------
# 4. REPORT DOWNLOAD & RETRIEVAL
# -----------------------------------------------------------------------------

@router.get("/download/{filename}")
async def download_report(
    filename: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Download generated forensic report PDF with strict path traversal defense.
    Allowed roles: All authenticated.
    """
    safe_fn = _validate_safe_identifier(filename, "Filename")

    reports_dir = get_reports_dir()
    file_path = (reports_dir / os.path.basename(safe_fn)).resolve()

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
    """
    Retrieve history of all generated forensic reports for a case. Preserves versioning.
    Allowed roles: All authenticated.
    """
    safe_cid = _validate_safe_identifier(case_id, "Case ID")
    records = []

    if db_client.is_connected():
        try:
            cursor = db_client.reports.find({"case_id": safe_cid}, {"_id": 0})
            async for doc in cursor:
                records.append(_sanitize_report_record(doc))
        except Exception as e:
            if db_client.require_persistent_storage:
                raise HTTPException(status_code=503, detail=f"Database query failed: {e}")

    if not records and not db_client.require_persistent_storage:
        records = [_sanitize_report_record(r) for r in REPORTS_REGISTRY if r.get("case_id") == safe_cid]

    return records

@router.get("/detail/{report_id}")
async def get_report_detail(
    report_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Retrieve detailed metadata for a specific forensic report.
    Allowed roles: All authenticated.
    """
    safe_rid = _validate_safe_identifier(report_id, "Report ID")
    rec = None

    if db_client.is_connected():
        try:
            rec = await db_client.reports.find_one({"report_id": safe_rid}, {"_id": 0})
        except Exception as e:
            if db_client.require_persistent_storage:
                raise HTTPException(status_code=503, detail=f"Database query failed: {e}")

    if not rec and not db_client.require_persistent_storage:
        rec = next((r for r in REPORTS_REGISTRY if r.get("report_id") == safe_rid), None)

    if not rec:
        raise HTTPException(status_code=404, detail=f"Report '{safe_rid}' not found")

    return _sanitize_report_record(rec)
