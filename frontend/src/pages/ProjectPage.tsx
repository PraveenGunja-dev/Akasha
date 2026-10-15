/* /project/:projectId - one project's workspace for any signed-in role. The
   links in emails and on shared screens point here, so a TC Ordering or TC
   Head user opens the project instead of the executive-only page. What the
   user may see is still limited to their portfolios by the server.
   Executives are sent on to the CEO dashboard's project view they know. */
import { Navigate, useLocation, useNavigate, useParams } from 'react-router-dom';
import ProjectWorkspace from '../features/projects/ProjectWorkspace';
import { useAuth } from '../context/AuthContext';

export default function ProjectPage() {
  const { projectId = '' } = useParams();
  const { search } = useLocation();
  const navigate = useNavigate();
  const { user, can, homeFor } = useAuth();
  if (can('dashboard.executive')) {
    return <Navigate to={`/ceo-dashboard/project/${encodeURIComponent(projectId)}${search}`} replace />;
  }
  return (
    <main className="min-h-screen bg-background px-3 py-4 sm:px-5">
      <ProjectWorkspace projectId={projectId}
        onBack={() => (window.history.length > 1 ? navigate(-1) : navigate(user ? homeFor(user, null) : '/workspaces'))} />
    </main>
  );
}
