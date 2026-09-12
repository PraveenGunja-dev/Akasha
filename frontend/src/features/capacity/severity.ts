import type { ComponentType } from 'react';
import { AlertTriangle, AlertCircle, CheckCircle2, Info } from 'lucide-react';
import type { Severity } from './types';

/* Severity presentation lives apart from the drawer so a component file
   exports only components — which is what keeps fast refresh working — and so
   the insight list and the drawer cannot fall out of step.

   Each entry carries an icon AND a written label: status is never left to
   colour alone. */
type IconType = ComponentType<{ className?: string }>;

export const SEVERITY_META: Record<Severity, { icon: IconType; label: string; chip: string }> = {
  critical: {
    icon: AlertCircle,
    label: 'Critical',
    chip: 'bg-status-critical-bg text-status-critical-fg border-status-critical-border',
  },
  warning: {
    icon: AlertTriangle,
    label: 'Warning',
    chip: 'bg-status-watch-bg text-status-watch-fg border-status-watch-border',
  },
  success: {
    icon: CheckCircle2,
    label: 'On track',
    chip: 'bg-status-healthy-bg text-status-healthy-fg border-status-healthy-border',
  },
  info: {
    icon: Info,
    label: 'Info',
    chip: 'bg-status-done-bg text-status-done-fg border-status-done-border',
  },
};
