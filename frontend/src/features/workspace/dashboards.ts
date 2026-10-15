/* The four role dashboards (Executive keeps its own page).

   Each lists its sections, in sidebar order, and the client's KPI document for
   that dashboard with an honest status per KPI:
     live     - shown today, in the section named
     partial  - shown in part; `note` says what is missing
     planned  - the data is in Akasha; the panel is still to be built
     no-data  - no source in Akasha yet; `note` names what is needed
   Nothing here invents a figure: a KPI without data says so. */

export type SectionId =
  | 'overview' | 'project360' | 'schedule' | 'capacity' | 'ordering' | 'quality'
  | 'approvals' | 'transmission' | 'sap' | 'einvoice' | 'reports' | 'kpis';

export type KpiStatus = 'live' | 'partial' | 'planned' | 'no-data';

export interface KpiRow {
  kpi: string;
  source: 'Projects' | 'TC';
  status: KpiStatus;
  section?: SectionId;
  note?: string;
}

export interface DashboardConfig {
  key: string;
  title: string;
  purpose: string;
  groups: { title: string; sections: SectionId[] }[];
  kpis: KpiRow[];
}

const NO_ISSUE_REGISTER = 'No issue register is connected to Akasha';

export const DASHBOARDS: Record<string, DashboardConfig> = {
  pmag: {
    key: 'pmag',
    title: 'PMAG',
    purpose: 'Governance and cross-functional oversight: risks, compliance and project health across the portfolio.',
    groups: [
      { title: 'Dashboard', sections: ['overview', 'project360'] },
      { title: 'Governance', sections: ['quality', 'approvals', 'schedule', 'capacity'] },
      { title: 'Output', sections: ['reports', 'kpis'] },
    ],
    kpis: [
      { kpi: 'MW at risk of delay (next 30/60/90 days)', source: 'Projects', status: 'planned', note: 'From P6 forecast vs baseline finish; will be labelled as a forecast' },
      { kpi: 'QA NC count and ageing by site / contractor', source: 'Projects', status: 'live', section: 'quality' },
      { kpi: 'RFI / NC count and ageing (critical / non-critical)', source: 'Projects', status: 'live', section: 'quality' },
      { kpi: 'Critical statutory approvals completion (%)', source: 'Projects', status: 'live', section: 'approvals' },
      { kpi: 'Issues in the issue register (weather, financial, land …)', source: 'Projects', status: 'no-data', note: NO_ISSUE_REGISTER },
      { kpi: 'Resource augmentation (MMM) vs availability', source: 'Projects', status: 'no-data', note: 'P6 holds resource assignments; which ones are manpower needs confirming' },
      { kpi: 'Procurement progress (plan % vs actual %)', source: 'TC', status: 'partial', note: 'Modules only (Ordering Schedule on Projects / TC); no plan dates for other materials' },
      { kpi: 'PR / SR / NFA to PO / SO cycle time vs SLA', source: 'TC', status: 'planned', note: 'PR and PO release dates are in ME2J; the SLA days are needed' },
      { kpi: 'Count of PO amendments', source: 'TC', status: 'planned', note: 'Amendment numbers are in ME2J' },
      { kpi: 'Ageing of overdue vendor invoices vs contract terms', source: 'Projects', status: 'partial', note: 'Invoice ageing is in E-Invoice; contract payment terms are not in Akasha' },
      { kpi: 'Contracts adhered to policy (Pulse)', source: 'Projects', status: 'no-data', note: 'Pulse contract-policy data is not synced' },
    ],
  },

  projects: {
    key: 'projects',
    title: 'Projects',
    purpose: 'Execution: construction progress, material readiness and site issues for Solar, Wind and BESS.',
    groups: [
      { title: 'Dashboard', sections: ['overview', 'project360'] },
      { title: 'Execution', sections: ['schedule', 'capacity', 'ordering', 'transmission'] },
      { title: 'Site', sections: ['quality', 'approvals'] },
      { title: 'Output', sections: ['reports', 'kpis'] },
    ],
    kpis: [
      { kpi: 'Progress actual vs plan, with piling / MMS / modules / inverters', source: 'Projects', status: 'live', section: 'schedule' },
      { kpi: 'PSS progress (% complete), milestone based', source: 'Projects', status: 'planned', note: 'PSS milestones are in P6' },
      { kpi: 'Transmission line CKM progress (solar)', source: 'Projects', status: 'live', section: 'transmission', note: 'Shown to all-portfolio users; portfolio filter still to add' },
      { kpi: 'Wind KPIs: WTG foundation, erection … actual vs plan', source: 'Projects', status: 'live', section: 'project360' },
      { kpi: 'Insurance, licence and land approvals with reminders', source: 'Projects', status: 'partial', section: 'approvals', note: 'Insurance and statutory approvals are live; land approvals are not in Akasha' },
      { kpi: 'WTG material set readiness', source: 'Projects', status: 'no-data', note: 'Needs the WTG bill of material per set' },
      { kpi: 'WTG main component supply status (%)', source: 'TC', status: 'planned', note: 'From SAP POs and Ariba deliveries on WTG lines' },
      { kpi: 'Issues in the issue register', source: 'Projects', status: 'no-data', note: NO_ISSUE_REGISTER },
      { kpi: 'Average ageing of open punch points', source: 'Projects', status: 'no-data', note: 'No punch-list source is connected' },
      { kpi: 'Machinery productivity plan vs actual (e.g. crane)', source: 'Projects', status: 'no-data', note: 'No equipment log is connected' },
      { kpi: 'Material reconciliation and theft', source: 'Projects', status: 'partial', section: 'project360', note: 'Issue vs consumption from SAP MB51; theft records are not in Akasha' },
      { kpi: 'Robotic module cleaning systems (Nos)', source: 'Projects', status: 'planned', note: 'Deliveries of robotic cleaning units are in Ariba' },
    ],
  },

  tc_ordering: {
    key: 'tc_ordering',
    title: 'TC Ordering',
    purpose: 'The procurement lifecycle: requisition and ordering through cost control and vendor performance.',
    groups: [
      { title: 'Dashboard', sections: ['overview', 'project360'] },
      { title: 'Ordering', sections: ['ordering', 'sap', 'einvoice'] },
      { title: 'Output', sections: ['kpis'] },
    ],
    kpis: [
      { kpi: 'Procurement progress (plan % vs actual %)', source: 'TC', status: 'partial', section: 'ordering', note: 'Modules only; other materials have no plan dates' },
      { kpi: 'PR / SR / NFA to PO / SO cycle time vs SLA', source: 'TC', status: 'planned', note: 'ME2J release dates; SLA days needed' },
      { kpi: 'TAT for PR/NFA → PO → GRN → invoicing', source: 'TC', status: 'planned', note: 'ME2J + Ariba GRN and invoice dates' },
      { kpi: 'Order completion rate', source: 'TC', status: 'planned', note: 'SAP CO commitment vs actual' },
      { kpi: 'Order status (supply / service) and payment status', source: 'TC', status: 'partial', section: 'sap', note: 'Order status in SAP; payment status from E-Invoice' },
      { kpi: '% emergency PR, PO, SO, NFA', source: 'TC', status: 'no-data', note: 'No emergency flag on requisitions in the extracts' },
      { kpi: 'TC (ordering) budget vs actual', source: 'TC', status: 'no-data', note: 'The ordering budget is not in Akasha' },
      { kpi: 'TC internal estimate (IE) vs actual', source: 'TC', status: 'no-data', note: 'Internal estimates are not in Akasha' },
      { kpi: 'Historical pricing of materials across vendors', source: 'TC', status: 'planned', note: 'Unit rates from SAP CO lines' },
      { kpi: 'Vendor / SO performance evaluation', source: 'TC', status: 'planned', note: 'Delivery lead times from Ariba; no quality score source' },
      { kpi: 'PO dates and status (open, closed) and PRs', source: 'TC', status: 'live', section: 'sap' },
      { kpi: 'Count of PO amendments', source: 'TC', status: 'planned', note: 'Amendment numbers are in ME2J' },
      { kpi: 'PO automation / STP rate', source: 'TC', status: 'no-data', note: 'No automation flag in the extracts' },
    ],
  },

  tc_stores: {
    key: 'tc_stores',
    title: 'TC Stores',
    purpose: 'Inventory: material availability at site and the efficiency of the stores function.',
    groups: [
      { title: 'Dashboard', sections: ['overview'] },
      { title: 'Stores', sections: ['sap', 'ordering'] },
      { title: 'Output', sections: ['kpis'] },
    ],
    kpis: [
      { kpi: 'Inventory turnover rate (ABC)', source: 'TC', status: 'planned', note: 'MB51 issues over MB52 stock; ABC derived from value' },
      { kpi: 'Inventory stockout rate', source: 'TC', status: 'no-data', note: 'Needs requirement dates per material' },
      { kpi: 'Inventory ageing', source: 'TC', status: 'planned', note: 'MB52 stock with posting dates' },
      { kpi: 'GE to GRN ageing', source: 'TC', status: 'no-data', note: 'Gate-entry records are not in Akasha' },
      { kpi: 'Ageing and value of materials issued to contractors', source: 'TC', status: 'planned', note: 'MB51 issue movements' },
      { kpi: 'Return rate of materials to vendors', source: 'TC', status: 'planned', note: 'MB51 return movements' },
      { kpi: 'Average milestone delay due to stores (days)', source: 'TC', status: 'no-data', note: 'Delay reasons are not attributed to stores' },
      { kpi: 'Scrap as % of inventory value', source: 'TC', status: 'planned', note: 'MB51 scrap movements, to be confirmed' },
      { kpi: 'Total inventory (Wind, Solar, BESS) plant-wise', source: 'TC', status: 'partial', section: 'ordering', note: 'Module stock is live; all-material stock by plant is planned (MB52)' },
      { kpi: 'Inventory analysis (VED, FSN, ABC)', source: 'TC', status: 'planned', note: 'ABC and FSN from SAP; VED needs a criticality list' },
      { kpi: 'Inventory optimisation (min / max / reorder level)', source: 'TC', status: 'no-data', note: 'Reorder levels are not maintained in the extracts' },
      { kpi: 'Emergency / spot procurement cost %', source: 'TC', status: 'no-data', note: 'No emergency flag in the extracts' },
    ],
  },
};
