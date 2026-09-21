"""
Module Planning Intelligence Engine
───────────────────────────────────
Autonomous, deterministic, constraint-satisfaction supply chain planning
for solar module deliveries. Calculates backward-scheduled delivery dates
from P6 FTC milestones, respects source procurement quotas, levels peaks,
supports interactive Scenario Versions and Priority Overrides, and
synthesizes 360-degree multi-perspective AI operational recommendations.
"""
from datetime import datetime, timedelta
import re
from typing import Dict, List, Any, Optional

CAP_LIMITS: Dict[str, float] = {
    'China': 750.0,
    'SEA': 500.0,
    'ALMM': 500.0,
    'ALCM': 100.0,
    'DCR': 100.0,
}
DEFAULT_CAP = 500.0

LEAD_TIMES: Dict[str, int] = {
    'China': 136,
    'SEA': 136,
    'ALMM': 98,
    'ALCM': 98,
    'DCR': 98,
}
DEFAULT_LEAD_TIME = 98
TC_OFFSET_DAYS = 45

PRIORITY_RANKS: Dict[str, int] = {
    'P1': 1,
    'P2': 2,
    'standard': 3,
}


def get_forecast_months(count: int = 13, now: Optional[datetime] = None) -> List[str]:
    """Rolling forecast months starting from the current month (matches frontend export.ts)."""
    if now is None:
        now = datetime.now()
    months = []
    for i in range(count):
        y = now.year + (now.month - 1 + i) // 12
        m = (now.month - 1 + i) % 12 + 1
        d = datetime(y, m, 1)
        months.append(d.strftime("%b-%y"))
    return months


def _parse_date_str(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    m = re.search(r'(\d{1,2})-([A-Za-z]{3})-(\d{2,4})', date_str)
    if not m:
        return None
    day = int(m.group(1))
    mon_name = m.group(2).capitalize()
    yr_raw = int(m.group(3))
    year = 2000 + yr_raw if yr_raw < 100 else yr_raw
    months_abbr = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    if mon_name not in months_abbr:
        return None
    month = months_abbr.index(mon_name) + 1
    try:
        return datetime(year, month, day)
    except ValueError:
        return None


def _calc_month_idx(dt: datetime, base_dt: datetime, max_months: int = 13) -> int:
    """Calculates 0-indexed month offset from base_dt. Returns negative if dt is in past."""
    diff = (dt.year - base_dt.year) * 12 + (dt.month - base_dt.month)
    return diff


def run_module_planning_engine(
    projects: List[Dict[str, Any]], 
    now: Optional[datetime] = None,
    scenario_version: str = 'baseline',
    priority_overrides: Optional[Dict[int, str]] = None
) -> Dict[str, Any]:
    """
    Executes the full planning intelligence engine across all projects.
    Mutates projects in-place by adding `month_mwp`, `priority`, `perspectives`, `remarks`, and `planning_flags`.
    Returns portfolio-level capacity summary and AI strategic briefing.
    """
    if now is None:
        now = datetime.now()
    base_month_dt = datetime(now.year, now.month, 1)
    forecast_months = get_forecast_months(13, now)
    num_months = len(forecast_months)
    priority_overrides = priority_overrides or {}

    # 1. Parse demands per project
    demands = []
    project_phases_map: Dict[int, List[Dict[str, Any]]] = {}
    # A phase whose own module date has already passed is no longer part of
    # the forward plan (user decision 2026-09-21): if we've crossed it,
    # there's no need for that phase's capacity in the leveling/quota system
    # any more — ordering it now can't meet ITS FTC via the lead-time math
    # that produced this date in the first place, so it becomes an immediate
    # exception outside the monthly plan, not a demand competing for a future
    # month's quota. Tracked here instead of silently dropped.
    project_excluded_phases: Dict[int, List[Dict[str, Any]]] = {}
    project_total_demand: Dict[int, float] = {}
    for p in projects:
        pid = p['id']
        bal = float(p.get('balance_ordering_mwp') or 0.0)
        source = p.get('type') or 'ALMM'
        lead_time = LEAD_TIMES.get(source, DEFAULT_LEAD_TIME)
        
        # Determine Priority for project based on scenario and overrides
        if pid in priority_overrides:
            proj_priority = priority_overrides[pid]
        elif scenario_version == 'ppa_safeguard':
            is_ppa = (p.get('category') == 'PPA') or ('PPA' in (p.get('project_name') or '').upper())
            proj_priority = 'P1' if is_ppa else 'standard'
        else:
            proj_priority = 'standard'
            
        p['priority'] = proj_priority
        p['month_mwp'] = {mo: 0.0 for mo in forecast_months}
        p['planning_flags'] = []
        p['perspectives'] = {}
        # MWp needing an immediate exception order, outside this plan, because
        # its module date already passed — set for real in part 3 once phases
        # are resolved; defaulted here so the frontend never has to special-case
        # a missing field to know "does this project need one" (user decision
        # 2026-09-21: the notification banner should read this instead of
        # re-deriving its own overdue check from the date string).
        p['excluded_module_date_mwp'] = 0.0
        
        if bal <= 0:
            if p.get('is_commissioned') or p.get('ftc_all_charged'):
                p['remarks'] = "All FTC phases commissioned. Project active on grid; no module delivery required."
                p['ai_suggestion'] = "Project operational. Monitor baseline generation against design targets."
                p['perspectives'] = {
                    'commercial': 'COD completed. PPA revenue active with zero LD penalty exposure.',
                    'supply_chain': 'All factory orders fulfilled and closed out.',
                    'site_execution': 'Site construction finished. Operations & Maintenance phase.',
                    'grid_transmission': 'Substation and transmission bay fully charged and energized.'
                }
            else:
                ord_mw = float(p.get('ordered_mwp') or 0.0)
                p['remarks'] = f"100% capacity ordered ({ord_mw:.1f} MWp PO placed). No balance left to order."
                p['ai_suggestion'] = "Ensure supplier factory slots and shipping schedules align with site erection milestones."
                p['perspectives'] = {
                    'commercial': 'PO committed. Focus on vendor on-time delivery to preserve SCOD.',
                    'supply_chain': 'Factory allocation locked. Track dispatch clearance certificates.',
                    'site_execution': 'Laydown yard readiness required for incoming deliveries.',
                    'grid_transmission': 'Grid bay synchronization on schedule.'
                }
            continue

        # Every FTC phase is already charged, but SAP's PO/delivered figures
        # still show a balance — a real project can't need MORE modules
        # ordered after it's already energized, so this is a data gap (SAP PO
        # records short of what's physically installed), not a forward
        # ordering need. Falling through to the SCOD/AOP/LTA fallback below
        # invented a full-balance "Project Balance" demand for capacity that
        # is not required in the planning (user decision 2026-09-21) — it
        # can't be scheduled against a future FTC that already happened.
        if p.get('ftc_all_charged'):
            p['remarks'] = (f"All FTC phases already charged, but SAP shows {bal:.1f} MWp of capacity still "
                             f"unordered/undelivered — a PO/delivery record gap, not a future ordering need.")
            p['ai_suggestion'] = "Reconcile SAP PO and delivery records against the as-built module count; this is not a procurement action."
            p['perspectives'] = {
                'commercial': 'COD milestone met. This gap is a records issue, not a revenue or schedule risk.',
                'supply_chain': 'Verify the missing PO/GRN entries in SAP rather than raising a new order.',
                'site_execution': 'Modules are physically on site (FTC charged); no further delivery required.',
                'grid_transmission': 'Substation and transmission bay already energized.'
            }
            continue

        # DB field 'module_date' actually stores TC ordering dates (earliest)
        # DB field 'tc_date' actually stores Module delivery dates (later)
        # Chronology: TC ordering -> Lead Time -> Module delivery -> 45 Days -> FTC
        tc_str = p.get('module_date') or ''
        ftc_str = p.get('ftc_date') or ''
        phases = []
        
        if tc_str:
            chunks = [c.strip() for c in tc_str.split('·')]
            for c in chunks:
                m_dt = _parse_date_str(c)
                if not m_dt:
                    continue
                m_mw = re.search(r'\((\d+(?:\.\d+)?)\s*MW\)', c, re.IGNORECASE)
                mw_ac = float(m_mw.group(1)) if m_mw else 0.0
                
                m_ph = re.search(r'^(Ph-[^\s:]+|Phase[^\s:]+)', c, re.IGNORECASE)
                ph_label = m_ph.group(1) if m_ph else (f"Phase {len(phases)+1}" if len(chunks) > 1 else "Main")
                
                tc_ordering_dt = m_dt
                mod_delivery_dt = tc_ordering_dt + timedelta(days=lead_time)
                ftc_dt = mod_delivery_dt + timedelta(days=TC_OFFSET_DAYS)
                phases.append({
                    'phase_label': ph_label,
                    'ftc_dt': ftc_dt,
                    'tc_dt': tc_ordering_dt,
                    'mod_dt': mod_delivery_dt,
                    'mw_ac': mw_ac,
                })
        elif ftc_str:
            chunks = [c.strip() for c in ftc_str.split('·')]
            for c in chunks:
                m_dt = _parse_date_str(c)
                if not m_dt:
                    continue
                m_mw = re.search(r'\((\d+(?:\.\d+)?)\s*MW\)', c, re.IGNORECASE)
                mw_ac = float(m_mw.group(1)) if m_mw else 0.0
                
                m_ph = re.search(r'^(Ph-[^\s:]+|Phase[^\s:]+)', c, re.IGNORECASE)
                ph_label = m_ph.group(1) if m_ph else (f"Phase {len(phases)+1}" if len(chunks) > 1 else "Main")
                
                mod_delivery_dt = m_dt - timedelta(days=TC_OFFSET_DAYS)
                tc_ordering_dt = mod_delivery_dt - timedelta(days=lead_time)
                phases.append({
                    'phase_label': ph_label,
                    'ftc_dt': m_dt,
                    'tc_dt': tc_ordering_dt,
                    'mod_dt': mod_delivery_dt,
                    'mw_ac': mw_ac,
                })

        # Fallback to SCOD or AOP or current date + lead time if no FTC phases
        if not phases:
            ref_dt = None
            for dt_key in ('scod', 'aop_plan', 'lta'):
                parsed = _parse_date_str(p.get(dt_key))
                if parsed:
                    ref_dt = parsed
                    break
            if not ref_dt:
                ref_dt = base_month_dt + timedelta(days=TC_OFFSET_DAYS + lead_time + 30)

            tc_dt = ref_dt - timedelta(days=TC_OFFSET_DAYS)
            mod_dt = tc_dt - timedelta(days=lead_time)
            phases.append({
                'phase_label': 'Project Balance',
                'ftc_dt': ref_dt,
                'tc_dt': tc_dt,
                'mod_dt': mod_dt,
                'mw_ac': float(p.get('capacity_mwac') or 0.0),
            })

        ol = float(p.get('ol') or 0.0)
        if ol <= 0:
            ol = (float(p.get('capacity_mwp') or 0.0) / float(p.get('capacity_mwac') or 1.0)) if float(p.get('capacity_mwac') or 0) > 0 else 1.35
        p['ol'] = ol

        for ph in phases:
            ph_mwac = ph['mw_ac']
            if ph_mwac <= 0:
                # If no MW specified in string, fallback to distributing the pending balance
                req_mwp = round(bal / len(phases), 1) if len(phases) > 0 else 0.0
            else:
                req_mwp = round(ph_mwac * ol, 1)
                
            raw_idx = _calc_month_idx(ph['tc_dt'], base_month_dt, num_months)

            # If FTC date has already passed, this phase is completed — skip entirely
            if ph['ftc_dt'] < base_month_dt:
                continue

            if raw_idx < 0:
                project_excluded_phases.setdefault(p['id'], []).append({
                    'phase_label': ph['phase_label'],
                    'ftc_dt': ph['ftc_dt'],
                    'mod_dt': ph['tc_dt'],  # Ordering Date has passed
                    'mwp': req_mwp,
                })
                continue

            demands.append({
                'project_id': p['id'],
                'project': p,
                'source': source,
                'priority': proj_priority,
                'phase_label': ph['phase_label'],
                'ftc_dt': ph['ftc_dt'],
                'tc_dt': ph['tc_dt'],
                'mod_dt': ph['mod_dt'],
                'mwp': req_mwp,
                'raw_month_idx': raw_idx,
                'target_month_idx': max(0, min(num_months - 1, raw_idx)),
                'lead_time': lead_time,
                'ol': ol,
            })
            project_total_demand[p['id']] = project_total_demand.get(p['id'], 0.0) + req_mwp

    # 2. Multi-source Leveling & Optimization with Priority Weighing
    by_source: Dict[str, List[Dict[str, Any]]] = {}
    for d in demands:
        by_source.setdefault(d['source'], []).append(d)

    monthly_alloc_by_source: Dict[str, List[float]] = {
        s: [0.0] * num_months for s in CAP_LIMITS
    }
    monthly_alloc_mwp_by_source: Dict[str, List[float]] = {
        s: [0.0] * num_months for s in CAP_LIMITS
    }
    project_allocations: Dict[int, Dict[int, float]] = {}
    project_pulled_details: Dict[int, List[Dict[str, Any]]] = {}
    project_capacity_delayed_details: Dict[int, List[Dict[str, Any]]] = {}
    project_lta_extended_details: Dict[int, List[Dict[str, Any]]] = {}

    for source, s_demands in by_source.items():
        cap = CAP_LIMITS.get(source, DEFAULT_CAP)
        if source not in monthly_alloc_by_source:
            monthly_alloc_by_source[source] = [0.0] * num_months
            monthly_alloc_mwp_by_source[source] = [0.0] * num_months
            
        # Priority sort: P1 first, then P2, then Standard; then earliest FTC date, then earliest Module Date
        s_demands.sort(key=lambda x: (
            PRIORITY_RANKS.get(x['priority'], 3),
            x['ftc_dt'],
            x['mod_dt'],
            x['project_id']
        ))

        for d in s_demands:
            pid = d['project_id']
            project_allocations.setdefault(pid, {m_i: 0.0 for m_i in range(num_months)})
            rem = d['mwp']
            target_m = d['target_month_idx']

            # Try target month, pull earlier if capacity is exceeded
            curr_m = target_m
            ol = d.get('ol', 1.35)
            while rem > 1e-4 and curr_m >= 0:
                avail = max(0.0, cap - monthly_alloc_by_source[source][curr_m])
                avail_mwp = avail * ol
                if avail_mwp > 1e-4:
                    take_mwp = min(rem, avail_mwp)
                    take_mwac = take_mwp / ol
                    monthly_alloc_by_source[source][curr_m] += take_mwac
                    monthly_alloc_mwp_by_source[source][curr_m] += take_mwp
                    project_allocations[pid][curr_m] += take_mwp
                    rem -= take_mwp
                    if curr_m < target_m:
                        project_pulled_details.setdefault(pid, []).append({
                            'pulled_from': forecast_months[target_m],
                            'pulled_to': forecast_months[curr_m],
                            'mwp': take_mwp,
                            'reason': f"{source} {cap:.0f} MW/mo quota in {forecast_months[target_m]}",
                        })
                curr_m -= 1

            # Every earlier month is already at quota, and pulling further
            # back isn't possible (month 0 is "now"). To strictly enforce the 
            # vendor quota, we MUST push the demand into future months.
            # If the future month is still before the LTA deadline, it's a safe extension.
            # If it's pushed past the LTA deadline, it's a critical capacity delay.
            if rem > 1e-4:
                lta_dt_str = d['project'].get('lta')
                lta_parsed = _parse_date_str(lta_dt_str)
                lta_m = target_m
                
                if lta_parsed:
                    lta_mod_dt = lta_parsed - timedelta(days=TC_OFFSET_DAYS + lead_time)
                    lta_calc = _calc_month_idx(lta_mod_dt, base_month_dt, num_months)
                    lta_m = max(target_m, lta_calc)
                    
                curr_m = target_m + 1
                while rem > 1e-4 and curr_m < num_months:
                    avail = max(0.0, cap - monthly_alloc_by_source[source][curr_m])
                    avail_mwp = avail * ol
                    if avail_mwp > 1e-4:
                        take_mwp = min(rem, avail_mwp)
                        take_mwac = take_mwp / ol
                        monthly_alloc_by_source[source][curr_m] += take_mwac
                        monthly_alloc_mwp_by_source[source][curr_m] += take_mwp
                        project_allocations[pid][curr_m] += take_mwp
                        rem -= take_mwp
                        
                        if curr_m <= lta_m:
                            project_lta_extended_details.setdefault(pid, []).append({
                                'pushed_from': forecast_months[target_m],
                                'pushed_to': forecast_months[curr_m],
                                'mwp': take_mwp,
                            })
                            if 'extended_to_lta' not in d['project']['planning_flags']:
                                d['project']['planning_flags'].append('extended_to_lta')
                        else:
                            project_capacity_delayed_details.setdefault(pid, []).append({
                                'pushed_from': forecast_months[target_m],
                                'pushed_to': forecast_months[curr_m],
                                'mwp': take_mwp,
                            })
                            if 'capacity_delayed' not in d['project']['planning_flags']:
                                d['project']['planning_flags'].append('capacity_delayed')
                    curr_m += 1

            # If there is STILL remainder after exhausting all 13 months,
            # we are forced to dump it in the last month (run out of columns).
            if rem > 1e-4:
                monthly_alloc_by_source[source][num_months - 1] += (rem / ol)
                monthly_alloc_mwp_by_source[source][num_months - 1] += rem
                project_allocations[pid][num_months - 1] += rem
                project_capacity_delayed_details.setdefault(pid, []).append({
                    'pushed_from': forecast_months[target_m],
                    'pushed_to': forecast_months[num_months - 1],
                    'mwp': rem,
                })
                if 'capacity_delayed' not in d['project']['planning_flags']:
                    d['project']['planning_flags'].append('capacity_delayed')
                rem = 0.0

    # 3. Format project results and synthesize 360° AI rationale
    for p in projects:
        pid = p['id']
        bal = float(p.get('balance_ordering_mwp') or 0.0)
        excluded_list = project_excluded_phases.get(pid, [])
        active_demand = project_total_demand.get(pid, 0.0)

        # bal<=0 and ftc_all_charged projects were finished in part 1
        # (remarks/perspectives already set, `continue`d before ever entering
        # `demands`). A project can ALSO have every one of its phases excluded
        # here for a different reason — each one's own module date already
        # passed (user decision 2026-09-21) — leaving active_demand at 0 while
        # bal is still positive. Without checking that too, the "fix rounding
        # discrepancies" step below saw month_mwp all-zero against a nonzero
        # bal and dumped the full balance back in, exactly like the
        # ftc_all_charged case did before it was fixed.
        if bal <= 0 or p.get('ftc_all_charged'):
            continue
        p['excluded_module_date_mwp'] = round(sum(x['mwp'] for x in excluded_list), 1)
        if active_demand <= 0 and excluded_list:
            total_excl = sum(x['mwp'] for x in excluded_list)
            phase_bits = "; ".join(
                f"{x['phase_label']} ({x['mwp']:.1f} MWp, module date {x['mod_dt'].strftime('%d-%b-%y')} — overdue)"
                for x in excluded_list
            )
            p['remarks'] = (f"Every pending phase's module date has already passed: {phase_bits}. "
                             f"These no longer fit the forward monthly plan — their ordering window is gone, "
                             f"so they're excluded from it rather than forced into a stale target month.")
            p['ai_suggestion'] = f"Place these {total_excl:.1f} MWp as an immediate exception order, outside the monthly leveling schedule — the original FTC date for these phases can no longer be met via the standard lead-time math."
            p['planning_flags'].append('module_date_passed')
            continue

        allocs = project_allocations.get(pid, {})
        for m_i, mo in enumerate(forecast_months):
            p['month_mwp'][mo] = round(allocs.get(m_i, 0.0), 1)

        # Fix minor rounding discrepancies — against active_demand (what was
        # actually queued for leveling), NOT the raw bal, which can now be
        # larger than what's planned when some of a project's phases were
        # excluded above but others are still active.
        row_sum = sum(p['month_mwp'].values())
        diff = round(active_demand - row_sum, 1)
        if abs(diff) > 0:
            best_mo = max(forecast_months, key=lambda mo: p['month_mwp'][mo])
            p['month_mwp'][best_mo] = round(p['month_mwp'][best_mo] + diff, 1)

        non_zero_months = [mo for mo in forecast_months if p['month_mwp'][mo] > 0]
        source = p.get('type') or 'ALMM'
        lead_time = LEAD_TIMES.get(source, DEFAULT_LEAD_TIME)
        cap = CAP_LIMITS.get(source, DEFAULT_CAP)

        pulled_list = project_pulled_details.get(pid, [])
        delayed_list = project_capacity_delayed_details.get(pid, [])
        lta_extended_list = project_lta_extended_details.get(pid, [])
        months_str = ", ".join(non_zero_months) if non_zero_months else "immediate"
        excl_note = ""
        if excluded_list:
            total_excl = sum(x['mwp'] for x in excluded_list)
            excl_note = (f" Separately, {total_excl:.1f} MWp across {len(excluded_list)} phase(s) already passed "
                         f"their own module date and is excluded from this plan as an immediate exception.")

        # Build Primary Diagnosis & Suggestion
        now_dt = datetime.now()
        if delayed_list:
            total_delayed = sum(x['mwp'] for x in delayed_list)
            delayed_months = ", ".join(sorted(list(set(x['pushed_to'] for x in delayed_list))))
            diag = (f"Scheduled into {months_str}: {total_delayed:.1f} MWp pushed to {delayed_months} because {source}'s {cap:.0f} MW/mo "
                    f"quota was exhausted. This delay exceeds the LTA transmission timeline.{excl_note}")
            sugg = (f"CRITICAL: Vendor capacity limit has caused a {total_delayed:.1f} MWp delay beyond the LTA date. "
                    f"Consider re-allocating quota from lower-priority projects, or sourcing from an alternative vendor.")
        elif lta_extended_list:
            total_extended = sum(x['mwp'] for x in lta_extended_list)
            extended_months = ", ".join(sorted(list(set(x['pushed_to'] for x in lta_extended_list))))
            diag = (f"Scheduled into {months_str}: {total_extended:.1f} MWp extended to {extended_months} due to vendor quota limits. "
                    f"The FTC target was relaxed to align with the later LTA transmission timeline.{excl_note}")
            sugg = (f"Vendor capacity constrained for the aggressive FTC date. Because transmission (LTA) is not ready until later, "
                    f"the delivery was successfully pushed to subsequent months without commercial risk.")
        elif pulled_list:
            pulled_info = pulled_list[0]
            diag = (f"Scheduled into {months_str}: {pulled_info['mwp']:.1f} MWp pulled early from "
                    f"{pulled_info['pulled_from']} into {pulled_info['pulled_to']} to respect {source} "
                    f"{cap:.0f} MW/mo supplier limit and protect FTC milestone.{excl_note}")
            sugg = (f"Ensure site laydown area in {pulled_info['pulled_to']} is ready to accept early delivery batch. "
                    f"Lock in supplier fabrication slot 30 days before intimation.")
            p['planning_flags'].append('leveled_early')
        else:
            first_mo = non_zero_months[0] if non_zero_months else forecast_months[0]
            target_phase = project_phases_map.get(pid, [{}])[0]
            ftc_dt = target_phase.get('ftc_dt')
            if ftc_dt:
                mod_dt = target_phase.get('mod_dt')
                diff_days = (mod_dt.date() - now_dt.date()).days if mod_dt else 0
                days_status = f"{abs(diff_days)} days overdue" if diff_days < 0 else f"{diff_days} days remaining"
                diag = (f"Allocated to {months_str} aligned with FTC {ftc_dt.strftime('%d-%b-%y')} "
                        f"(site target {mod_dt.strftime('%d-%b-%y')}, {days_status} | {lead_time}d {source} lead time + 45d TC). "
                        f"Demand fits comfortably within monthly {source} capacity.{excl_note}")
            else:
                diag = (f"Allocated to {months_str} aligned with FTC schedule (-45d TC, -{lead_time}d {source} lead time). "
                        f"Demand fits comfortably within monthly {source} capacity.{excl_note}")
            sugg = (f"Maintain planned procurement cycle. Issue formal PO intimation at least {lead_time} days prior to {first_mo}.")

        p['remarks'] = diag
        p['ai_suggestion'] = sugg

        # 360-Degree Operational Perspectives
        first_delivery_mo = non_zero_months[0] if non_zero_months else "immediate"
        peak_allocated = max([p['month_mwp'][mo] for mo in non_zero_months], default=bal)
        acreage_est = round(peak_allocated * 0.08, 1)  # ~2 acres per 25 MWp batch
        crane_est = max(1, round(peak_allocated / 50))

        is_ppa = (p.get('category') == 'PPA') or ('PPA' in (p.get('project_name') or '').upper())
        tariff_txt = "Standard PPA contract" if is_ppa else "Merchant pricing model"
        ld_exposure = "High LD risk on SCOD delay" if is_ppa else "Revenue deferral risk only"

        p['perspectives'] = {
            'commercial': f"{tariff_txt} with {ld_exposure}. Priority ranking '{p['priority']}' allocated {bal:.1f} MWp across {months_str} to shield commissioning cash flows.",
            'supply_chain': f"Consumes up to {peak_allocated:.1f} MWp ({round((peak_allocated/cap)*100)}% of monthly {source} factory quota). Lead time requires PO intimation {lead_time}d prior to {first_delivery_mo}.",
            'site_execution': f"Requires approx {acreage_est} acres of prepared laydown yard and {crane_est} unloading crane team(s) at Plot {p.get('plot') or 'Site'} during peak delivery month.",
            'grid_transmission': f"Synchronized with {p.get('connectivity_phase') or 'Transmission'} network. Modules arrive {lead_time}d before TC to ensure trial-run completion before FTC."
        }

    # 4. Generate Portfolio-Level Capacity Summary & Strategic Briefing
    # Iterating CAP_LIMITS alone silently dropped any project whose source
    # isn't one of the 5 known origins (e.g. a blank/'Unknown' type falls
    # through the `p.get('type') or 'ALMM'` default only when type is empty —
    # a literal 'Unknown' string survives as its own bucket in
    # monthly_alloc_by_source and would vanish from this summary without
    # ever showing up as a discrepancy). Iterate every source that actually
    # received an allocation instead, so nothing is silently excluded.
    capacity_summary = {}
    for s in monthly_alloc_by_source:
        cap = CAP_LIMITS.get(s, DEFAULT_CAP)
        alloc_list_mwac = monthly_alloc_by_source[s]
        alloc_list_mwp = monthly_alloc_mwp_by_source.get(s, [0.0] * num_months)
        if s not in CAP_LIMITS and not any(v > 0 for v in alloc_list_mwac):
            continue
        capacity_summary[s] = {
            'monthly_cap_mwp': cap, # Legacy key name to avoid frontend breakage
            'monthly_cap_mwac': cap,
            'lead_time_days': LEAD_TIMES.get(s, DEFAULT_LEAD_TIME),
            'allocated_by_month': [round(v, 1) for v in alloc_list_mwp],
            'allocated_by_month_mwac': [round(v, 1) for v in alloc_list_mwac],
            'utilization_pct_by_month': [round((v / cap) * 100, 1) if cap > 0 else 0 for v in alloc_list_mwac],
            'peak_month': forecast_months[alloc_list_mwac.index(max(alloc_list_mwac))] if max(alloc_list_mwac) > 0 else '-',
            'peak_mwp': round(max(alloc_list_mwp), 1) if max(alloc_list_mwp) > 0 else 0,
            'peak_mwac': round(max(alloc_list_mwac), 1),
        }

    # 'critical_ordering' no longer gets set anywhere — a phase whose module
    # date already passed is excluded from the plan now (part 1), not forced
    # into month 0 and flagged critical — so counting that flag here would
    # always read 0. 'module_date_passed' is the flag that now carries that
    # signal (set only when EVERY phase of a project was excluded; a partial
    # exclusion alongside active demand doesn't set it, so it's counted
    # separately via the phase-level totals below).
    excluded_projects_count = sum(1 for p in projects if 'module_date_passed' in p.get('planning_flags', []))
    leveled_count = sum(1 for p in projects if 'leveled_early' in p.get('planning_flags', []))
    extended_lta_count = sum(1 for p in projects if 'extended_to_lta' in p.get('planning_flags', []))
    delayed_count = sum(1 for p in projects if 'capacity_delayed' in p.get('planning_flags', []))
    p1_count = sum(1 for p in projects if p.get('priority') == 'P1')

    # Two distinct, non-overlapping reasons the raw balance can exceed what's
    # actually planned — reported separately so neither hides behind the
    # other's explanation:
    #   1. ftc_all_charged: already energized; SAP's gap there is a records
    #      issue (see part 1), not an ordering need.
    #   2. module date passed: that specific phase's ordering window is gone
    #      (user decision 2026-09-21) — tracked per-phase in
    #      project_excluded_phases regardless of whether the REST of that
    #      project still has active demand.
    total_planned = sum(sum(p.get('month_mwp', {}).values()) for p in projects)
    excluded_ftc_charged_mwp = round(sum(
        float(p.get('balance_ordering_mwp') or 0.0) for p in projects if p.get('ftc_all_charged')
    ), 1)
    excluded_module_passed_mwp = round(sum(
        x['mwp'] for phases in project_excluded_phases.values() for x in phases
    ), 1)

    takeaways = [
        f"Scenario '{scenario_version.replace('_', ' ').title()}': Planned {round(total_planned, 1):,} MWp across {len(forecast_months)} months.",
        f"{p1_count} projects prioritized with guaranteed first-claim allocation on manufacturing quotas.",
        f"{leveled_count} projects were proactively pulled earlier to avoid exceeding vendor monthly limits.",
    ]
    if extended_lta_count:
        takeaways.append(f"{extended_lta_count} projects were safely extended to their LTA dates, avoiding quota limits while respecting transmission timelines.")
    if delayed_count:
        takeaways.append(f"{delayed_count} projects were delayed past their LTA dates due to strict monthly vendor quotas. Critical commercial risk.")
    if excluded_projects_count:
        takeaways.append(f"{excluded_projects_count} projects have no active plan: every pending phase's module date has already passed, so they're immediate exceptions rather than a scheduled order.")
    if excluded_module_passed_mwp > 0.5:
        takeaways.append(f"{excluded_module_passed_mwp:,} MWp excluded: its module date already passed — that phase's ordering window is gone, place it as an immediate exception, not part of this plan.")
    if excluded_ftc_charged_mwp > 0.5:
        takeaways.append(f"{excluded_ftc_charged_mwp:,} MWp excluded: already FTC-charged, so the SAP balance there is a records gap, not an ordering need.")

    strategic_briefing = {
        'scenario_version': scenario_version,
        'total_balance_ordering_mwp': round(total_planned, 1),
        'critical_ordering_projects_count': excluded_projects_count,
        'proactively_leveled_projects_count': leveled_count,
        'p1_projects_count': p1_count,
        'forecast_months': forecast_months,
        'executive_takeaways': takeaways,
    }

    return {
        'forecast_months': forecast_months,
        'capacity_summary': capacity_summary,
        'strategic_briefing': strategic_briefing,
    }
