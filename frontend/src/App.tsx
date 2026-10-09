import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import LandingPage from './pages/LandingPage';
import CEODashboard from './pages/CEODashboard';
import ProjectWorkspace from './features/projects/ProjectWorkspace';
import FloatingCopilot from './components/ui/FloatingCopilot';
import KnowledgeGraphPage from './pages/KnowledgeGraphPage';
import AdminDashboard from './pages/AdminDashboard';
import RoleWorkspace from './features/workspace/RoleWorkspace';
import WindDashboard from './pages/WindDashboard';
import RequireAuth from './components/auth/RequireAuth';
import DashboardPicker from './pages/auth/DashboardPicker';
import ChangePassword from './pages/auth/ChangePassword';
import { Toaster } from 'sonner';
import { SecurityAlertWatcher } from './features/admin/securityAlerts';

function App() {
  return (
    <AuthProvider>
      <Toaster richColors position="bottom-right" />
      <BrowserRouter basename="/akasha">
        {/* Security alerts for administrators: badge + toast on a new one */}
        <SecurityAlertWatcher />
        <div className="min-h-screen bg-background antialiased text-foreground flex flex-col">
          <Routes>
            <Route path="/" element={<LandingPage />} />
            {/* Sign-in is the landing page with its sign-in panel open */}
            <Route path="/login" element={<LandingPage />} />
            {/* Everything below needs a signed-in user; `anyOf` is the permission
                that opens the page. The server enforces the same on every API call. */}
            <Route path="/workspaces" element={<RequireAuth><DashboardPicker /></RequireAuth>} />
            <Route path="/account/password" element={<RequireAuth><ChangePassword /></RequireAuth>} />
            {/* Executive / CEO */}
            <Route path="/ceo-dashboard" element={<RequireAuth anyOf={['dashboard.executive']}><CEODashboard /></RequireAuth>} />
            <Route path="/ceo-dashboard/project/:projectId" element={<RequireAuth anyOf={['dashboard.executive']}><CEODashboard /></RequireAuth>} />
            <Route path="/ceo-dashboard/knowledge-graph" element={<RequireAuth anyOf={['dashboard.executive']}><KnowledgeGraphPage /></RequireAuth>} />
            <Route path="/wind-dashboard" element={<RequireAuth anyOf={['dashboard.executive']}><WindDashboard /></RequireAuth>} />
            {/* Role dashboards: one shell, each with its own sections and KPIs
                (features/workspace/dashboards.ts) */}
            <Route path="/pmag" element={<RequireAuth anyOf={['dashboard.pmag']}><RoleWorkspace key="pmag" dashboard="pmag" /></RequireAuth>} />
            <Route path="/projects" element={<RequireAuth anyOf={['dashboard.projects']}><RoleWorkspace key="projects" dashboard="projects" /></RequireAuth>} />
            <Route path="/tc-ordering" element={<RequireAuth anyOf={['dashboard.tc_ordering']}><RoleWorkspace key="tc_ordering" dashboard="tc_ordering" /></RequireAuth>} />
            <Route path="/tc-stores" element={<RequireAuth anyOf={['dashboard.tc_stores']}><RoleWorkspace key="tc_stores" dashboard="tc_stores" /></RequireAuth>} />
            {/* Admin console */}
            <Route path="/admin/*" element={<RequireAuth anyOf={['users.manage', 'roles.manage', 'audit.view', 'data.edit']}><AdminDashboard /></RequireAuth>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;

