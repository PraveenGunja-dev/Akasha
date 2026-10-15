"""The "Project snapshot" PDF attached to ordering emails - one A4 page:
key dates, where the modules are (ordered / received / on site / erected
against capacity), construction progress by stage (P6 block stages, from
Advanced planning), and the phase-wise ordering plan. Every figure is one the
Ordering Schedule shows; the data dates are printed on the page.
Drawn with matplotlib (already a dependency), no browser or office needed.
"""
import io
from typing import Dict, List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

BLUE, GREY, INK, MUTED, LINE = "#0b74b1", "#c9ced6", "#1f2937", "#6b7280", "#e5e7eb"
STATUS_COLOUR = {"Overdue": "#b42318", "FTC at risk": "#b42318", "Moved": "#b45309", "On plan": "#15803d"}


def _num(v) -> float:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def build(p: dict, ctx: Dict, plan: Optional[dict], orders: List[dict]) -> bytes:
    fig = plt.figure(figsize=(11.69, 8.27), dpi=110)   # A4 landscape
    fig.patch.set_facecolor("white")

    # Header
    fig.text(0.04, 0.945, "Akasha · Project snapshot", fontsize=10, color=BLUE, weight="bold")
    fig.text(0.04, 0.905, ctx.get("project_name", ""), fontsize=17, color=INK, weight="bold")
    sub = " · ".join(x for x in [ctx.get("project_id"), ctx.get("portfolio"), f"Origin {ctx.get('vendor_type')}"
                                 if ctx.get("vendor_type") else "", f"Priority {ctx.get('priority')}"] if x)
    fig.text(0.04, 0.875, sub, fontsize=9.5, color=MUTED)
    asof = " · ".join(x for x in [f"P6 as of {ctx['p6_as_of']}" if ctx.get("p6_as_of") else "",
                                  f"SAP as of {ctx['sap_as_of']}" if ctx.get("sap_as_of") else "",
                                  f"Generated {ctx.get('generated_at', '')}"] if x)
    fig.text(0.96, 0.905, asof, fontsize=8, color=MUTED, ha="right")

    # Key dates (left)
    ax = fig.add_axes([0.04, 0.56, 0.28, 0.28]); ax.axis("off")
    ax.set_title("Key dates", loc="left", fontsize=10.5, color=INK, weight="bold", pad=6)
    rows = [("Ordering date", ctx.get("module_ordering_date")), ("Modules needed at site", ctx.get("tc_delivery_date")),
            ("FTC (P6)", ctx.get("ftc_date")), ("LTA", ctx.get("lta_date")), ("SCOD", ctx.get("scod_date"))]
    for i, (k, v) in enumerate(rows):
        y = 0.88 - i * 0.19
        ax.text(0.0, y, k, fontsize=9, color=MUTED, transform=ax.transAxes)
        ax.text(1.0, y, (v or "-").split(" · ")[0], fontsize=9.5, color=INK, weight="bold", ha="right", transform=ax.transAxes)
        ax.plot([0, 1], [y - 0.07, y - 0.07], color=LINE, lw=0.8, transform=ax.transAxes)

    # Module position (middle)
    ax = fig.add_axes([0.38, 0.58, 0.20, 0.25])
    cap = _num(ctx.get("capacity_mwp"))
    labels = ["Ordered", "Received", "On site", "Erected"]
    vals = [_num(ctx.get(k)) for k in ("ordered_mwp", "received_mwp", "on_site_stock_mwp", "erected_mwp")]
    ax.barh(labels[::-1], [cap] * 4, color=GREY, height=0.55)
    ax.barh(labels[::-1], vals[::-1], color=BLUE, height=0.55)
    for i, v in enumerate(vals[::-1]):
        ax.text(cap * 1.02 if cap else v, i, f"{v:,.1f} MWp", va="center", fontsize=8.5, color=INK)
    ax.set_xlim(0, (cap or max(vals + [1])) * 1.45)
    ax.set_title(f"Modules (capacity {cap:,.1f} MWp)", loc="left", fontsize=10.5, color=INK, weight="bold")
    ax.tick_params(labelsize=8.5, colors=INK, length=0); ax.set_xticks([])
    for s in ax.spines.values(): s.set_visible(False)

    # Construction progress by stage (right)
    stages = (plan or {}).get("stages") or []
    ax = fig.add_axes([0.80, 0.58, 0.15, 0.25])
    ax.set_title("Construction progress (P6)", loc="left", fontsize=10.5, color=INK, weight="bold")
    if stages:
        names = [s.get("label") for s in stages][::-1]
        pcts = [float(s.get("pct") or 0) for s in stages][::-1]
        ax.barh(names, [100] * len(names), color=GREY, height=0.55)
        ax.barh(names, pcts, color="#15803d", height=0.55)
        for i, v in enumerate(pcts):
            ax.text(102, i, f"{v:.0f}%", va="center", fontsize=8.5, color=INK)
        ax.set_xlim(0, 125); ax.set_xticks([]); ax.tick_params(labelsize=8.5, colors=INK, length=0)
        for s in ax.spines.values(): s.set_visible(False)
    else:
        ax.axis("off"); ax.text(0, 0.5, "No block stages in P6 for this project", fontsize=9, color=MUTED)

    # Ordering plan by phase (bottom)
    ax = fig.add_axes([0.04, 0.08, 0.92, 0.40]); ax.axis("off")
    ax.set_title("Ordering plan by phase (Ordering Schedule)", loc="left", fontsize=10.5, color=INK, weight="bold", pad=8)
    head = ["Phase", "MWp", "Ordering date", "Ordering month", "Needed at site", "FTC (P6)", "Status"]
    xs = [0.0, 0.14, 0.24, 0.39, 0.53, 0.67, 0.81]
    for x, h in zip(xs, head):
        ax.text(x, 0.94, h, fontsize=8.5, color=MUTED, weight="bold", transform=ax.transAxes)
    ax.plot([0, 1], [0.91, 0.91], color=LINE, lw=1, transform=ax.transAxes)
    if not orders:
        ax.text(0, 0.82, "Nothing left to order in the plan.", fontsize=9, color=MUTED, transform=ax.transAxes)
    for i, o in enumerate(orders[:10]):
        y = 0.84 - i * 0.082
        status = ("Overdue" if o.get("overdue") else "FTC at risk" if not o.get("ftc_reachable", True)
                  else "Moved" if o.get("shifted") else "On plan")
        cells = [o.get("phase_label") or "-", f"{_num(o.get('mwp')):,.1f}", o.get("order_date") or "-",
                 ", ".join(o.get("months") or []) or "-", o.get("tc_date") or "-", o.get("ftc_date") or "-", status]
        for x, c in zip(xs, cells):
            colour = STATUS_COLOUR.get(c, INK) if c == status else INK
            ax.text(x, y, str(c), fontsize=8.5, color=colour, transform=ax.transAxes,
                    weight="bold" if c == status else "normal")
        ax.plot([0, 1], [y - 0.03, y - 0.03], color=LINE, lw=0.6, transform=ax.transAxes)
    fig.text(0.04, 0.03, "Ordering date = latest date to place the order (needed-at-site date minus supplier lead time). "
             "Needed at site = FTC minus 45 days. Figures as shown in the Akasha Ordering Schedule.",
             fontsize=7.5, color=MUTED)

    buf = io.BytesIO()
    fig.savefig(buf, format="pdf")
    plt.close(fig)
    return buf.getvalue()
