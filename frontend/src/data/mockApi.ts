// Types for P6 Project Data
export interface P6ProjectData {
  id: string;
  name: string;
  plannedProgress: number; // percentage
  actualProgress: number;  // percentage
  criticalPathDelayDays: number;
  status: 'On Track' | 'Delayed' | 'Critical';
}

// Types for SAP Financials
export interface SAPFinancials {
  quarter: string;
  plannedCapex: number; // in millions
  actualCapex: number;  // in millions
  cashFlowVariancePercent: number;
}

// Types for Logistics (Module Tracker)
export interface LogisticsStatus {
  category: string;
  count: number;
  color: string;
}

// Mock Data representing API response
export const mockP6Projects: P6ProjectData[] = [
  { id: 'PROJ-001', name: 'Khavda', plannedProgress: 85, actualProgress: 82, criticalPathDelayDays: 3, status: 'On Track' },
  { id: 'PROJ-002', name: 'Mundra', plannedProgress: 90, actualProgress: 88, criticalPathDelayDays: 0, status: 'On Track' },
  { id: 'PROJ-003', name: 'Dholera', plannedProgress: 75, actualProgress: 70, criticalPathDelayDays: 14, status: 'Delayed' },
  { id: 'PROJ-004', name: 'Jaisalmer', plannedProgress: 60, actualProgress: 61, criticalPathDelayDays: 0, status: 'On Track' },
  { id: 'PROJ-005', name: 'Bhuj', plannedProgress: 45, actualProgress: 40, criticalPathDelayDays: 21, status: 'Critical' },
];

export const mockSAPFinancials: SAPFinancials[] = [
  { quarter: 'Q1', plannedCapex: 120, actualCapex: 115, cashFlowVariancePercent: -4.1 },
  { quarter: 'Q2', plannedCapex: 150, actualCapex: 140, cashFlowVariancePercent: -6.6 },
  { quarter: 'Q3', plannedCapex: 180, actualCapex: 190, cashFlowVariancePercent: 5.5 },
  { quarter: 'Q4', plannedCapex: 210, actualCapex: 195, cashFlowVariancePercent: -7.1 },
];

export const mockLogistics: LogisticsStatus[] = [
  { category: 'Delivered', count: 1048, color: '#0B74B0' },
  { category: 'In Transit', count: 735, color: '#75479C' },
  { category: 'At Port', count: 580, color: '#BD3861' },
  { category: 'Delayed', count: 300, color: '#f59e0b' },
];
