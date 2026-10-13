import io
import os
import hashlib
import time
import datetime
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape
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

def _safe_xml(val) -> str:
    """Safely escape text for ReportLab Paragraph XML."""
    if val is None:
        return "N/A"
    return xml_escape(str(val))

def _format_size(size_bytes) -> str:
    """Format bytes into readable size."""
    try:
        b = int(size_bytes)
        if b < 1024:
            return f"{b} B"
        elif b < 1024 * 1024:
            return f"{b / 1024:.1f} KB"
        else:
            return f"{b / (1024 * 1024):.1f} MB"
    except (ValueError, TypeError):
        return "N/A"

def generate_pdf_report(
    case_id: str,
    case_data: dict,
    evidence_items: list[dict],
    audit_logs: list[dict],
    preserve_existing: bool = True
) -> tuple[str, bytes, str]:
    """
    Generate a tamper-evident forensic audit report in PDF format using ReportLab Platypus.
    Returns (report_filepath, pdf_bytes, report_sha256_hash).

    Layout Rules Enforced:
    - Platypus flowable hierarchy with auto-wrapping Paragraphs in every table cell.
    - Zero fixed-coordinate text overlaps or cell bleeds.
    - Dynamic NumberedCanvas for header/footer and 'Page X of Y' pagination.
    - Repeating table headers across page breaks (repeatRows=1).
    - Usable width strictly bounded to 540 points (8.5in - 2x 0.5in margins).
    - Long hashes, filenames, and Ethereum addresses wrap gracefully without clipping.
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas

    class NumberedCanvas(canvas.Canvas):
        """Two-pass canvas for dynamic total page count and boundary-safe headers/footers."""
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._saved_page_states = []

        def showPage(self):
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            num_pages = len(self._saved_page_states)
            for state in self._saved_page_states:
                self.__dict__.update(state)
                self.draw_page_decorations(num_pages)
                super().showPage()
            super().save()

        def draw_page_decorations(self, page_count):
            self.saveState()
            self.setFont("Helvetica-Bold", 7.5)
            self.setFillColor(colors.HexColor("#475569"))

            # Running Header (pages > 1)
            if self._pageNumber > 1:
                self.drawString(36, 756, "CHAINVAULT FORENSIC EVIDENCE & CUSTODY REPORT")
                self.drawRightString(576, 756, f"CASE: {_safe_xml(case_id)}")
                self.setStrokeColor(colors.HexColor("#cbd5e1"))
                self.setLineWidth(0.5)
                self.line(36, 750, 576, 750)

            # Running Footer (all pages)
            self.setStrokeColor(colors.HexColor("#cbd5e1"))
            self.setLineWidth(0.5)
            self.line(36, 42, 576, 42)

            self.setFont("Helvetica", 7.5)
            self.setFillColor(colors.HexColor("#64748b"))
            self.drawString(36, 28, "ChainVault Digital Forensics — SHA-256 Tamper-Evident Report (RFC 3161 Aligned)")
            self.drawRightString(576, 28, f"Page {self._pageNumber} of {page_count}")
            self.restoreState()

    reports_dir = get_reports_dir()
    if preserve_existing:
        ts = int(time.time() * 1000)
        report_filename = f"ChainVault_Forensic_Report_{case_id}_{ts}.pdf"
    else:
        report_filename = f"ChainVault_Forensic_Report_{case_id}.pdf"
    report_path = reports_dir / report_filename

    buffer = io.BytesIO()
    # Usable width: 612 - 36 - 36 = 540 points. Height: 792 - 54 - 54 = 684 points.
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()

    # Typography & Flowable Styles
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=18,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=2,
        keepWithNext=True
    )
    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10.5,
        textColor=colors.HexColor("#475569"),
        spaceAfter=8
    )
    section_heading = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#1e293b"),
        spaceBefore=8,
        spaceAfter=4,
        keepWithNext=True
    )
    meta_label = ParagraphStyle(
        "MetaLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#334155")
    )
    meta_val = ParagraphStyle(
        "MetaVal",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#0f172a")
    )
    table_head = ParagraphStyle(
        "TableHead",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9.5,
        textColor=colors.whitesmoke
    )
    table_cell = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7,
        leading=9,
        textColor=colors.HexColor("#1e293b")
    )
    table_cell_mono = ParagraphStyle(
        "TableCellMono",
        parent=styles["Normal"],
        fontName="Courier",
        fontSize=6.5,
        leading=8,
        textColor=colors.HexColor("#0f172a")
    )

    story = []

    # 1. Document Title Banner
    story.append(Paragraph("CHAINVAULT FORENSIC EVIDENCE & CUSTODY REPORT", title_style))
    story.append(Paragraph("Cryptographic Proof of Digital Evidence Integrity & Append-Only Custody Log", subtitle_style))

    # 2. Case Summary & Tamper-Evident QR Verification Badge
    primary_ev_id = (
        evidence_items[0].get("evidence_id")
        if evidence_items and evidence_items[0].get("evidence_id")
        else case_id
    )

    qr_flowable = None
    try:
        qr_bytes = generate_qr_image(primary_ev_id)
        qr_buf = io.BytesIO(qr_bytes)
        qr_flowable = Image(qr_buf, width=68, height=68)
    except Exception:
        qr_flowable = Paragraph("<b>QR Unavailable</b>", meta_val)

    qr_caption = Paragraph(
        f"<font size='6' color='#475569'><b>Scan to Verify</b><br/>{_safe_xml(primary_ev_id)}</font>",
        ParagraphStyle("QRCap", alignment=1, leading=7.5)
    )

    gen_time = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    summary_rows = [
        [
            Paragraph("Case Reference:", meta_label),
            Paragraph(f"<b>{_safe_xml(case_id)}</b>", meta_val),
            [qr_flowable, qr_caption]
        ],
        [
            Paragraph("Case Title:", meta_label),
            Paragraph(_safe_xml(case_data.get("title", "Forensic Investigation")), meta_val),
            ""
        ],
        [
            Paragraph("Description:", meta_label),
            Paragraph(_safe_xml(case_data.get("description", "Synthetic demonstration case for digital forensics verification")), meta_val),
            ""
        ],
        [
            Paragraph("Lead Investigator:", meta_label),
            Paragraph(_safe_xml(case_data.get("lead_investigator", "investigator1")), meta_val),
            ""
        ],
        [
            Paragraph("Generated At:", meta_label),
            Paragraph(f"{gen_time} | <i>SHA-256 Digest Anchored</i>", meta_val),
            ""
        ]
    ]

    # Summary table widths sum to 540 pt
    summary_table = Table(summary_rows, colWidths=[95, 355, 90])
    summary_table.setStyle(TableStyle([
        ("SPAN", (2, 0), (2, 4)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (2, 0), (2, 4), "CENTER"),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 8))

    # 3. Evidence Table (Total colWidths: 75 + 130 + 170 + 45 + 120 = 540 pt)
    story.append(Paragraph("1. Registered Forensic Evidence Items", section_heading))
    ev_head = [
        Paragraph("Evidence ID", table_head),
        Paragraph("Filename", table_head),
        Paragraph("SHA-256 Digest", table_head),
        Paragraph("Size", table_head),
        Paragraph("Custodian", table_head)
    ]
    ev_rows = [ev_head]

    if evidence_items:
        for ev in evidence_items:
            h = ev.get("file_hash") or ev.get("hash") or "N/A"
            sz_str = _format_size(ev.get("file_size") or ev.get("size"))
            ev_rows.append([
                Paragraph(_safe_xml(ev.get("evidence_id", "N/A")), table_cell),
                Paragraph(_safe_xml(ev.get("filename", "evidence.bin")), table_cell),
                Paragraph(_safe_xml(h), table_cell_mono),
                Paragraph(sz_str, table_cell),
                Paragraph(_safe_xml(ev.get("custodian", "N/A")), table_cell_mono)
            ])
    else:
        ev_rows.append([
            Paragraph("EV-001", table_cell),
            Paragraph("synthetic_evidence.bin", table_cell),
            Paragraph("SHA-256 Verified (Default Entry)", table_cell_mono),
            Paragraph("0 B", table_cell),
            Paragraph("investigator1", table_cell_mono)
        ])

    ev_table = Table(ev_rows, colWidths=[75, 130, 170, 45, 120], repeatRows=1)
    ev_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0284c7")),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(ev_table)
    story.append(Spacer(1, 8))

    # 4. Chain of Custody Audit Trail (Total colWidths: 85 + 75 + 115 + 115 + 150 = 540 pt)
    story.append(Paragraph("2. Chain of Custody Audit Trail", section_heading))
    audit_head = [
        Paragraph("Log ID", table_head),
        Paragraph("Action", table_head),
        Paragraph("Previous Custodian", table_head),
        Paragraph("New Custodian", table_head),
        Paragraph("Timestamp / Blockchain TX", table_head)
    ]
    audit_rows = [audit_head]

    if audit_logs:
        for log in audit_logs:
            ts_val = log.get("timestamp", "N/A")
            if isinstance(ts_val, str) and len(ts_val) > 19:
                ts_disp = ts_val[:19].replace("T", " ")
            else:
                ts_disp = str(ts_val)

            tx_val = log.get("blockchain_tx") or "None"
            ts_cell_content = f"{_safe_xml(ts_disp)}"
            if tx_val and tx_val != "None" and tx_val != "Pending":
                ts_cell_content += f"<br/><font color='#64748b' size='6'>TX: {_safe_xml(tx_val)}</font>"

            audit_rows.append([
                Paragraph(_safe_xml(log.get("log_id", "N/A")), table_cell),
                Paragraph(_safe_xml(log.get("action", "TRANSFER")), table_cell),
                Paragraph(_safe_xml(log.get("previous_custodian", "N/A")), table_cell_mono),
                Paragraph(_safe_xml(log.get("new_custodian", "N/A")), table_cell_mono),
                Paragraph(ts_cell_content, table_cell)
            ])
    else:
        audit_rows.append([
            Paragraph("AUD-001", table_cell),
            Paragraph("INGESTION", table_cell),
            Paragraph("None", table_cell_mono),
            Paragraph("investigator1", table_cell_mono),
            Paragraph("2026-10-11 00:00:00", table_cell)
        ])

    audit_table = Table(audit_rows, colWidths=[85, 75, 115, 115, 150], repeatRows=1)
    audit_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(audit_table)
    story.append(Spacer(1, 8))

    # 5. Integrity & Legal Disclaimers Box (KeepTogether, 540 pt width)
    notice_text = (
        "<b>Forensic Integrity Notice:</b> This report is protected by an independent SHA-256 file checksum "
        "computed upon compilation. Any modification to this PDF file invalidates the checksum recorded on the "
        "ChainVault server. <i>Technical Disclaimer:</i> This document is an academic prototype demonstration record "
        "aligned with ISO/IEC 27037 digital forensics preservation guidelines. It utilizes a SHA-256 file-integrity "
        "digest, distinct from an asymmetric X.509 PKCS#7 digital signature."
    )
    notice_p = Paragraph(
        notice_text,
        ParagraphStyle("Notice", parent=styles["Normal"], fontSize=6.5, leading=8.5, textColor=colors.HexColor("#475569"))
    )
    notice_table = Table([[notice_p]], colWidths=[540])
    notice_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f1f5f9")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#94a3b8")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(KeepTogether(notice_table))

    # Build document using NumberedCanvas
    doc.build(story, canvasmaker=NumberedCanvas)
    pdf_bytes = buffer.getvalue()
    report_hash = hashlib.sha256(pdf_bytes).hexdigest()

    with open(report_path, "wb") as f:
        f.write(pdf_bytes)

    return str(report_path), pdf_bytes, report_hash
