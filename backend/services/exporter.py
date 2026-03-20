from __future__ import annotations

import io
import json
from datetime import datetime
from typing import Any, Dict

from backend.services.transcriber import format_timestamp


def to_markdown(session: Dict[str, Any]) -> str:
    lines = []
    title = session.get("title") or "Video Notes"
    lines += [f"# {title}", ""]

    meta = []
    if session.get("source_url"):
        meta.append(f"**Source:** {session['source_url']}")
    if session.get("duration"):
        meta.append(f"**Duration:** {format_timestamp(session['duration'])}")
    if session.get("channel"):
        meta.append(f"**Channel:** {session['channel']}")
    if meta:
        lines += [" | ".join(meta), ""]

    lines.append(f"*Generated on {datetime.utcnow().strftime('%B %d, %Y at %H:%M UTC')} by VideoNotes AI — Armaan Manoj Kumar*")
    lines += ["", "---", ""]

    if session.get("executive_summary"):
        lines += ["## TL;DR", "", session["executive_summary"], ""]
    if session.get("key_points"):
        lines += ["## Key Points", ""]
        for pt in session["key_points"]:
            lines.append(f"- {pt}")
        lines.append("")
    if session.get("summary"):
        lines += ["## Summary", "", session["summary"], ""]
    if session.get("topics"):
        lines += ["## Topics", "", " | ".join(session["topics"]), ""]
    if session.get("chapters"):
        lines += ["## Chapters", ""]
        for ch in session["chapters"]:
            lines.append(f"### [{format_timestamp(ch.get('start_time', 0))} - {format_timestamp(ch.get('end_time', 0))}] {ch['title']}")
            if ch.get("summary"):
                lines.append(ch["summary"])
            lines.append("")
    if session.get("key_timestamps"):
        lines += ["## Key Timestamps", ""]
        for ts in sorted(session["key_timestamps"], key=lambda x: x.get("time", 0)):
            lines.append(f"- `{format_timestamp(ts.get('time', 0))}` - {ts['label']} ({ts.get('importance', 3)}/5)")
        lines.append("")
    if session.get("action_items"):
        lines += ["## Action Items", ""]
        for a in sorted(session["action_items"], key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.get("priority", "medium"), 1)):
            owner = f" (Owner: {a['owner']})" if a.get("owner") else ""
            lines.append(f"- [ ] [{a.get('priority', 'medium').upper()}] {a['task']}{owner}")
            if a.get("context"):
                lines.append(f"  > {a['context']}")
        lines.append("")
    if session.get("transcript"):
        lines += ["## Full Transcript", "", session["transcript"], ""]

    return "\n".join(lines)


def to_pdf(session: Dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, ListFlowable, ListItem

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=20*mm, leftMargin=20*mm, topMargin=20*mm, bottomMargin=20*mm)
    styles = getSampleStyleSheet()
    ACCENT = colors.HexColor("#6366f1")
    DARK = colors.HexColor("#1e1b4b")

    h1 = ParagraphStyle("H1", parent=styles["Heading1"], textColor=DARK, fontSize=22, spaceAfter=6)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=ACCENT, fontSize=14, spaceBefore=14, spaceAfter=4)
    h3 = ParagraphStyle("H3", parent=styles["Heading3"], textColor=DARK, fontSize=11, spaceBefore=8, spaceAfter=2)
    body = ParagraphStyle("Body", parent=styles["Normal"], fontSize=9, leading=14)
    meta_style = ParagraphStyle("Meta", parent=styles["Normal"], fontSize=8, textColor=colors.gray)

    story = []
    story.append(Paragraph(session.get("title") or "Video Notes", h1))

    meta_parts = []
    if session.get("duration"):
        meta_parts.append(f"Duration: {format_timestamp(session['duration'])}")
    if session.get("channel"):
        meta_parts.append(f"Channel: {session['channel']}")
    meta_parts.append(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} by Armaan Manoj Kumar")
    story += [Paragraph(" | ".join(meta_parts), meta_style), Spacer(1, 8), HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e0e0f0"), spaceAfter=8)]

    if session.get("executive_summary"):
        story += [Paragraph("TL;DR", h2), Paragraph(session["executive_summary"], body), Spacer(1, 8)]
    if session.get("key_points"):
        story.append(Paragraph("Key Points", h2))
        story += [ListFlowable([ListItem(Paragraph(pt, body), bulletColor=ACCENT) for pt in session["key_points"]], bulletType="bullet"), Spacer(1, 8)]
    if session.get("summary"):
        story += [Paragraph("Summary", h2), Paragraph(session["summary"], body), Spacer(1, 8)]
    if session.get("action_items"):
        story.append(Paragraph("Action Items", h2))
        pri_colors = {"high": "#ef4444", "medium": "#f59e0b", "low": "#22c55e"}
        for a in session["action_items"]:
            col = pri_colors.get(a.get("priority", "medium"), "#888")
            story.append(Paragraph(f'<font color="{col}">[{a.get("priority","medium").upper()}]</font> {a["task"]}', body))
            if a.get("context"):
                story.append(Paragraph(f"Context: {a['context']}", meta_style))
        story.append(Spacer(1, 8))

    doc.build(story)
    return buffer.getvalue()


def export_session(session: Dict[str, Any], fmt: str) -> tuple[bytes, str, str]:
    title_slug = (session.get("title") or "notes").replace(" ", "_")[:40]
    if fmt == "pdf":
        return to_pdf(session), "application/pdf", f"{title_slug}.pdf"
    elif fmt == "json":
        return json.dumps(session, indent=2, default=str).encode(), "application/json", f"{title_slug}.json"
    else:
        return to_markdown(session).encode("utf-8"), "text/markdown; charset=utf-8", f"{title_slug}.md"
