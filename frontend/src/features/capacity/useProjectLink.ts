import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';

/* ═══════════════════════════════════════════════════════════════════════════
   PROJECT LINK

   One place that knows how to reach a project workspace, so every surface —
   capacity drill-down, insight drawer, intelligence hub — navigates the same
   way. Executives use /ceo-dashboard/project/:projectId; every other role
   /project/:projectId (pages/ProjectPage.tsx) - the CEO route is closed to
   them. `projectId` is the
   mapping id (e.g. "FY26-P17"), NOT the project name.

   `open` also accepts a tab so a caller can land the user on the section that
   prompted the click, e.g. the SAP tab from a PO figure.
   ═══════════════════════════════════════════════════════════════════════════ */

export type ProjectTab = 'overview' | 'intelligence' | 'sap' | 'schedule' | 'quality' | 'transmission' | 'installation';

export function useProjectLink() {
  const navigate = useNavigate();
  const { can } = useAuth();
  const base = can('dashboard.executive') ? '/ceo-dashboard/project' : '/project';

  const open = useCallback((projectId?: string | null, tab?: ProjectTab) => {
    if (!projectId) return;
    const qs = tab ? `?tab=${tab}` : '';
    navigate(`${base}/${encodeURIComponent(projectId)}${qs}`);
  }, [navigate, base]);

  /** Href for anchors, so a project is genuinely linkable — middle-click and
   *  "open in new tab" work, which they do not on a div with onClick. */
  const href = useCallback(
    (projectId?: string | null, tab?: ProjectTab) =>
      projectId ? `/akasha${base}/${encodeURIComponent(projectId)}${tab ? `?tab=${tab}` : ''}` : undefined,
    [base],
  );

  return { open, href };
}
