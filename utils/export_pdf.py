import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
)

from utils.metrics_catalog import SECTION_A, SECTION_B, SECTION_C, PRINCIPLES

NAVY = colors.HexColor("#1F3864")
BLUE = colors.HexColor("#2E75B6")
LIGHT = colors.HexColor("#EAF1FB")


def build_pdf_report(org, period, esg_rows, submission=None):
    values_by_code = {row.metric_code: row for row in esg_rows}

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleStyle", parent=styles["Title"], textColor=NAVY, fontSize=20)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=colors.white, backColor=BLUE,
                         spaceBefore=10, spaceAfter=6, leftIndent=4, borderPadding=4)
    normal = styles["Normal"]

    elements = []
    elements.append(Paragraph("MEIL Group — BRSR Disclosure Report", title_style))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph(f"<b>Entity:</b> {org.name} ({org.org_type.replace('_',' ').title()})", normal))
    elements.append(Paragraph(f"<b>Reporting Period:</b> {period.name}", normal))
    if submission:
        elements.append(Paragraph(f"<b>Report Status:</b> {submission.status}", normal))
    elements.append(Spacer(1, 14))

    # Section A
    elements.append(Paragraph("SECTION A: General Disclosures", h2))
    data = [["Field", "Value"]]
    for m in SECTION_A:
        entry = values_by_code.get(m["code"])
        data.append([m["name"], entry.value if entry else "-"])
    elements.append(_table(data, [10 * cm, 7 * cm]))
    elements.append(Spacer(1, 10))

    # Section B
    elements.append(Paragraph("SECTION B: Management &amp; Process Disclosures", h2))
    data = [["Policy Coverage Question", "Response"]]
    for m in SECTION_B:
        entry = values_by_code.get(m["code"])
        data.append([m["name"], entry.value if entry else "-"])
    elements.append(_table(data, [12 * cm, 5 * cm]))
    elements.append(PageBreak())

    # Section C
    elements.append(Paragraph("SECTION C: Principle-wise Performance Metrics", h2))
    current_principle = None
    data = [["Metric", "Value", "Unit"]]
    for m in SECTION_C:
        if m["principle"] != current_principle:
            current_principle = m["principle"]
            data.append([f"{current_principle}: {PRINCIPLES[current_principle]}", "", ""])
        entry = values_by_code.get(m["code"])
        label = m["name"] + (" *" if entry and entry.is_consolidated else "")
        data.append([label, entry.value if entry else "-", m.get("unit", "")])
    elements.append(_table(data, [10 * cm, 4 * cm, 3 * cm], highlight_principle_rows=True))
    elements.append(Spacer(1, 8))
    elements.append(Paragraph("<i>* Denotes a value automatically consolidated from subordinate entities.</i>", normal))

    doc.build(elements)
    buf.seek(0)
    return buf


def _table(data, col_widths, highlight_principle_rows=False):
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if highlight_principle_rows:
        for i, row in enumerate(data):
            if i > 0 and row[1] == "" and row[2] == "":
                style.append(("BACKGROUND", (0, i), (-1, i), BLUE))
                style.append(("TEXTCOLOR", (0, i), (-1, i), colors.white))
                style.append(("FONTNAME", (0, i), (-1, i), "Helvetica-Bold"))
                style.append(("SPAN", (0, i), (-1, i)))
    t.setStyle(TableStyle(style))
    return t
