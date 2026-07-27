from __future__ import annotations

from pathlib import Path


def _rows(dataset: dict) -> list[tuple[str, str]]:
    summary = dataset["project_summary"]
    schedule = dataset["schedule"]
    return [
        ("Project status", str(summary.get("status") or "Unavailable")),
        ("P6 duration progress", f"{schedule.get('progress_pct')}%" if schedule.get("progress_pct") is not None else "Unavailable"),
        ("Completed activities", str(schedule.get("completed_activities"))),
        ("In-progress activities", str(schedule.get("in_progress_activities"))),
        ("Not-started activities", str(schedule.get("not_started_activities"))),
        ("SPI", str(schedule.get("spi")) if schedule.get("spi") is not None else "Unavailable"),
        ("CPI", str(schedule.get("cpi")) if schedule.get("cpi") is not None else "Unavailable"),
        ("Scheduled finish", str(summary.get("scheduled_finish") or "Unavailable")),
        ("P6 data date", str(summary.get("data_date") or "Unavailable")),
        ("P6 last synchronized", str(summary.get("last_synced_at") or "Unavailable")),
    ]


def _domain_rows(value: dict, limit: int = 10) -> list[tuple[str, str]]:
    rows = []
    for key, item in (value or {}).items():
        if key.startswith("_") or isinstance(item, (dict, list)) or item is None:
            continue
        rows.append((key.replace("_", " ").title(), str(item)))
        if len(rows) >= limit:
            break
    return rows or [("Status", "No mapped data")]


def render_project_progress_pdf(dataset: dict, path: Path) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    story = [
        Paragraph("AKASHA", styles["Title"]),
        Paragraph("Project Progress Report", styles["Heading1"]),
        Paragraph(dataset["metadata"]["project_name"], styles["Heading2"]),
        Spacer(1, 6 * mm),
        Paragraph("Executive Summary", styles["Heading2"]),
        Paragraph(dataset["executive_summary"], styles["BodyText"]),
        Spacer(1, 5 * mm),
        Paragraph("Project and Schedule", styles["Heading2"]),
    ]
    table = Table([["Metric", "Value"], *_rows(dataset)], colWidths=[70 * mm, 100 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3a5f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([table, Spacer(1, 5 * mm), Paragraph("Source Coverage", styles["Heading2"])])
    freshness = dataset["metadata"]["source_freshness"]
    story.append(Table([["Source", "Last synchronized"], *[
        [name, str(value or "No mapped data")] for name, value in freshness.items()
    ]], colWidths=[45 * mm, 125 * mm], style=TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
        ("PADDING", (0, 0), (-1, -1), 6),
    ])))
    for heading, key in [
        ("SAP Procurement", "procurement"),
        ("TC Transmission", "transmission"),
        ("Pulse Quality", "quality"),
    ]:
        story.extend([Spacer(1, 5 * mm), Paragraph(heading, styles["Heading2"])])
        story.append(Table([["Metric", "Value"], *_domain_rows(dataset[key])], colWidths=[70 * mm, 100 * mm], style=TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
            ("PADDING", (0, 0), (-1, -1), 6),
        ])))
    story.extend([Spacer(1, 5 * mm), Paragraph("In-Progress Activities", styles["Heading2"])])
    activities = dataset["in_progress_activities"].get("activities") or []
    activity_rows = [[row.get("activity_id"), row.get("name"), f"{row.get('percent_complete')}%"] for row in activities]
    story.append(Table([["ID", "Activity", "Complete"], *activity_rows] if activity_rows else [["Status"], ["No in-progress activities"]], style=TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("PADDING", (0, 0), (-1, -1), 4),
    ])))
    SimpleDocTemplate(str(path), pagesize=A4, rightMargin=18*mm, leftMargin=18*mm).build(story)


def render_project_progress_docx(dataset: dict, path: Path) -> None:
    from docx import Document
    from docx.shared import RGBColor

    document = Document()
    title = document.add_heading("AKASHA", 0)
    title.runs[0].font.color.rgb = RGBColor(31, 58, 95)
    document.add_heading("Project Progress Report", level=1)
    document.add_heading(dataset["metadata"]["project_name"], level=2)
    document.add_heading("Executive Summary", level=2)
    document.add_paragraph(dataset["executive_summary"])
    document.add_heading("Project and Schedule", level=2)
    table = document.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    table.rows[0].cells[0].text = "Metric"
    table.rows[0].cells[1].text = "Value"
    for label, value in _rows(dataset):
        cells = table.add_row().cells
        cells[0].text = label
        cells[1].text = value
    document.add_heading("Source Coverage", level=2)
    for name, value in dataset["metadata"]["source_freshness"].items():
        document.add_paragraph(f"{name}: {value or 'No mapped data'}")
    for heading, key in [
        ("SAP Procurement", "procurement"),
        ("TC Transmission", "transmission"),
        ("Pulse Quality", "quality"),
    ]:
        document.add_heading(heading, level=2)
        domain_table = document.add_table(rows=1, cols=2)
        domain_table.style = "Table Grid"
        domain_table.rows[0].cells[0].text = "Metric"
        domain_table.rows[0].cells[1].text = "Value"
        for label, value in _domain_rows(dataset[key]):
            cells = domain_table.add_row().cells
            cells[0].text = label
            cells[1].text = value
    document.add_heading("In-Progress Activities", level=2)
    activity_table = document.add_table(rows=1, cols=3)
    activity_table.style = "Table Grid"
    for cell, value in zip(activity_table.rows[0].cells, ["ID", "Activity", "Complete"]):
        cell.text = value
    for row in dataset["in_progress_activities"].get("activities") or []:
        cells = activity_table.add_row().cells
        cells[0].text = str(row.get("activity_id") or "")
        cells[1].text = str(row.get("name") or "")
        cells[2].text = f"{row.get('percent_complete')}%"
    document.add_paragraph("Confidential - generated by Akasha from synchronized source data.")
    document.save(str(path))
