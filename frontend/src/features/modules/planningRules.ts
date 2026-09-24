/* Every rule the Ordering Schedule applies, in one place.
 *
 * This is the single source for the on-screen "How this plan is built" panel
 * and the Planning Rules sheet in the XLSX export, so a number defended in a
 * meeting reads the same wherever it is quoted. Each entry names the rule, what
 * it does, and — where it matters — the file that enforces it, so anyone can
 * check the claim against the code rather than taking it on trust.
 *
 * Keep these in step with backend/services/module_planner.py and
 * backend/routers/module_deliveries.py. A rule stated here but not enforced
 * there is worse than no rule at all.
 */

export interface PlanningRule {
  /** Short handle, used as the row label. */
  name: string;
  /** What the rule actually does, in a sentence a planner can act on. */
  detail: string;
  /** Where it is enforced, for anyone who wants to verify it. */
  source?: string;
}

export interface RuleGroup {
  title: string;
  rules: PlanningRule[];
}

export const PLANNING_RULES: RuleGroup[] = [
  {
    title: 'What gets planned',
    rules: [
      {
        name: 'Quantity planned',
        detail:
          'The Balance Ordering (MWp) column — capacity still to be ordered — is what the monthly plan distributes. Not the project total, and not the phase capacities: if those exceed the balance, the surplus phases are simply not ordered.',
        source: 'module_planner.py',
      },
      {
        name: 'Scope',
        detail:
          'Solar projects carrying a capacity. Wind rows have no module tracking and are excluded.',
        source: 'module_deliveries.py',
      },
      {
        name: 'Nothing left to order',
        detail:
          'A project whose balance is zero shows no plan. A commissioned project whose FTC phases are all charged but which still shows a SAP balance is a PO/GRN records gap, not an ordering need, so it is excluded from the plan and says so in Remarks.',
        source: 'module_planner.py',
      },
    ],
  },
  {
    title: 'Phase sequencing',
    rules: [
      {
        name: 'One phase at a time',
        detail:
          'Phases are sorted by the date their order must be placed, and each is given its FULL requirement (phase MWac x OL) before the next one starts. No phase is scaled down to make everything fit.',
        source: 'module_planner.py',
      },
      {
        name: 'Requirement per phase',
        detail:
          'Phase MWac (from its P6 milestone name) x the project OL ratio. A phase whose milestone states no capacity takes whatever balance remains.',
        source: 'module_planner.py',
      },
      {
        name: 'When the balance runs out',
        detail:
          'The last funded phase is truncated to what is left and every later phase is not ordered at all — on the reading that what has already been ordered covered the earlier phases.',
        source: 'module_planner.py',
      },
      {
        name: 'A moved order moves everything after it',
        detail:
          'When vendor quota pushes an order into a later month, its TC and FTC move by the same amount — the lead time and the 45-day install run from the date the order is actually placed, not from the original plan. The tooltip shows the new date with the original struck through beneath it.',
        source: 'module_planner.py',
      },
      {
        name: 'A phase split across months',
        detail:
          'Vendor quota can spread one phase over two consecutive months. The sequence still holds: the next phase does not start until the current one is ordered in full.',
        source: 'module_planner.py',
      },
    ],
  },
  {
    title: 'Dates',
    rules: [
      {
        name: 'FTC (First Time Charging)',
        detail: 'Read from the project P6 milestone. Every other date is derived backwards from it.',
        source: 'module_deliveries.py',
      },
      {
        name: 'TC date',
        detail: 'FTC minus 45 days, for installation.',
      },
      {
        name: 'Module order date',
        detail:
          'TC minus the supplier lead time. This is the date the order must actually be placed.',
      },
      {
        name: 'Lead times',
        detail: 'China and SEA 136 days; ALMM, ALCM and DCR 98 days.',
        source: 'module_planner.py',
      },
      {
        name: 'No FTC in P6',
        detail:
          'Falls back to SCOD, then AOP, then LTA. A project with none of those is scheduled from today plus the full lead time, and that is an inference, not a measurement.',
        source: 'module_planner.py',
      },
    ],
  },
  {
    title: 'Vendor capacity levelling',
    rules: [
      {
        name: 'Monthly ceilings',
        detail: 'China 750 MW, SEA 500 MW, ALMM 500 MW, ALCM 100 MW, DCR 100 MW per month.',
        source: 'module_planner.py',
      },
      {
        name: 'Pull earlier first',
        detail:
          'When the target month is full, the order is pulled into earlier months before it is ever pushed later. Those cells are marked "Quota Leveled (Pulled Early)".',
      },
      {
        name: 'Push later, within LTA',
        detail:
          'If no earlier month has room, it is pushed later. While the later date still meets the LTA, it is "Extended to LTA" — the FTC slips but transmission is not the constraint.',
      },
      {
        name: 'Push past LTA',
        detail:
          'If it is pushed beyond the LTA date it is flagged "Capacity Delayed" — critical commercial risk, because both the FTC and the transmission window are missed.',
      },
      {
        name: 'Priority order',
        detail:
          'PPA projects first, then P1, P2, standard, then earliest FTC. This decides who gets the scarce monthly quota.',
      },
    ],
  },
  {
    title: 'Overdue orders',
    rules: [
      {
        name: 'Ordering window already passed',
        detail:
          'A phase whose order date is in the past is still real demand, so it is planned into the earliest month still open and marked overdue. It is not dropped from the plan.',
        source: 'module_planner.py',
      },
      {
        name: 'What overdue does NOT mean',
        detail:
          'The month shown is the earliest date an order can still be placed. It does not recover the original FTC — that date is already missed.',
      },
    ],
  },
  {
    title: 'LTA breach check',
    rules: [
      {
        name: 'PPA projects',
        detail: 'The LTA date must not fall after SCOD. If it does, the cell is flagged.',
        source: 'module_deliveries.py',
      },
      {
        name: 'Non-PPA projects',
        detail: 'The LTA date must not fall after AOP (Plan).',
      },
      {
        name: 'How PPA is decided',
        detail:
          'From the contract token in the P6 project name (_PPA / _MERCHANT / _GROUP), present on 40 of 45 solar rows. The display project name is not used — it disagrees with the P6 token on 14 rows.',
      },
      {
        name: 'No contract token',
        detail:
          'The row is measured against AOP by default and the tooltip says so. Confirm the contract type before acting on it.',
      },
      {
        name: 'Missing basis date',
        detail:
          'A project with no SCOD (PPA) or no AOP (non-PPA) is not flagged. A missing date is no signal, not a pass.',
      },
    ],
  },
  {
    title: 'Known data limits',
    rules: [
      {
        name: 'Module wattage',
        detail:
          'MWp per PO line is quantity x the module wattage read from the SAP material text. Some vendors state it only inside the part number (Jinko JKM590N, Goldi GF-585); those are now read, but a line stating no rating at all is excluded from MWp rather than guessed.',
        source: 'services/module_wattage.py',
      },
      {
        name: 'Shared WBS elements',
        detail:
          'Where several projects sit on one WBS element, SAP cannot tell them apart, so the PO is apportioned by capacity. Those rows are marked as apportioned, not measured.',
        source: 'module_deliveries.py',
      },
      {
        name: 'PO value counts POrd only',
        detail: 'A PReq is a requisition, not an order, and is excluded from every PO figure.',
        source: 'slr_rules.py',
      },
      {
        name: 'No delivery date in ZSPS',
        detail:
          'The extract carries no GRN or delivery date, so there is no overdue, ageing or lateness signal on deliveries. Delivery is a cumulative value only.',
      },
    ],
  },
];

/** Flat list, for the export sheet. */
export const flatRules = (): { group: string; name: string; detail: string; source: string }[] =>
  PLANNING_RULES.flatMap(g =>
    g.rules.map(r => ({ group: g.title, name: r.name, detail: r.detail, source: r.source ?? '' })));
