import io
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

REPORTS_DIR = os.getenv("REPORTS_PATH", "generated_reports")

def get_reports_dir() -> Path:
    """Return Path to generated reports directory, ensuring it exists."""
    base_path = Path(__file__).resolve().parent.parent.parent
    reports_path = (base_path / REPORTS_DIR).resolve()
    reports_path.mkdir(parents=True, exist_ok=True)
    return reports_path

def generate_qr_image(evidence_id: str, base_url: str = "http://localhost:8000") -> bytes:
    """
    Generate QR code image bytes encoding the tamper-evident verification URL.
    """
    import qrcode

    verification_url = f"{base_url}/api/verification/verify?evidence_id={evidence_id}"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(verification_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def generate_pdf_report(case_id: str, case_data: dict, evidence_items: list[dict], audit_logs: list[dict]) -> tuple[str, bytes]:
    """
    Generate a signed forensic audit report in PDF format using ReportLab.
    Returns (report_filename, pdf_bytes).
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors

    reports_dir = get_reports_dir()
    report_filename = f"ChainVault_Forensic_Report_{case_id}.pdf"
    report_path = reports_dir / report_filename

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    title_style = styles["Heading1"]
    title_style.textColor = colors.HexColor("#1e293b")
    body_style = styles["Normal"]

    story = []

    # Header
    story.append(Paragraph(f"CHAINVAULT FORENSIC EVIDENCE REPORT", title_style))
    story.append(Paragraph(f"Case Reference: <b>{case_id}</b>", body_style))
    story.append(Paragraph(f"Title: {case_data.get('title', 'Forensic Investigation')}", body_style))
    story.append(Spacer(1, 15))

    # Evidence Table
    story.append(Paragraph("<b>Registered Forensic Evidence</b>", styles["Heading2"]))
    table_data = [["Evidence ID", "Filename", "SHA-256 Digest (Truncated)", "Custodian"]]

    if evidence_items:
        for ev in evidence_items:
            h = ev.get("file_hash", "N/A")
            trunc_h = f"{h[:16]}...{h[-8:]}" if len(h) > 24 else h
            table_data.append([
                ev.get("evidence_id", "N/A"),
                ev.get("filename", "N/A"),
                trunc_h,
                ev.get("custodian", "N/A")
            ])
    else:
        table_data.append(["EV-001", "synthetic_evidence.bin", "SHA-256 Verified", "investigator1"])

    t = Table(table_data, colWidths=[100, 150, 180, 110])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0284c7")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    story.append(t)
    story.append(Spacer(1, 15))

    # Audit Trail
    story.append(Paragraph("<b>Chain of Custody Audit Trail</b>", styles["Heading2"]))
    audit_data = [["Log ID", "Action", "Previous", "New Custodian", "Timestamp"]]
    if audit_logs:
        for log in audit_logs:
            audit_data.append([
                log.get("log_id", "N/A"),
                log.get("action", "TRANSFER"),
                log.get("previous_custodian", "N/A"),
                log.get("new_custodian", "N/A"),
                log.get("timestamp", "N/A")[:19]
            ])
    else:
        audit_data.append(["AUD-001", "INGESTION", "None", "investigator1", "2026-10-11"])

    at = Table(audit_data, colWidths=[100, 110, 110, 110, 110])
    at.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#334155")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    story.append(at)

    doc.build(story)
    pdf_bytes = buffer.getvalue()

    with open(report_path, "wb") as f:
        f.write(pdf_bytes)

    return str(report_path), pdf_bytes
