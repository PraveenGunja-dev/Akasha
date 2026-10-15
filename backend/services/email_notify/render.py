"""Template rendering: {{variables}} only - no expressions, loops or code, so a
template edited in the admin screen can never run anything. Values are
HTML-escaped (except the few Akasha builds itself, catalogue.HTML_VARIABLES),
and a missing value reads "Not available", never a blank.

The body is light text (see catalogue.py): "Label: value" lines become a
details table, "Required Action:" is highlighted, **bold** works, blank lines
split paragraphs. The result is wrapped in one email-safe layout (inline CSS,
table-based, fluid up to 960px) with the no-reply notice and the data dates in the footer.
"""
import html
import os
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


# A unit after a missing value ("Not available MWp") reads as a figure - drop it.
NA_UNIT = re.compile(r"Not available\s+(?:MWp|MWac|MW|days|d)\b")


def fill(text: str, ctx: Dict, as_html: bool = False) -> str:
    out = VAR_RE.sub(lambda m: _value(ctx, m.group(1), as_html), text or "")
    return NA_UNIT.sub(NA, EMPTY_PARENS.sub("", out))


def subject(text: str, ctx: Dict) -> str:
    return " ".join(fill(text, ctx).split())


def _inline(s: str) -> str:
    """Escaped text -> bold and links."""
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    return re.sub(r"(https?://[^\s<]+)", r'<a href="\1" style="color:#0b74b1;">\1</a>', s)


INK, MUTED, RULE, BRAND = "#111827", "#5b6472", "#e7eaee", "#0b74b1"

# The Adani banner at the top of every email. It travels INSIDE the email as an
# inline image (Content-ID), so mail clients show it without "download
# pictures" - a linked image is blocked by default in Outlook. sender.send()
# attaches it whenever the HTML refers to it.
BANNER_CID = "akasha-banner"
BANNER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "email_banner.jpg")


def banner_bytes() -> bytes:
    with open(BANNER_PATH, "rb") as f:
        return f.read()


def for_browser(html_text: str) -> str:
    """The same email for a browser preview (admin screen, email log): the
    inline image as a data URI, since a browser cannot resolve cid:."""
    if f"cid:{BANNER_CID}" not in (html_text or ""):
        return html_text
    import base64
    uri = "data:image/jpeg;base64," + base64.b64encode(banner_bytes()).decode()
    return html_text.replace(f"cid:{BANNER_CID}", uri)
# "View in Akasha: <link>" lines become buttons, not table rows.
LINK_LINE = re.compile(r"^(?P<label>[^:]*akasha[^:]*):\s*(?P<url>https?://\S+)\s*$", re.IGNORECASE)


def body_html(text: str, ctx: Dict) -> Tuple[str, List[Tuple[str, str]]]:
    """The body as HTML blocks (paragraphs, a details table, the required
    action) and the Akasha links it names, which the layout shows as buttons."""
    # Escape the template's own text, then fill values (escaped themselves).
    lines = fill(html.escape(text or "", quote=False).replace("&#x27;", "'"), ctx, as_html=True).split("\n")
    blocks, para, rows, links = [], [], [], []

    def flush_para():
        if para:
            blocks.append(f'<p style="{FONT}margin:0 0 16px;font-size:14px;line-height:1.6;color:#1f2937;">{_inline(" ".join(para))}</p>')
            para.clear()

    def flush_rows():
        if rows:
            trs = "".join(
                f'<tr><td style="{FONT}font-size:12.5px;line-height:1.45;padding:8px 14px;border-top:{"0" if n == 0 else "1px solid " + RULE};'
                f'color:{MUTED};width:32%;vertical-align:top;">{k}</td>'
                f'<td style="{FONT}font-size:13.5px;line-height:1.45;padding:8px 14px;border-top:{"0" if n == 0 else "1px solid " + RULE};'
                f'color:{INK};font-weight:600;vertical-align:top;">{_inline(v)}</td></tr>' for n, (k, v) in enumerate(rows))
            blocks.append(f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
                          f'style="border:1px solid {RULE};border-radius:8px;border-collapse:separate;margin:0 0 18px;background:#ffffff;">{trs}</table>')
            rows.clear()

    for raw in lines:
        line = raw.strip()
        if not line:
            flush_para(); flush_rows()
            continue
        plain = re.sub(r"<[^>]+>", "", line)
        link = LINK_LINE.match(plain)
        if link:
            flush_para(); flush_rows()
            links.append((link.group("label").strip(), link.group("url")))
            continue
        if line.lower().startswith("required action:"):
            flush_para(); flush_rows()
            blocks.append(f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin:0 0 18px;">'
                          f'<tr><td style="{FONT}padding:12px 16px;border-left:4px solid #b45309;background:#fdf6ec;border-radius:4px;">'
                          f'<div style="font-size:11px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;color:#92400e;margin:0 0 3px;">Required action</div>'
                          f'<div style="font-size:14px;line-height:1.55;color:{INK};">{_inline(line.split(":", 1)[1].strip())}</div></td></tr></table>')
            continue
        kv = KV_RE.match(line)
        if kv and not line.endswith(".") and len(kv.group(2)) < 300:
            flush_para()
            rows.append((kv.group(1).strip(), kv.group(2).strip()))
            continue
        flush_rows()
        para.append(line)
    flush_para(); flush_rows()
    return "\n".join(blocks), links


def body_text(text: str, ctx: Dict) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", fill(text, ctx))


# What each level of intimation means to the person reading it.
LEVEL_BAND = {
    1: ("Level 1 · First notice", "#eef6fb", "#0b5e8f", "You are receiving this as part of the team responsible."),
    2: ("Level 2 · Escalation", "#fdf6ec", "#92400e", "This has reached Level 2: it needs attention beyond the first notice."),
    3: ("Level 3 · Senior escalation", "#fdecea", "#b42318", "This has reached Level 3: senior leadership is now informed."),
}


def _button(label: str, url: str, primary: bool) -> str:
    e = html.escape
    bg, fg, border = (BRAND, "#ffffff", BRAND) if primary else ("#ffffff", BRAND, "#b9d6ea")
    return (f'<td style="padding:0 8px 8px 0;"><table role="presentation" cellspacing="0" cellpadding="0"><tr>'
            f'<td style="border-radius:6px;background:{bg};border:1px solid {border};">'
            f'<a href="{e(url)}" style="{FONT}display:inline-block;padding:10px 18px;font-size:13.5px;font-weight:600;'
            f'color:{fg};text-decoration:none;border-radius:6px;">{e(label)}</a></td></tr></table></td>')


def _headline(subj: str) -> Tuple[str, str, str]:
    """'Akasha Critical Alert | Project 140 Days Behind AOP | Group - Cement'
    -> (kicker, title, subtitle). A subject without bars is the title."""
    parts = [x.strip() for x in subj.replace("[TEST]", "").split("|") if x.strip()]
    if len(parts) >= 3:
        return parts[0], parts[1], " | ".join(parts[2:])
    if len(parts) == 2:
        return parts[0], parts[1], ""
    return "", subj, ""


def layout(inner: str, severity: str, ctx: Dict, test_banner: str = "", ack: Optional[Dict] = None,
           subj: str = "", links: Optional[List[Tuple[str, str]]] = None) -> str:
    """One email-safe page (tables, inline CSS; fluid, filling the reading pane
    up to 960px, a fixed 960px frame in Outlook desktop): brand header, the
    level of intimation, the headline, the body, the actions, the footer."""
    e = html.escape
    label, colour, wash = SEVERITY.get(severity, SEVERITY["info"])
    support = ctx.get("support_contact")
    asof = " · ".join(x for x in (
        f"P6 data as of {ctx['p6_as_of']}" if ctx.get("p6_as_of") else "",
        f"SAP data as of {ctx['sap_as_of']}" if ctx.get("sap_as_of") else "") if x)
    banner = (f'<tr><td style="{FONT}background:#fff4ce;color:#7a5a00;padding:9px 28px;font-size:12px;">'
              f'{e(test_banner)}</td></tr>') if test_banner else ""
    kicker, title, subtitle = _headline(subj) if subj else ("", "", "")

    level_row = ""
    if ack:
        lv = max(1, min(3, int(ack.get("level") or 1)))
        name, bg, fg, meaning = LEVEL_BAND[lv]
        why = ack.get("why") or meaning
        level_row = (f'<tr><td style="{FONT}padding:10px 28px;background:{bg};border-bottom:1px solid {RULE};">'
                     f'<span style="font-size:11px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;color:{fg};">{e(name)}</span>'
                     f'<span style="font-size:12.5px;color:#374151;"> &nbsp;{e(why)}</span></td></tr>')

    head = ""
    if title:
        head = (f'<tr><td style="{FONT}padding:26px 28px 6px;">'
                + (f'<div style="font-size:11px;font-weight:700;letter-spacing:.6px;text-transform:uppercase;color:{colour};margin:0 0 6px;">{e(kicker)}</div>' if kicker else "")
                + f'<div style="font-size:21px;line-height:1.3;font-weight:700;color:{INK};">{e(title)}</div>'
                + (f'<div style="font-size:14px;line-height:1.4;color:{MUTED};margin:4px 0 0;">{e(subtitle)}</div>' if subtitle else "")
                + '</td></tr>')

    buttons = []
    if ack and ack.get("url"):
        buttons.append(_button(ack.get("button") or "Acknowledge in Akasha", ack["url"], True))
    for i, (lbl, url) in enumerate(links or []):
        buttons.append(_button(lbl, url, primary=not buttons))
    actions = ""
    if ack or buttons:
        ask = (f'<div style="{FONT}font-size:12.5px;line-height:1.5;color:{MUTED};margin:0 0 12px;">{e(ack.get("ask") or "")}</div>'
               if ack and ack.get("ask") else "")
        no_url = (f'<div style="{FONT}font-size:12px;color:#b45309;margin:0 0 8px;">AKASHA_PUBLIC_URL is not set - open Akasha to act on this alert.</div>'
                  if ack and not ack.get("url") else "")
        actions = (f'<tr><td style="padding:2px 28px 18px;">{ask}{no_url}'
                   f'<table role="presentation" cellspacing="0" cellpadding="0"><tr>{"".join(buttons)}</tr></table></td></tr>')

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta name="color-scheme" content="light"></head>
<body style="margin:0;padding:0;background:#eef1f4;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#eef1f4;padding:14px 6px;">
<tr><td align="center">
<!--[if mso]><table role="presentation" width="960" align="center" cellspacing="0" cellpadding="0"><tr><td><![endif]-->
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="width:100%;max-width:960px;background:#ffffff;border:1px solid #dde2e8;border-radius:12px;overflow:hidden;">
<tr><td style="padding:0;line-height:0;font-size:0;"><img src="cid:{BANNER_CID}" width="960" alt="Adani - Growth with Goodness" style="display:block;width:100%;max-width:960px;height:auto;border:0;outline:none;text-decoration:none;"></td></tr>
<tr><td style="height:4px;background:{colour};font-size:0;line-height:0;">&nbsp;</td></tr>
<tr><td style="padding:16px 28px;border-bottom:1px solid {RULE};">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr>
    <td style="{FONT}font-size:16px;font-weight:700;color:{BRAND};letter-spacing:.3px;">AKASHA <span style="font-weight:400;color:#8a94a3;font-size:12.5px;letter-spacing:0;">Intelligence · Adani Green Energy</span></td>
    <td align="right" style="{FONT}"><span style="display:inline-block;padding:4px 10px;border-radius:999px;background:{wash};color:{colour};font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;">{label}</span></td>
  </tr></table>
</td></tr>
{banner}
{level_row}
{head}
<tr><td style="{FONT}padding:16px 28px 2px;font-size:14px;color:#1f2937;">{inner}</td></tr>
{actions}
<tr><td style="{FONT}padding:16px 28px 20px;background:#f7f8fa;border-top:1px solid {RULE};font-size:11.5px;line-height:1.6;color:#6b7280;">
  Automated message from Akasha - replies to this address are not monitored{f"; for questions contact {e(support)}" if support else ""}.<br>
  Figures are from the source systems as of the times below; forecasts and calculated dates are labelled as such.<br>
  {e(asof + (" · " if asof else "") + "Generated " + str(ctx.get("generated_at", "")))}
</td></tr>
</table>
<!--[if mso]></td></tr></table><![endif]-->
</td></tr></table>
</body></html>"""


def render(template, ctx: Dict, test_banner: str = "", ack: Optional[Dict] = None) -> Tuple[str, str, str]:
    """(subject, html, text) for a template object or dict."""
    get = (lambda k: template.get(k)) if isinstance(template, dict) else (lambda k: getattr(template, k))
    subj = subject(get("subject"), ctx)
    inner, links = body_html(get("body"), ctx)
    html_out = layout(inner, get("severity") or "info", ctx, test_banner, ack, subj, links)
    ack_text = ""
    if ack:
        lv = max(1, min(3, int(ack.get("level") or 1)))
        ack_text = (f"\n\n{LEVEL_BAND[lv][0]} - {ack.get('why') or LEVEL_BAND[lv][3]} {ack.get('ask') or ''}\n"
                    f"{ack.get('button') or 'Acknowledge in Akasha'}: {ack.get('url') or 'the Alerts page in Akasha'}")
    text_out = body_text(get("body"), ctx) + ack_text + (
        "\n\n--\nAutomated message from Akasha. Replies to this address are not monitored.")
    return subj, html_out, text_out
