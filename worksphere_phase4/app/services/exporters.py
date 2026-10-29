"""CSV / PDF report builders (Module 25). Pure functions: rows in, bytes out."""
import csv
import io
from datetime import datetime, timezone
from typing import List, Sequence
from xml.sax.saxutils import escape

MAX_ROWS = 5000
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value) -> str:
    """Neutralise spreadsheet formula injection (a cell starting with = + - @ would run in Excel)."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(_FORMULA_PREFIXES) else text


def to_csv(headers: Sequence[str], rows: Sequence[Sequence]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for row in rows[:MAX_ROWS]:
        writer.writerow([safe_cell(c) for c in row])
    return buf.getvalue().encode("utf-8-sig")  # BOM so Excel opens UTF-8 correctly


def to_pdf(title: str, headers: Sequence[str], rows: Sequence[Sequence]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    cell = styles["BodyText"]
    cell.fontSize = 8
    cell.leading = 10

    def p(value) -> Paragraph:  # Paragraph parses markup, so always escape user data
        return Paragraph(escape("" if value is None else str(value)), cell)

    data: List[list] = [[p(h) for h in headers]]
    data += [[p(c) for c in row] for row in rows[:MAX_ROWS]]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=28, bottomMargin=28)
    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef7")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#b8c2d1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    doc.build(
        [
            Paragraph(escape(title), styles["Title"]),
            Paragraph(f"Generated {stamp} - {len(data) - 1} row(s)", styles["Normal"]),
            Spacer(1, 10),
            table,
        ]
    )
    return buf.getvalue()
