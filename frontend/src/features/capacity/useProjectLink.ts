import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

/* ═══════════════════════════════════════════════════════════════════════════
   PROJECT LINK

   One place that knows how to reach a project workspace, so every surface —
   capacity drill-down, insight drawer, intelligence hub — navigates the same
   way. The route is /ceo-dashboard/project/:projectId, and `projectId` is the
   mapping id (e.g. "FY26-P17"), NOT the project name.

   `open` also accepts a tab so a caller can land the user on the section that
   prompted the click, e.g. the SAP tab from a PO figure.
   ═══════════════════════════════════════════════════════════════════════════ */

export type ProjectTab = 'overview' | 'intelligence' | 'sap' | 'schedule' | 'quality' | 'transmission' | 'installation';

export function useProjectLink() {
  const navigate = useNavigate();

  const open = useCallback((projectId?: string | null, tab?: ProjectTab) => {
    if (!projectId) return;
    const qs = tab ? `?tab=${tab}` : '';
    navigate(`/ceo-dashboard/project/${encodeURIComponent(projectId)}${qs}`);
  }, [navigate]);

  /** Href for anchors, so a project is genuinely linkable — middle-click and
   *  "open in new tab" work, which they do not on a div with onClick. */
  const href = useCallback(
    (projectId?: string | null, tab?: ProjectTab) =>
      projectId ? `/akasha/ceo-dashboard/project/${encodeURIComponent(projectId)}${tab ? `?tab=${tab}` : ''}` : undefined,
    [],
  );

  return { open, href };
}
