import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import LandingPage from './pages/LandingPage';
import CEODashboard from './pages/CEODashboard';
import ProjectWorkspace from './features/projects/ProjectWorkspace';
import FloatingCopilot from './components/ui/FloatingCopilot';
import KnowledgeGraphPage from './pages/KnowledgeGraphPage';
import AdminDashboard from './pages/AdminDashboard';
import PMAGDashboard from './pages/PMAGDashboard';
import { Toaster } from 'sonner';
import ProtectedRoute from './components/auth/ProtectedRoute';

function App() {
  return (
    <AuthProvider>
      <Toaster richColors position="bottom-right" />
      <BrowserRouter basename="/akasha">
        <div className="min-h-screen bg-background antialiased text-foreground flex flex-col">
          <Routes>
            <Route path="/" element={<LandingPage />} />
            {/* Executive / CEO Dashboard */}
            <Route path="/ceo-dashboard" element={<ProtectedRoute roles={['executive']}><CEODashboard /></ProtectedRoute>} />
            <Route path="/ceo-dashboard/project/:projectId" element={<ProtectedRoute roles={['executive']}><CEODashboard /></ProtectedRoute>} />
            <Route path="/ceo-dashboard/knowledge-graph" element={<ProtectedRoute roles={['executive']}><KnowledgeGraphPage /></ProtectedRoute>} />
            {/* PMAG Dashboard */}
            <Route path="/pmag" element={<ProtectedRoute roles={['pmag']}><PMAGDashboard /></ProtectedRoute>} />
            {/* Placeholder routes for other roles */}
            <Route path="/projects" element={<ProtectedRoute roles={['pmag']}><PMAGDashboard /></ProtectedRoute>} />
            <Route path="/tc-ordering" element={<ProtectedRoute roles={['pmag']}><PMAGDashboard /></ProtectedRoute>} />
            <Route path="/tc-stores" element={<ProtectedRoute roles={['pmag']}><PMAGDashboard /></ProtectedRoute>} />
            {/* Admin */}
            <Route path="/admin/*" element={<ProtectedRoute roles={['executive']}><AdminDashboard /></ProtectedRoute>} />
          </Routes>
        </div>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;

