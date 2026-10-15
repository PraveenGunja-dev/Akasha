"""Template rendering: {{variables}} only - no expressions, loops or code, so a
template edited in the admin screen can never run anything. Values are
HTML-escaped (except the few Akasha builds itself, catalogue.HTML_VARIABLES),
and a missing value reads "Not available", never a blank.

The body is light text (see catalogue.py): "Label: value" lines become a
details table, "Required Action:" is highlighted, **bold** works, blank lines
split paragraphs. The result is wrapped in one email-safe layout (inline CSS,
table-based, 640px) with the no-reply notice and the data dates in the footer.
"""
import html
import re
from typing import Dict, List, Optional, Tuple

from .catalogue import HTML_VARIABLES, VARIABLES

VAR_RE = re.compile(r"\{\{\s*([^{}]*?)\s*\}\}")
KV_RE = re.compile(r"^([A-Za-z][^:{}]{1,48}):\s*(.*)$")
NA = "Not available"
FONT = "font-family:'Segoe UI',Arial,Helvetica,sans-serif;"
# Optional parts: empty means "leave it out", not "Not available" - an
# unphased project has no phase, which is not missing data.
OPTIONAL = {"phase"}
EMPTY_PARENS = re.compile(r"\s*\(\s*\)")

SEVERITY = {  # chip label, chip colour, accent
    "info":     ("Information", "#0b74b1", "#e7f1f8"),
    "action":   ("Action needed", "#b45309", "#fdf3e1"),
    "critical": ("Critical", "#b42318", "#fdecea"),
}


def validate(*texts: str) -> List[str]:
    """Problems that must be fixed before a template is saved."""
    out, seen = [], set()
    for t in texts:
        for m in VAR_RE.finditer(t or ""):
            name = m.group(1)
            if not name:
                msg = "An empty placeholder {{}} - put a variable name inside it"
            elif name not in VARIABLES:
                msg = f"Unknown variable {{{{{name}}}}} - pick one from the variable list"
            else:
                continue
            if msg not in seen:
                seen.add(msg)
                out.append(msg)
    return out


def used_variables(*texts: str) -> List[str]:
    return sorted({m.group(1) for t in texts for m in VAR_RE.finditer(t or "") if m.group(1)})


def _value(ctx: Dict, name: str, as_html: bool) -> str:
    v = ctx.get(name)
    if v is None or (isinstance(v, str) and not v.strip()):
        return "" if name in OPTIONAL else NA
    if name in HTML_VARIABLES:
        return str(v) if as_html else re.sub(r"<[^>]+>", " ", str(v))
    return html.escape(str(v)) if as_html else str(v)


def fill(text: str, ctx: Dict, as_html: bool = False) -> str:
    out = VAR_RE.sub(lambda m: _value(ctx, m.group(1), as_html), text or "")
    return EMPTY_PARENS.sub("", out)


def subject(text: str, ctx: Dict) -> str:
    return " ".join(fill(text, ctx).split())


def _inline(s: str) -> str:
    """Escaped text -> bold and links."""
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    return re.sub(r"(https?://[^\s<]+)", r'<a href="\1" style="color:#0b74b1;">\1</a>', s)


def body_html(text: str, ctx: Dict) -> str:
    """The body as HTML blocks (paragraphs, details tables, action box)."""
    # Escape the template's own text, then fill values (escaped themselves).
    lines = fill(html.escape(text or "", quote=False).replace("&#x27;", "'"), ctx, as_html=True).split("\n")
    blocks, para, rows = [], [], []

    def flush_para():
        if para:
            blocks.append(f'<p style="margin:0 0 14px;line-height:1.55;{FONT}">{_inline(" ".join(para))}</p>')
            para.clear()

    def flush_rows():
        if rows:
            trs = "".join(
                f'<tr><td style="{FONT}font-size:13px;line-height:1.4;padding:7px 12px;border-bottom:1px solid #eef0f3;color:#5b6472;width:42%;'
                f'vertical-align:top;">{k}</td><td style="{FONT}font-size:13px;line-height:1.4;padding:7px 12px;border-bottom:1px solid #eef0f3;'
                f'color:#111827;font-weight:600;vertical-align:top;">{_inline(v)}</td></tr>' for k, v in rows)
            blocks.append('<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
                          'style="border:1px solid #e5e7eb;border-radius:8px;border-collapse:separate;'
                          f'margin:0 0 16px;font-size:13px;">{trs}</table>')
            rows.clear()

    for raw in lines:
        line = raw.strip()
        if not line:
            flush_para(); flush_rows()
            continue
        if line.lower().startswith("required action:"):
            flush_para(); flush_rows()
            blocks.append(f'<div style="{FONT}margin:0 0 16px;padding:11px 14px;border-left:3px solid #b45309;'
                          'background:#fdf6ec;border-radius:4px;line-height:1.5;"><strong>Required action:</strong> '
                          f'{_inline(line.split(":", 1)[1].strip())}</div>')
            continue
        kv = KV_RE.match(line)
        if kv and not line.endswith(".") and len(kv.group(2)) < 300:
            flush_para()
            rows.append((kv.group(1).strip(), kv.group(2).strip()))
            continue
        flush_rows()
        para.append(line)
    flush_para(); flush_rows()
    return "\n".join(blocks)


def body_text(text: str, ctx: Dict) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", fill(text, ctx))


def ack_block(ack: Optional[Dict]) -> str:
    """The acknowledgement panel: the level this email went out at, why,
    and the button to acknowledge in Akasha. Sign-in identifies who
    acknowledges, and the page needs a deliberate click - a link scanner
    opening the URL acknowledges nothing."""
    if not ack:
        return ""
    e = html.escape
    why = f'<div style="{FONT}font-size:12.5px;color:#4b5563;margin:0 0 10px;line-height:1.5;">{e(ack["why"])}</div>' if ack.get("why") else ""
    button = (f'<table role="presentation" cellspacing="0" cellpadding="0"><tr><td style="border-radius:6px;background:#0b74b1;">'
              f'<a href="{e(ack["url"])}" style="{FONT}display:inline-block;padding:9px 18px;font-size:13px;font-weight:600;'
              f'color:#ffffff;text-decoration:none;border-radius:6px;">{e(ack.get("button") or "Acknowledge in Akasha")}</a></td></tr></table>') if ack.get("url") else (
              f'<div style="{FONT}font-size:12px;color:#b45309;">AKASHA_PUBLIC_URL is not set - acknowledge from the Alerts page in Akasha.</div>')
    return (f'<tr><td style="padding:0 24px 18px;"><table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
            f'style="border:1px solid #d6e6f2;background:#f4f9fc;border-radius:8px;"><tr><td style="padding:12px 14px;">'
            f'<div style="{FONT}font-size:11px;font-weight:700;letter-spacing:.4px;text-transform:uppercase;color:#0b74b1;margin:0 0 6px;">'
            f'Level {e(str(ack.get("level", 1)))} of 3 · {e(ack.get("title") or "acknowledgement required")}</div>{why}'
            f'<div style="{FONT}font-size:12.5px;color:#1f2937;margin:0 0 10px;line-height:1.5;">{e(ack.get("ask") or "")}</div>'
            f'{button}</td></tr></table></td></tr>')


def layout(inner: str, severity: str, ctx: Dict, test_banner: str = "", ack: Optional[Dict] = None) -> str:
    label, colour, wash = SEVERITY.get(severity, SEVERITY["info"])
    support = ctx.get("support_contact")
    asof = " · ".join(x for x in (
        f"P6 data as of {ctx['p6_as_of']}" if ctx.get("p6_as_of") else "",
        f"SAP data as of {ctx['sap_as_of']}" if ctx.get("sap_as_of") else "") if x)
    banner = (f'<tr><td style="background:#fff4ce;color:#7a5a00;padding:8px 24px;font-size:12px;">'
              f'{html.escape(test_banner)}</td></tr>') if test_banner else ""
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"></head>
<body style="margin:0;padding:0;background:#f3f4f6;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f3f4f6;padding:24px 0;">
<tr><td align="center">
<table role="presentation" width="640" cellspacing="0" cellpadding="0" style="max-width:640px;width:100%;background:#ffffff;border:1px solid #e5e7eb;border-radius:10px;overflow:hidden;font-family:Segoe UI,Arial,sans-serif;font-size:14px;color:#1f2937;">
<tr><td style="padding:16px 24px;border-bottom:3px solid {colour};">
  <table role="presentation" width="100%"><tr>
    <td style="{FONT}font-size:17px;font-weight:700;color:#0b74b1;letter-spacing:.2px;">Akasha <span style="font-weight:400;color:#6b7280;font-size:13px;">Intelligence</span></td>
    <td align="right" style="{FONT}"><span style="display:inline-block;padding:3px 10px;border-radius:999px;background:{wash};color:{colour};font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.4px;">{label}</span></td>
  </tr></table>
</td></tr>
{banner}
<tr><td style="padding:22px 24px 8px;{FONT}font-size:14px;color:#1f2937;">{inner}</td></tr>
{ack_block(ack)}
<tr><td style="{FONT}padding:14px 24px 18px;background:#f9fafb;border-top:1px solid #e5e7eb;font-size:11.5px;line-height:1.55;color:#6b7280;">
  This is an automated message from Akasha. Replies to this address are not monitored.
  To act, use the link above{f"; for questions contact {html.escape(support)}" if support else ""}.<br>
  {html.escape(asof + (" · " if asof else "") + "Generated " + str(ctx.get("generated_at", "")))}
</td></tr>
</table>
</td></tr></table>
</body></html>"""


def render(template, ctx: Dict, test_banner: str = "", ack: Optional[Dict] = None) -> Tuple[str, str, str]:
    """(subject, html, text) for a template object or dict."""
    get = (lambda k: template.get(k)) if isinstance(template, dict) else (lambda k: getattr(template, k))
    subj = subject(get("subject"), ctx)
    html_out = layout(body_html(get("body"), ctx), get("severity") or "info", ctx, test_banner, ack)
    ack_text = ""
    if ack:
        ack_text = (f"\n\nLevel {ack.get('level', 1)} of 3 - {ack.get('title') or 'acknowledgement required'}. "
                    f"{ack.get('why') or ''} {ack.get('ask') or ''}\n"
                    f"{ack.get('button') or 'Acknowledge in Akasha'}: {ack.get('url') or 'the Alerts page in Akasha'}")
    text_out = body_text(get("body"), ctx) + ack_text + (
        "\n\n--\nThis is an automated message from Akasha. Replies to this address are not monitored.")
    return subj, html_out, text_out
