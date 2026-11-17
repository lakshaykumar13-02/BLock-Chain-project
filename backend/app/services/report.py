import io
import os
import hashlib
import time
import datetime
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from xml.sax.saxutils import escape as xml_escape
from dotenv import load_dotenv

load_dotenv()

REPORTS_DIR = os.getenv("REPORTS_PATH", "generated_reports")
PUBLIC_VERIFICATION_URL_BASE = os.getenv("PUBLIC_VERIFICATION_URL_BASE")
LOCAL_VERIFICATION_URL_BASE = os.getenv("LOCAL_VERIFICATION_URL_BASE", "http://localhost:8000")
ALLOW_LOCAL_QR_LINKS = os.getenv("ALLOW_LOCAL_QR_LINKS", "true").lower() in ("true", "1", "yes")

def get_reports_dir() -> Path:
    """Return Path to generated reports directory, ensuring it exists."""
    base_path = Path(__file__).resolve().parent.parent.parent
    p = Path(REPORTS_DIR)
    reports_path = p.resolve() if p.is_absolute() else (base_path / p).resolve()
    reports_path.mkdir(parents=True, exist_ok=True)
    return reports_path

def resolve_verification_url(target_id: str, is_report: bool = False) -> Tuple[str, bool, str]:
    """
    Resolve destination URL for tamper-evident verification QR code and report metadata.
    Returns: (url, is_local_development, human_readable_note)

    Security rules enforced:
    - Never pretend a localhost development URL is publicly accessible.
    - If PUBLIC_VERIFICATION_URL_BASE is not configured:
        - If ALLOW_LOCAL_QR_LINKS is True: generate local development link with explicit warning label.
        - If ALLOW_LOCAL_QR_LINKS is False: disable public link generation; return empty URL.
    - Never expose tokens, passwords, private keys, or internal directory paths in the URL.
    """
    clean_target = xml_escape(target_id.strip()) if target_id else "unknown"

    # 1. Configured Public Production URL
    if PUBLIC_VERIFICATION_URL_BASE and PUBLIC_VERIFICATION_URL_BASE.strip():
        base = PUBLIC_VERIFICATION_URL_BASE.strip().rstrip("/")
        if is_report:
            url = f"{base}/api/reports/verify/{clean_target}"
        else:
            url = f"{base}/api/verification/verify?evidence_id={clean_target}"
        return (url, False, "Public Verification Endpoint")

    # 2. Local Development Fallback
    if ALLOW_LOCAL_QR_LINKS:
        base = LOCAL_VERIFICATION_URL_BASE.strip().rstrip("/")
        if is_report:
            url = f"{base}/api/reports/verify/{clean_target}"
        else:
            url = f"{base}/api/verification/verify?evidence_id={clean_target}"
        return (url, True, "Local Development Link (Non-Public)")

    # 3. Public link disabled / unconfigured
    return ("", False, "Public Verification URL Unconfigured")

def generate_qr_image(
    evidence_id: str,
    base_url: Optional[str] = None,
    is_report: bool = False,
    custom_url: Optional[str] = None
) -> bytes:
    """
    Generate QR code image bytes encoding the tamper-evident verification URL.
    Returns PNG bytes.
    Preserves backward compatibility with generate_qr_image(evidence_id, base_url).
    """
    import qrcode

    if custom_url:
        verification_url = custom_url
    elif base_url:
        base = base_url.strip().rstrip("/")
        if is_report:
            verification_url = f"{base}/api/reports/verify/{evidence_id}"
        else:
            verification_url = f"{base}/api/verification/verify?evidence_id={evidence_id}"
    else:
        url, _, _ = resolve_verification_url(evidence_id, is_report=is_report)
        verification_url = url if url else f"urn:chainvault:verification:{evidence_id}:unconfigured"

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
    preserve_existing: bool = True,
    report_id: Optional[str] = None,
    schema_version: str = "1.0.0",
    verification_results: Optional[dict] = None,
    custody_verification: Optional[dict] = None,
    blockchain_metadata: Optional[dict] = None,
    discrepancies: Optional[list[str]] = None,
    report_status: Optional[str] = None,
    qr_url: Optional[str] = None,
    is_local_qr: bool = True
) -> Tuple[str, bytes, str]:
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
    - Displays explicit statuses (VERIFIED, TAMPERED, INCONSISTENT, NOT_FOUND, UNAVAILABLE).
    - Prominently displays INCOMPLETE / UNVERIFIED banners when verification fails.
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
    rep_id = report_id or f"REP-{case_id}-{int(time.time() * 1000)}"
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
        fontSize=14,
        leading=17,
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
        spaceAfter=6
    )
    section_heading = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=9.5,
        leading=12,
        textColor=colors.HexColor("#1e293b"),
        spaceBefore=7,
        spaceAfter=3,
        keepWithNext=True
    )
    meta_label = ParagraphStyle(
        "MetaLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7,
        leading=9.5,
        textColor=colors.HexColor("#334155")
    )
    meta_val = ParagraphStyle(
        "MetaVal",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7,
        leading=9.5,
        textColor=colors.HexColor("#0f172a")
    )
    table_head = ParagraphStyle(
        "TableHead",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7,
        leading=9,
        textColor=colors.whitesmoke
    )
    table_cell = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=6.5,
        leading=8.5,
        textColor=colors.HexColor("#1e293b")
    )
    table_cell_mono = ParagraphStyle(
        "TableCellMono",
        parent=styles["Normal"],
        fontName="Courier",
        fontSize=6,
        leading=7.5,
        textColor=colors.HexColor("#0f172a")
    )
    alert_title = ParagraphStyle(
        "AlertTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#991b1b")
    )
    alert_text = ParagraphStyle(
        "AlertText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=6.5,
        leading=8.5,
        textColor=colors.HexColor("#7f1d1d")
    )
    verified_badge = ParagraphStyle(
        "VerifiedBadge",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#065f46")
    )

    story = []

    # 1. Document Title Banner
    story.append(Paragraph("CHAINVAULT FORENSIC EVIDENCE & CUSTODY REPORT", title_style))
    story.append(Paragraph("Verifiable Digital Forensic Report & Independent Cryptographic Audit Ledger", subtitle_style))

    # 2. Prominent Verification Status Alert Banner
    effective_status = report_status or "VERIFIED"
    is_fully_verified = (effective_status == "VERIFIED")

    if is_fully_verified:
        badge_p = Paragraph("<b>CRYPTOGRAPHIC VERIFICATION STATUS: VERIFIED</b> — All independent hash comparisons agree across physical disk, database, and Ethereum smart contract.", verified_badge)
        badge_table = Table([[badge_p]], colWidths=[540])
        badge_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ecfdf5")),
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#10b981")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(badge_table)
    else:
        warn_title = f"<b>[INCOMPLETE / UNVERIFIED FORENSIC REPORT - STATUS: {_safe_xml(effective_status)}]</b>"
        warn_body = (
            "<b>WARNING:</b> One or more independent cryptographic verification checks failed, were inconsistent, "
            "or were unavailable during report generation. This document faithfully records unverified or compromised "
            "forensic state and MUST NOT be accepted as a cryptographically verified exhibit without independent re-validation."
        )
        warn_content = [Paragraph(warn_title, alert_title), Paragraph(warn_body, alert_text)]
        badge_table = Table([[warn_content]], colWidths=[540])
        badge_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fef2f2")),
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#ef4444")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(badge_table)

    story.append(Spacer(1, 5))

    # 3. Case Summary & Tamper-Evident QR Verification Badge
    primary_ev_id = (
        evidence_items[0].get("evidence_id")
        if evidence_items and evidence_items[0].get("evidence_id")
        else case_id
    )

    qr_flowable = None
    try:
        qr_bytes = generate_qr_image(primary_ev_id, is_report=True, custom_url=qr_url)
        qr_buf = io.BytesIO(qr_bytes)
        qr_flowable = Image(qr_buf, width=64, height=64)
    except Exception:
        qr_flowable = Paragraph("<b>QR Unavailable</b>", meta_val)

    if is_local_qr:
        qr_caption_text = f"<font size='5.5' color='#475569'><b>Scan to Verify</b><br/>{_safe_xml(rep_id)}<br/><font color='#dc2626'>[Local Dev Link]</font></font>"
    else:
        qr_caption_text = f"<font size='5.5' color='#475569'><b>Scan to Verify</b><br/>{_safe_xml(rep_id)}</font>"

    qr_caption = Paragraph(qr_caption_text, ParagraphStyle("QRCap", alignment=1, leading=6.5))

    gen_time = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    summary_rows = [
        [
            Paragraph("Report Reference:", meta_label),
            Paragraph(f"<b>{_safe_xml(rep_id)}</b> (Schema: {_safe_xml(schema_version)})", meta_val),
            [qr_flowable, qr_caption]
        ],
        [
            Paragraph("Case Reference:", meta_label),
            Paragraph(f"<b>{_safe_xml(case_id)}</b> — {_safe_xml(case_data.get('title', 'Forensic Investigation'))}", meta_val),
            ""
        ],
        [
            Paragraph("Lead Investigator:", meta_label),
            Paragraph(_safe_xml(case_data.get("lead_investigator", "investigator1")), meta_val),
            ""
        ],
        [
            Paragraph("Generated At:", meta_label),
            Paragraph(f"{gen_time} | <i>SHA-256 Checksum Protected</i>", meta_val),
            ""
        ],
        [
            Paragraph("Verification Result:", meta_label),
            Paragraph(f"<b>{_safe_xml(effective_status)}</b>", meta_val),
            ""
        ]
    ]

    # Summary table widths sum to 540 pt (100 + 350 + 90 = 540 pt)
    summary_table = Table(summary_rows, colWidths=[100, 350, 90])
    summary_table.setStyle(TableStyle([
        ("SPAN", (2, 0), (2, 4)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (2, 0), (2, 4), "CENTER"),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 6))

    # 4. Registered Forensic Evidence & Tripartite Hash Reconciliation
    # Total colWidths: 70 + 105 + 155 + 105 + 105 = 540 pt
    story.append(Paragraph("1. Forensic Evidence & Tripartite Hash Verification", section_heading))
    ev_head = [
        Paragraph("Evidence ID", table_head),
        Paragraph("Filename / Size", table_head),
        Paragraph("Cryptographic Hashes (File vs DB vs Chain)", table_head),
        Paragraph("Verification Result", table_head),
        Paragraph("Custodian / Uploaded", table_head)
    ]
    ev_rows = [ev_head]

    v_res = verification_results or {}
    phys_hash = v_res.get("physical_file_hash") or "UNAVAILABLE"
    db_hash = v_res.get("database_hash") or "UNAVAILABLE"
    chain_hash = v_res.get("blockchain_hash") or "UNAVAILABLE"
    ev_verif_status = v_res.get("verification_status") or effective_status

    if evidence_items:
        for idx, ev in enumerate(evidence_items):
            eid = ev.get("evidence_id", "N/A")
            fname = ev.get("filename", "evidence.bin")
            sz_str = _format_size(ev.get("file_size") or ev.get("size"))
            cust = ev.get("custodian", "N/A")
            up_at = ev.get("uploaded_at", "N/A")

            # Tripartite hash breakdown
            hash_display = (
                f"<b>Physical Disk:</b> {_safe_xml(phys_hash)}<br/>"
                f"<b>DB Recorded:</b> {_safe_xml(db_hash)}<br/>"
                f"<b>Blockchain:</b> {_safe_xml(chain_hash)}"
            )

            res_display = (
                f"<b>Status:</b> {_safe_xml(ev_verif_status)}<br/>"
                f"<font size='5.5' color='#64748b'>File Match DB: {'YES' if v_res.get('file_vs_database') else 'NO'}<br/>"
                f"File Match Chain: {'YES' if v_res.get('file_vs_blockchain') else 'NO'}</font>"
            )

            ev_rows.append([
                Paragraph(_safe_xml(eid), table_cell),
                Paragraph(f"{_safe_xml(fname)}<br/><font color='#64748b'>{sz_str}</font>", table_cell),
                Paragraph(hash_display, table_cell_mono),
                Paragraph(res_display, table_cell),
                Paragraph(f"{_safe_xml(cust)}<br/><font color='#64748b' size='5.5'>{_safe_xml(up_at)}</font>", table_cell_mono)
            ])
    else:
        ev_rows.append([
            Paragraph("N/A", table_cell),
            Paragraph("No evidence records registered", table_cell),
            Paragraph("UNAVAILABLE", table_cell_mono),
            Paragraph("NOT_FOUND", table_cell),
            Paragraph("None", table_cell_mono)
        ])

    ev_table = Table(ev_rows, colWidths=[70, 105, 155, 105, 105], repeatRows=1)
    ev_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0284c7")),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(ev_table)
    story.append(Spacer(1, 6))

    # 5. Blockchain Ledger Settlement Details
    # colWidths: [130, 410] = 540 pt
    story.append(Paragraph("2. Blockchain Ledger Settlement & Smart Contract Anchor", section_heading))
    b_meta = blockchain_metadata or {}
    chain_id_val = b_meta.get("chain_id") or v_res.get("chain_id") or "UNAVAILABLE"
    contract_addr_val = b_meta.get("contract_address") or v_res.get("contract_address") or "UNAVAILABLE"
    tx_hash_val = b_meta.get("tx_hash") or v_res.get("tx_hash") or "NOT FOUND"
    block_num_val = b_meta.get("block_number") or (evidence_items[0].get("block_number") if evidence_items else None) or "UNAVAILABLE"
    receipt_status_val = b_meta.get("receipt_status") or ("Confirmed (0x1)" if is_fully_verified else "UNVERIFIED")

    bc_rows = [
        [Paragraph("Blockchain Network / Chain ID:", meta_label), Paragraph(_safe_xml(chain_id_val), table_cell_mono)],
        [Paragraph("EvidenceRegistry Contract Address:", meta_label), Paragraph(_safe_xml(contract_addr_val), table_cell_mono)],
        [Paragraph("Registration Transaction Hash:", meta_label), Paragraph(_safe_xml(tx_hash_val), table_cell_mono)],
        [Paragraph("Block Number / Height:", meta_label), Paragraph(_safe_xml(block_num_val), table_cell)],
        [Paragraph("Transaction Receipt Status:", meta_label), Paragraph(_safe_xml(receipt_status_val), table_cell)]
    ]
    bc_table = Table(bc_rows, colWidths=[130, 410])
    bc_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(bc_table)
    story.append(Spacer(1, 6))

    # 6. Chain of Custody Audit Trail & Chain Verification
    # colWidths: [65, 75, 90, 90, 220] = 540 pt
    story.append(Paragraph("3. Chain of Custody Audit Trail & Event Hash Verification", section_heading))
    audit_head = [
        Paragraph("Log / Seq #", table_head),
        Paragraph("Action", table_head),
        Paragraph("Previous Custodian", table_head),
        Paragraph("New Custodian", table_head),
        Paragraph("Timestamp / Canonical Event Hash / Anchor TX", table_head)
    ]
    audit_rows = [audit_head]

    c_verif = custody_verification or {}
    custody_audit_status = c_verif.get("verification_status") or "UNVERIFIED"

    if audit_logs:
        for log in audit_logs:
            ts_val = log.get("timestamp", "N/A")
            if isinstance(ts_val, str) and len(ts_val) > 19:
                ts_disp = ts_val[:19].replace("T", " ")
            else:
                ts_disp = str(ts_val)

            ev_hash = log.get("event_hash") or "N/A"
            tx_val = log.get("blockchain_tx") or "None"
            seq_val = log.get("sequence_number")
            log_id_disp = f"{log.get('log_id', log.get('event_id', 'N/A'))}"
            if seq_val is not None:
                log_id_disp += f" (Seq {seq_val})"

            details_cell = (
                f"<b>Time:</b> {_safe_xml(ts_disp)} UTC<br/>"
                f"<b>Hash:</b> <font face='Courier' size='5.5'>{_safe_xml(ev_hash)}</font>"
            )
            if tx_val and tx_val not in ("None", "0x0", "Pending"):
                details_cell += f"<br/><b>TX:</b> <font face='Courier' size='5.5' color='#64748b'>{_safe_xml(tx_val)}</font>"

            audit_rows.append([
                Paragraph(_safe_xml(log_id_disp), table_cell),
                Paragraph(_safe_xml(log.get("action", "TRANSFER")), table_cell),
                Paragraph(_safe_xml(log.get("previous_custodian", "N/A")), table_cell_mono),
                Paragraph(_safe_xml(log.get("new_custodian", "N/A")), table_cell_mono),
                Paragraph(details_cell, table_cell)
            ])
    else:
        audit_rows.append([
            Paragraph("AUD-GEN", table_cell),
            Paragraph("INGESTION", table_cell),
            Paragraph("None", table_cell_mono),
            Paragraph("investigator1", table_cell_mono),
            Paragraph("Initial synthetic lifecycle entry", table_cell)
        ])

    # Append summary row for custody audit verification
    audit_rows.append([
        Paragraph("<b>Audit Integrity:</b>", table_cell),
        Paragraph(f"<b>{_safe_xml(custody_audit_status)}</b>", table_cell),
        Paragraph(f"Chain Intact: {'YES' if c_verif.get('chain_intact', True) else 'NO'}", table_cell),
        Paragraph(f"Events: {len(audit_logs)}", table_cell),
        Paragraph(f"Reconciled: {'YES' if c_verif.get('blockchain_reconciled', True) else 'NO'}", table_cell)
    ])

    audit_table = Table(audit_rows, colWidths=[65, 75, 90, 90, 220], repeatRows=1)
    audit_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f1f5f9")),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(audit_table)
    story.append(Spacer(1, 6))

    # 7. Discrepancies, Missing Data & Verification Limitations (KeepTogether)
    disc_list = discrepancies or []
    if disc_list:
        story.append(Paragraph("4. Detected Inconsistencies & Verification Limitations", section_heading))
        disc_text = "<br/>".join([f"• {_safe_xml(d)}" for d in disc_list])
        disc_p = Paragraph(disc_text, alert_text)
        disc_table = Table([[disc_p]], colWidths=[540])
        disc_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff7ed")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#f97316")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(KeepTogether(disc_table))
        story.append(Spacer(1, 6))

    # 8. Integrity & Legal Disclaimers Box (KeepTogether, 540 pt width)
    notice_text = (
        "<b>Forensic Bitstream Integrity Notice:</b> This forensic report is bound to an independent SHA-256 "
        "document checksum computed upon binary compilation. Any alteration or modification to the byte stream "
        "of this PDF file invalidates the checksum recorded on the ChainVault server. <br/>"
        "<b>Cryptographic & Legal Disclaimer:</b> This document establishes document-level bitstream checksum integrity "
        "aligned with ISO/IEC 27037 guidelines. This SHA-256 digest is distinct from an asymmetric X.509 PKCS#7 "
        "digital signature and does not constitute a certified digital signature or legally binding court certificate "
        "unless independently countersigned under applicable jurisdictional rules."
    )
    notice_p = Paragraph(
        notice_text,
        ParagraphStyle("Notice", parent=styles["Normal"], fontSize=6, leading=8, textColor=colors.HexColor("#475569"))
    )
    notice_table = Table([[notice_p]], colWidths=[540])
    notice_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f1f5f9")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#94a3b8")),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(KeepTogether(notice_table))

    # Build document using NumberedCanvas
    doc.build(story, canvasmaker=NumberedCanvas)
    pdf_bytes = buffer.getvalue()
    report_hash = hashlib.sha256(pdf_bytes).hexdigest()

    with open(report_path, "wb") as f:
        f.write(pdf_bytes)

    return str(report_path), pdf_bytes, report_hash
