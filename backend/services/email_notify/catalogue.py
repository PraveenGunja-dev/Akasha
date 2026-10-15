"""What the email module knows about: distribution groups, the variables a
template may use, the triggers that fire templates, and the starting
templates. Templates are SEEDED from here once and then belong to the
administrators (database, versioned) - later edits here never overwrite theirs.

Template text format (kept simple on purpose, so it can be edited safely):
  - {{variable}} is replaced with the value, or "Not available" when there is none
  - A line "Label: value" becomes a row of the details table
  - "Required Action: ..." is highlighted
  - **text** is bold; a blank line starts a new paragraph
"""

# ── Distribution groups ──────────────────────────────────────────────────────
GROUPS = {
    "tc_ordering": "TC Ordering",
    "tc_head":     "TC Head",
    "projects":    "Projects",
    "pmag":        "PMAG",
    "executive":   "Executive / CEO",
    "tc_stores":   "TC Stores",
    "finance":     "Finance",
    "admin":       "Akasha Admin",
}

# ── Variables ────────────────────────────────────────────────────────────────
# key -> (label, meaning / source, sample). `html` variables are built by
# Akasha (escaped inside) and inserted as-is; all others are escaped.
VARIABLES = {
    # Project
    "project_name":          ("Project", "Project name (Ordering Schedule)", "SECI VIII PPA"),
    "project_id":            ("P6 project ID", "Project master", "FY26-P05"),
    "phase":                 ("Phase", "FTC phase the order is for (blank when the project is unphased)", "Ph-I"),
    "portfolio":             ("Portfolio", "Project master cluster", "Solar Khavda"),
    "vendor_type":           ("Module origin", "ALMM / China / SEA / DCR / ALCM", "China"),
    "priority":              ("Priority", "Ordering priority", "P1"),
    "capacity_mwp":          ("Project capacity (MWp)", "Project master", "408.0"),
    # Quantities
    "module_quantity_mwp":   ("Quantity to order (MWp)", "This phase's order in the Ordering Schedule", "120.5"),
    "balance_ordering_mwp":  ("Balance to order (MWp)", "Capacity not yet on a PO (SAP)", "120.5"),
    "ordered_mwp":           ("Ordered till now (MWp)", "Module POs in SAP (ZPSPS007)", "287.5"),
    "received_mwp":          ("Received (MWp)", "SAP total receipt", "250.0"),
    "in_transit_mwp":        ("In transit (MWp)", "SAP", "20.0"),
    "on_site_stock_mwp":     ("Modules on site (MWp)", "SAP MB52 stock", "40.0"),
    "erected_mwp":           ("Erected (MWp)", "P6 module erection", "180.0"),
    "erection_pct":          ("Erection (% of capacity)", "erected / capacity", "44%"),
    "construction_progress": ("Construction progress", "P6 block stages: piling, capping, structure, purlin, module", "Piling 100% · Structure 80% · Module 45%"),
    # Dates
    "module_ordering_date":  ("Ordering date", "Latest date to place the order (TC date - supplier lead time)", "21-Nov-26"),
    "tc_delivery_date":      ("Modules needed at site", "TC date (FTC - 45 days)", "08-Mar-27"),
    "ftc_date":              ("FTC date (P6)", "Phase FTC milestone in P6", "22-Apr-27"),
    "lta_date":              ("LTA date", "Connectivity ECOD", "30-Jun-27"),
    "scod_date":             ("SCOD", "Scheduled COD", "31-Mar-27"),
    "days_to_ordering":      ("Days to ordering date", "Ordering date - today", "30"),
    "days_overdue":          ("Days overdue", "Today - ordering date", "12"),
    "revised_ordering_month": ("Ordering month in the plan", "Month the Ordering Schedule now places the order", "Oct-26"),
    "forecast_tc_date":      ("Expected site delivery (calculated)", "Order month + lead time - a calculation, not a P6 date", "16-Feb-27"),
    "forecast_ftc_date":     ("Forecast FTC (calculated)", "Expected site delivery + 45 days - a calculation, not the P6 date", "02-Apr-27"),
    "ftc_shortfall_days":    ("FTC shortfall (days)", "Days the order is too late for the P6 FTC", "122"),
    # Status / reasons
    "ordering_status":       ("Ordering status", "From SAP POs against the requirement", "Ordered 287.5 of 408.0 MWp - 120.5 MWp to order"),
    "risk_reason":           ("Risk", "Why the schedule is at risk, from the Ordering Schedule's own checks", "FTC cannot be met from the current ordering month (122 days short)"),
    "shift_reason":          ("Why it moved", "Vendor allocation that moved the order", "China 750 MWac/month vendor allocation full in Nov-26"),
    "escalation_level":      ("Escalation", "Overdue escalation step", "Level 2 - 14 days overdue"),
    # Changes
    "changed_date_field":    ("Date changed", "Which date moved", "FTC date"),
    "previous_date":         ("Previous date", "Value before the change", "22-Apr-27"),
    "revised_date":          ("Revised date", "Value now", "15-May-27"),
    "date_variance_days":    ("Variance (days)", "Revised - previous (positive = later)", "+23"),
    # Procurement / logistics
    "vendor_name":           ("Vendor", "Module PO vendor(s) in SAP", "Waaree Energies"),
    "po_numbers":            ("PO number(s)", "Module PO(s) in SAP", "4500123456"),
    "po_date":               ("PO date", "Document date of the PO in SAP", "14-Oct-26"),
    "po_quantity_mwp":       ("PO quantity (MWp)", "The PO's module quantity", "120.5"),
    "awaiting_grn_mwp":      ("Dispatched, no GRN (MWp)", "Ariba: dispatched with no goods receipt", "35.0"),
    "oldest_awaiting_days":  ("Oldest dispatch without GRN (days)", "Ariba", "41"),
    "checklist_pending":     ("Receipts without finance checklist", "Ariba GRNs with no checklist raised", "3"),
    # Approval (Ordering Schedule -> Request approval; decided in Akasha)
    "order_month":           ("Order month", "The Ordering Schedule month the approval is for", "Jan-27"),
    "requested_by":          ("Requested by", "Who raised the approval request", "Ravi Kumar"),
    "request_note":          ("Requester's note", "What the requester wrote", "Vendor slot confirmed for January"),
    "approval_status":       ("Approval status", "Pending / Approved / Returned", "Pending"),
    "approval_decision":     ("Decision", "Approved or Returned", "Approved"),
    "approved_by":           ("Decided by", "Who approved or returned the request", "Suresh Patel"),
    "approval_date":         ("Decision date", "When it was decided (IST)", "16-Oct-26 11:20 IST"),
    "decision_note":         ("Decision remarks", "The approver's remarks", "Approved - place the PO this week"),
    "approval_next_step":    ("Next step", "What happens after the decision (a 'Required Action' line)", ""),
    # Project delay / AOP (P6 COD milestones)
    "aop_date":              ("AOP date", "Baseline finish of the COD milestone in P6 (the plan of record)", "31-Mar-27"),
    "forecast_cod_date":     ("Forecast COD (P6)", "Current finish of the COD milestone in P6 - a forecast", "30-Jun-27"),
    "cod_delay_days":        ("Days late against AOP", "Forecast COD (or today, if that forecast has passed) minus the AOP", "91"),
    "days_to_aop":           ("Days to AOP", "Days from today to the AOP", "28"),
    "progress_pct":          ("Progress (P6)", "Completed / total P6 activities, with the counts", "62% (812 of 1,310 activities completed)"),
    "activities_remaining":  ("Activities remaining", "P6 activities not completed", "498"),
    "forecast_note":         ("Forecast note", "What P6 forecasts, or that its forecast has gone stale", "P6 forecasts COD on 30-Jun-27"),
    # Schedule changes
    "change_source":         ("Changed by", "Where the change came from: a sync, or a person in Akasha", "Edited in Akasha by Ravi Kumar"),
    "change_remarks":        ("Reason given", "The reason the person gave (manual edits)", "Connectivity revised by CTUIL letter"),
    "change_impact":         ("Impact of the change", "Worked out from the plan and P6 for the date that moved (AOP: forecast COD vs AOP; LTA: FTCs after it; ...)",
                              "P6 forecast COD 30-Jun-27 is 35 days after the new AOP (it was 140 days after the old AOP)"),
    "order_value":           ("Order value", "From the SAP PO once placed - never estimated", ""),
    # System
    "source_name":           ("Data source", "Sync feed", "Primavera P6"),
    "sync_error":            ("Error", "Last sync failure message", "Login failed"),
    "last_success":          ("Last successful sync", "sync log", "14-Oct-26 06:10 IST"),
    "digest_table":          ("Digest table", "This week's items for the recipient's portfolios (built by Akasha)", ""),
    "digest_period":         ("Digest period", "Week covered", "13-Oct-26 to 19-Oct-26"),
    "p6_as_of":              ("P6 data as of", "Last successful P6 sync", "15-Oct-26 06:00 IST"),
    "sap_as_of":             ("SAP data as of", "Data date of the last SAP extract", "15-Oct-26"),
    "generated_at":          ("Generated", "When Akasha produced this email (IST)", "15-Oct-26 09:00 IST"),
    "akasha_project_link":   ("View in Akasha", "Link to the project in Akasha (AKASHA_PUBLIC_URL)", "https://host/akasha/project/FY26-P05"),
    "akasha_link":           ("Open Akasha", "Link to Akasha", "https://host/akasha"),
    "akasha_approval_link":  ("Review and approve", "The approval in Akasha", "https://host/akasha/alerts/12"),
}
HTML_VARIABLES = {"digest_table"}

# ── Triggers ─────────────────────────────────────────────────────────────────
TRIGGERS = {
    "ordering_due":     "Days before a phase's ordering date for each level (config: levels {level: days}); each phase gets the nearest one it has reached",
    "ordering_today":   "On the ordering date, with balance still to order",
    "ordering_overdue": "Ordering date passed, balance still to order; L1 / L2 / L3 by days overdue (config: escalation)",
    "date_change":      "A watched P6 / connectivity date changed since the last check (config: fields)",
    "ftc_unreachable":  "An order can no longer reach the phase's P6 FTC",
    "vendor_shift":     "Vendor allocation moved an order out of its target month",
    "awaiting_grn":     "Dispatched in Ariba with no GRN for longer than config.min_days (repeats every remind_every_days)",
    "checklist_missing": "Goods received with no finance checklist raised",
    "site_stock_low":   "Modules on site at or below config.min_stock_mwp while erection is still to do",
    "po_detected":      "A new module PO appears in SAP for the project",
    "sync_failed":      "A data feed failed, or has had no success for config.stale_hours",
    "project_delay":    "COD later than the AOP; L1 / L2 / L3 at the days late in config levels",
    "aop_due":          "AOP approaching with COD not achieved; L1 / L2 / L3 at the days before in config levels",
    "weekly_digest":    "Once a week (config.weekday, 0 = Monday) - one summary per group",
    "manual":           "Sent from the admin screen for a chosen project (no automatic trigger yet)",
}

LEVELS = [  # overdue reminders: each step emails again and adds these groups
    {"after_days": 0, "label": "Overdue", "add_to": [], "add_cc": []},
    {"after_days": 7, "label": "7 days overdue", "add_to": ["tc_head"], "add_cc": ["pmag"]},
    {"after_days": 14, "label": "14 days overdue", "add_to": [], "add_cc": ["executive"]},
]

# Level of intimation each template goes out at, and whether its To
# recipients must acknowledge it. Module ordering climbs one level per
# reminder: 30 days before the ordering date L1, 15 days L2, 7 days L3.
# An administrator changes both per template; these are the defaults (and
# fill templates saved before the columns existed).
LEVEL_DEFAULT = {"ordering_due_today": 3}
ACK_DEFAULT = {"ordering_due_30", "ordering_due_today", "ordering_overdue",
               "date_change", "ftc_unreachable", "vendor_shift", "awaiting_grn", "site_stock_low",
               "approval_request", "sync_failed", "project_delay", "aop_due"}

# How an alert closes: "order" when the phase has nothing left to order in
# the Ordering Schedule (the PO is in SAP); "condition" when its trigger no
# longer finds it; "one_off" (a date change, a moved order, a manual
# request) when a To recipient acknowledges it.
CASE_KIND = {"ordering_due": "order", "ordering_today": "order", "ordering_overdue": "order",
             "ftc_unreachable": "condition", "awaiting_grn": "condition", "site_stock_low": "condition",
             "sync_failed": "condition", "project_delay": "condition", "aop_due": "condition"}

# ── Starting templates ───────────────────────────────────────────────────────
def _t(key, name, category, trigger, severity, to, cc, subject, body, description, config=None, attach=False):
    return {"key": key, "name": name, "category": category, "trigger": trigger, "severity": severity,
            "to_groups": to, "cc_groups": cc, "subject": subject, "body": body.strip("\n"),
            "description": description, "config": config or {}, "attach_snapshot": attach,
            "level": LEVEL_DEFAULT.get(key, 1), "ack_required": key in ACK_DEFAULT}


TEMPLATES = [
    _t("ordering_due_30", "Module ordering - due", "Reminder", "ordering_due", "action",
       ["tc_ordering"], ["projects", "pmag"],
       "Akasha Reminder | Module Ordering Due in {{days_to_ordering}} Days | {{project_name}} {{phase}}",
       """
Dear Team,

Akasha has identified an upcoming module order for **{{project_name}}** ({{phase}}). Ordering on time keeps site delivery and the FTC on plan.

Quantity to Order: {{module_quantity_mwp}} MWp
Ordering Date: {{module_ordering_date}}
Modules Needed at Site: {{tc_delivery_date}}
FTC Date (P6): {{ftc_date}}
LTA Date: {{lta_date}}
Balance to Order: {{balance_ordering_mwp}} MWp
Module Origin: {{vendor_type}}

Required Action: Validate the requirement and start the ordering process (PR / vendor slot).

View in Akasha: {{akasha_project_link}}
""", "L1 30, L2 15 and L3 7 days before the phase's ordering date", {"levels": {"1": 30, "2": 15, "3": 7}}, attach=True),

    _t("ordering_due_today", "Module ordering - due today", "Reminder", "ordering_today", "action",
       ["tc_ordering"], ["projects"],
       "Akasha Action Alert | Module Ordering Due Today | {{project_name}} {{phase}}",
       """
Dear Team,

Today is the last planned date to order modules for **{{project_name}}** ({{phase}}). Akasha has not yet seen a PO for this quantity in SAP.

Quantity to Order: {{module_quantity_mwp}} MWp
Ordering Date: {{module_ordering_date}}
Modules Needed at Site: {{tc_delivery_date}}
FTC Date (P6): {{ftc_date}}
Ordering Status: {{ordering_status}}

Required Action: Place the order today, or record the reason for the delay.

View in Akasha: {{akasha_project_link}}
""", "On the ordering date, while no PO covers the quantity"),

    _t("date_change", "Schedule date changed", "Alert", "date_change", "action",
       ["projects", "pmag"], ["executive", "tc_ordering"],
       "Akasha Schedule Alert | {{changed_date_field}} Revised | {{project_name}}",
       """
Dear Team,

Akasha has detected a change in the **{{changed_date_field}}** for **{{project_name}}**. The revised date may change the module ordering window, site delivery or FTC feasibility.

Date Changed: {{changed_date_field}}
Previous Date: {{previous_date}}
Revised Date: {{revised_date}}
Variance: {{date_variance_days}} days
Changed By: {{change_source}}
Reason Given: {{change_remarks}}
Ordering Date (recalculated): {{module_ordering_date}}
Modules Needed at Site (recalculated): {{tc_delivery_date}}
FTC Date (P6): {{ftc_date}}
Impact: {{change_impact}}
Ordering Impact: {{risk_reason}}

Required Action: Projects and TC teams to validate the revised date and update the ordering plan if required.

Review in Akasha: {{akasha_project_link}}
""", "When FTC, LTA, SCOD, AOP or the ordering date changes - after a sync, or an edit in Akasha (with the reason)",
       {"fields": ["ftc_date", "lta", "scod", "aop_plan", "module_date"]}),

    _t("ordering_overdue", "Module ordering - overdue (escalating)", "Alert", "ordering_overdue", "critical",
       ["tc_ordering", "projects"], ["pmag"],
       "Akasha Critical Alert | Module Ordering Overdue {{days_overdue}} Days | {{project_name}} {{phase}}",
       """
Dear Team,

The planned ordering date for **{{project_name}}** ({{phase}}) has passed and the quantity is still unordered. The Ordering Schedule now places it in {{revised_ordering_month}}, the earliest open month.

Escalation: {{escalation_level}}
Overdue Quantity: {{module_quantity_mwp}} MWp
Original Ordering Date: {{module_ordering_date}}
Days Overdue: {{days_overdue}}
Ordering Month in the Plan: {{revised_ordering_month}}
Expected Site Delivery (calculated): {{forecast_tc_date}}
FTC Date (P6): {{ftc_date}}
Forecast FTC (calculated): {{forecast_ftc_date}}
FTC Shortfall: {{ftc_shortfall_days}} days
Risk: {{risk_reason}}

Required Action: TC and Projects to confirm the recovery plan - order date, vendor slot, and whether the FTC must be re-baselined.

Review in Akasha: {{akasha_project_link}}
""", "The ordering date has passed with balance still to order. Repeats at each escalation step.",
       {"escalation": LEVELS}, attach=True),

    _t("approval_request", "Module ordering - approval request", "Approval", "manual", "action",
       ["tc_head"], ["tc_ordering", "projects", "pmag"],
       "Akasha Approval Required | Module Ordering {{order_month}} | {{project_name}} {{phase}}",
       """
Dear Sir/Ma'am,

{{requested_by}} requests approval to order **{{module_quantity_mwp}} MWp** of modules for **{{project_name}}** ({{phase}}) in **{{order_month}}**. Once approved, this quantity is frozen in {{order_month}} in the Ordering Schedule until its PO is in SAP.

Quantity to Approve: {{module_quantity_mwp}} MWp
Order Month: {{order_month}}
Phase: {{phase}}
Ordering Date (planned): {{module_ordering_date}}
Modules Needed at Site: {{tc_delivery_date}}
FTC Date (P6): {{ftc_date}}
LTA Date: {{lta_date}}
Module Origin: {{vendor_type}}
Ordered Till Now: {{ordered_mwp}} MWp
Balance to Order: {{balance_ordering_mwp}} MWp
Schedule Risk: {{risk_reason}}
Requested By: {{requested_by}}
Requester's Note: {{request_note}}

Required Action: Approve, or return the request with remarks, in Akasha.

Project in Akasha: {{akasha_project_link}}
""", "Sent when someone requests approval for a month's order from the Ordering Schedule", attach=True),

    _t("approval_decision", "Module ordering - approval decision", "Approval", "manual", "info",
       ["tc_ordering"], ["projects", "pmag"],
       "Akasha Approval {{approval_decision}} | Module Ordering {{order_month}} | {{project_name}} {{phase}}",
       """
Dear Team,

The request to order **{{module_quantity_mwp}} MWp** of modules for **{{project_name}}** ({{phase}}) in **{{order_month}}** has been **{{approval_decision}}** by {{approved_by}}.

Decision: {{approval_decision}}
Decided By: {{approved_by}}
Decision Date: {{approval_date}}
Remarks: {{decision_note}}
Quantity: {{module_quantity_mwp}} MWp
Order Month: {{order_month}}
Ordering Date (planned): {{module_ordering_date}}
FTC Date (P6): {{ftc_date}}
Requested By: {{requested_by}}

{{approval_next_step}}

View in Akasha: {{akasha_project_link}}
""", "Sent when an approval request is approved or returned; the requester is always on To"),

    _t("order_completed", "Module order completed", "Approval", "manual", "info",
       ["projects", "pmag"], ["tc_ordering", "tc_stores", "executive"],
       "Akasha Confirmation | Module Order Completed | {{project_name}} {{phase}}",
       """
Dear Team,

Module ordering for **{{project_name}}** ({{phase}}) is complete. Projects, PMAG and TC Stores can now track dispatch, transit and site receipt against this order.

Ordered Quantity: {{po_quantity_mwp}} MWp
PO Number(s): {{po_numbers}}
Vendor: {{vendor_name}}
PO Date: {{po_date}}
Modules Needed at Site: {{tc_delivery_date}}
FTC Date (P6): {{ftc_date}}
Approved By: {{approved_by}}
Approval Date: {{approval_date}}

Track in Akasha: {{akasha_project_link}}
""", "Sent from the admin screen once approved; the automatic version is 'New module PO in SAP'"),

    _t("weekly_digest", "Weekly ordering digest", "Digest", "weekly_digest", "info",
       ["tc_ordering", "projects", "pmag"], [],
       "Akasha Weekly Digest | Module Ordering | {{digest_period}}",
       """
Dear Team,

Your module ordering summary for {{digest_period}} - everything due, overdue or at risk in your portfolios, in one place.

{{digest_table}}

Open Akasha: {{akasha_link}}
""", "Every Monday, one email per group with its portfolios' items", {"weekday": 0}),

    _t("ftc_unreachable", "FTC no longer reachable", "Alert", "ftc_unreachable", "critical",
       ["projects", "tc_ordering"], ["pmag", "executive"],
       "Akasha Critical Alert | FTC Not Achievable From Current Ordering | {{project_name}} {{phase}}",
       """
Dear Team,

With the order now planned for {{revised_ordering_month}}, modules for **{{project_name}}** ({{phase}}) cannot reach site in time for the P6 FTC.

FTC Date (P6): {{ftc_date}}
Forecast FTC (calculated): {{forecast_ftc_date}}
FTC Shortfall: {{ftc_shortfall_days}} days
Quantity Affected: {{module_quantity_mwp}} MWp
Ordering Month in the Plan: {{revised_ordering_month}}
LTA Date: {{lta_date}}

Required Action: Decide between expediting (vendor / logistics) and re-baselining the FTC, and record it in P6.

Review in Akasha: {{akasha_project_link}}
""", "The Ordering Schedule finds an order that cannot reach its phase's P6 FTC"),

    _t("vendor_shift", "Order moved by vendor allocation", "Alert", "vendor_shift", "action",
       ["tc_ordering"], ["projects"],
       "Akasha Alert | Order Moved by Vendor Allocation | {{project_name}} {{phase}}",
       """
Dear Team,

The {{vendor_type}} vendor allocation is full in the target month, so part of the order for **{{project_name}}** ({{phase}}) has been moved to {{revised_ordering_month}}.

Why It Moved: {{shift_reason}}
Quantity Moved: {{module_quantity_mwp}} MWp
Planned Ordering Date: {{module_ordering_date}}
Ordering Month in the Plan: {{revised_ordering_month}}
FTC Date (P6): {{ftc_date}}
Risk: {{risk_reason}}

Required Action: Confirm the moved month with the vendor, or change the project priority if this order must keep its month.

Review in Akasha: {{akasha_project_link}}
""", "Vendor monthly allocation moved an order out of its target month"),

    _t("awaiting_grn", "Dispatched but not received (GRN pending)", "Alert", "awaiting_grn", "action",
       ["tc_stores"], ["projects"],
       "Akasha Alert | Modules Dispatched, GRN Pending {{oldest_awaiting_days}} Days | {{project_name}}",
       """
Dear Team,

Ariba shows modules dispatched for **{{project_name}}** with no goods receipt posted.

Dispatched, No GRN: {{awaiting_grn_mwp}} MWp
Oldest Dispatch Without GRN: {{oldest_awaiting_days}} days
Vendor: {{vendor_name}}
PO Number(s): {{po_numbers}}

Required Action: Confirm whether the material has reached site and post the GRN, or follow up with the transporter.

Review in Akasha: {{akasha_project_link}}
""", "Dispatched in Ariba with no GRN for more than 30 days; reminds weekly",
       {"min_days": 30, "remind_every_days": 7}),

    _t("checklist_missing", "Finance checklist not raised", "Alert", "checklist_missing", "info",
       ["finance"], ["tc_stores"],
       "Akasha Alert | Finance Checklist Pending for {{checklist_pending}} Receipt(s) | {{project_name}}",
       """
Dear Team,

Goods have been received for **{{project_name}}** but no finance checklist has been raised for {{checklist_pending}} receipt(s). The checklist is the handover for PO payment release.

Receipts Without Checklist: {{checklist_pending}}
Vendor: {{vendor_name}}
PO Number(s): {{po_numbers}}

Required Action: Raise the pending finance checklist(s) in Ariba.

Review in Akasha: {{akasha_project_link}}
""", "Goods received in Ariba with no finance checklist"),

    _t("site_stock_low", "Site module stock low", "Alert", "site_stock_low", "action",
       ["projects"], ["tc_stores", "tc_ordering"],
       "Akasha Alert | Site Module Stock Low | {{project_name}}",
       """
Dear Team,

Module stock at **{{project_name}}** is down to {{on_site_stock_mwp}} MWp while erection is still in progress.

Modules on Site: {{on_site_stock_mwp}} MWp
In Transit: {{in_transit_mwp}} MWp
Erected: {{erected_mwp}} MWp ({{erection_pct}})
Construction Progress: {{construction_progress}}
Balance to Order: {{balance_ordering_mwp}} MWp

Required Action: Check the next dispatch against the erection plan so the site does not stop for modules.

Review in Akasha: {{akasha_project_link}}
""", "Modules on site at or below the threshold while erection is still to do", {"min_stock_mwp": 5}, attach=True),

    _t("po_detected", "New module PO in SAP", "Approval", "po_detected", "info",
       ["projects", "pmag"], ["tc_ordering", "tc_stores"],
       "Akasha Update | Module PO Placed | {{project_name}}",
       """
Dear Team,

Akasha has found a new module PO in SAP for **{{project_name}}**. Dispatch, transit and site receipt will now be tracked against it.

PO Number: {{po_numbers}}
Vendor: {{vendor_name}}
PO Date: {{po_date}}
PO Quantity: {{po_quantity_mwp}} MWp
Ordered Till Now: {{ordered_mwp}} MWp
Balance to Order: {{balance_ordering_mwp}} MWp
FTC Date (P6): {{ftc_date}}

Track in Akasha: {{akasha_project_link}}
""", "A module PO for the project appears in SAP for the first time"),

    _t("project_delay", "Project delayed against AOP", "Alert", "project_delay", "critical",
       ["projects", "pmag"], ["executive", "tc_ordering"],
       "Akasha Critical Alert | Project {{cod_delay_days}} Days Behind AOP | {{project_name}}",
       """
Dear Team,

**{{project_name}}** is running **{{cod_delay_days}} days behind its AOP**. {{forecast_note}}.

AOP (P6 baseline COD): {{aop_date}}
Forecast COD (P6): {{forecast_cod_date}}
Days Late Against AOP: {{cod_delay_days}}
Progress (P6): {{progress_pct}}
Activities Remaining: {{activities_remaining}}
Construction Progress: {{construction_progress}}
Erected: {{erected_mwp}} MWp ({{erection_pct}})
Modules on Site: {{on_site_stock_mwp}} MWp
Balance to Order: {{balance_ordering_mwp}} MWp
LTA Date: {{lta_date}}
SCOD: {{scod_date}}

Required Action: Projects to confirm the recovery plan and the revised COD in P6; PMAG to review it against the AOP and the LTA.

View in Akasha: {{akasha_project_link}}
""", "COD later than the AOP: L1 at 15, L2 at 30, L3 at 60 days late", {"levels": {"1": 15, "2": 30, "3": 60}}, attach=True),

    _t("aop_due", "AOP approaching - COD not achieved", "Alert", "aop_due", "action",
       ["projects", "pmag"], ["executive"],
       "Akasha Alert | AOP in {{days_to_aop}} Days, COD Not Achieved | {{project_name}}",
       """
Dear Team,

The AOP for **{{project_name}}** is **{{days_to_aop}} days away** and COD is not yet achieved. {{forecast_note}}.

AOP (P6 baseline COD): {{aop_date}}
Days to AOP: {{days_to_aop}}
Forecast COD (P6): {{forecast_cod_date}}
Progress (P6): {{progress_pct}}
Activities Remaining: {{activities_remaining}}
Construction Progress: {{construction_progress}}
Erected: {{erected_mwp}} MWp ({{erection_pct}})
Modules on Site: {{on_site_stock_mwp}} MWp
Balance to Order: {{balance_ordering_mwp}} MWp

Required Action: Projects to confirm the AOP can still be met, or raise the risk with PMAG now with a recovery plan.

View in Akasha: {{akasha_project_link}}
""", "AOP near with COD not achieved: L1 at 60, L2 at 30, L3 at 15 days before", {"levels": {"1": 60, "2": 30, "3": 15}}, attach=True),

    _t("sync_failed", "Data sync failed", "System", "sync_failed", "critical",
       ["admin"], [],
       "Akasha System Alert | {{source_name}} Sync Failed",
       """
Dear Team,

The {{source_name}} sync has failed or has not succeeded for a while. Dashboards and alerts are using older data until it recovers.

Data Source: {{source_name}}
Error: {{sync_error}}
Last Successful Sync: {{last_success}}

Required Action: Check the integration in the Akasha admin console and re-run the sync.

Open Akasha: {{akasha_link}}
""", "A feed failed, or had no successful run for 26 hours", {"stale_hours": 26}),
]
