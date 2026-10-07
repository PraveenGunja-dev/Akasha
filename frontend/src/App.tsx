import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import LandingPage from './pages/LandingPage';
import CEODashboard from './pages/CEODashboard';
import ProjectWorkspace from './features/projects/ProjectWorkspace';
import FloatingCopilot from './components/ui/FloatingCopilot';
import KnowledgeGraphPage from './pages/KnowledgeGraphPage';
import AdminDashboard from './pages/AdminDashboard';
import PMAGDashboard from './pages/PMAGDashboard';
import WindDashboard from './pages/WindDashboard';
import RequireAuth from './components/auth/RequireAuth';
import { Toaster } from 'sonner';

function App() {
  return (
    <AuthProvider>
      <Toaster richColors position="bottom-right" />
      <BrowserRouter basename="/akasha">
        <div className="min-h-screen bg-background antialiased text-foreground flex flex-col">
          <Routes>
            <Route path="/" element={<LandingPage />} />
            {/* Sign-in is the landing page with its sign-in panel open */}
            <Route path="/login" element={<LandingPage />} />
            {/* Everything below needs a signed-in user */}
            {/* Executive / CEO Dashboard */}
            <Route path="/ceo-dashboard" element={<RequireAuth><CEODashboard /></RequireAuth>} />
            <Route path="/ceo-dashboard/project/:projectId" element={<RequireAuth><CEODashboard /></RequireAuth>} />
            <Route path="/ceo-dashboard/knowledge-graph" element={<RequireAuth><KnowledgeGraphPage /></RequireAuth>} />
            {/* PMAG Dashboard */}
            <Route path="/pmag" element={<RequireAuth><PMAGDashboard /></RequireAuth>} />
            <Route path="/wind-dashboard" element={<RequireAuth><WindDashboard /></RequireAuth>} />
            {/* Placeholder routes for other roles */}
            <Route path="/projects" element={<RequireAuth><PMAGDashboard /></RequireAuth>} />
            <Route path="/tc-ordering" element={<RequireAuth><PMAGDashboard /></RequireAuth>} />
            <Route path="/tc-stores" element={<RequireAuth><PMAGDashboard /></RequireAuth>} />
            {/* Admin */}
            <Route path="/admin/*" element={<RequireAuth><AdminDashboard /></RequireAuth>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;

