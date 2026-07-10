import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ReactLenis } from 'lenis/react';
import 'lenis/dist/lenis.css';
import { AuthProvider } from './context/AuthContext';
import LandingPage from './pages/LandingPage';
import CEODashboard from './pages/CEODashboard';
import ProjectWorkspace from './features/projects/ProjectWorkspace';
import FloatingCopilot from './components/ui/FloatingCopilot';
import KnowledgeGraphPage from './pages/KnowledgeGraphPage';
import AdminDashboard from './pages/AdminDashboard';
import PMAGDashboard from './pages/PMAGDashboard';
import { Toaster } from 'sonner';

function App() {
  return (
    <AuthProvider>
      <Toaster richColors position="bottom-right" />
      <BrowserRouter basename="/akasha">
        <ReactLenis root options={{ lerp: 0.08, smoothWheel: true }}>
          <div className="min-h-screen bg-background antialiased text-foreground flex flex-col">
            <Routes>
              <Route path="/" element={<LandingPage />} />
              {/* Executive / CEO Dashboard */}
              <Route path="/dashboard" element={<CEODashboard />} />
              <Route path="/dashboard/project/:projectId" element={<CEODashboard />} />
              <Route path="/dashboard/knowledge-graph" element={<KnowledgeGraphPage />} />
              {/* PMAG Dashboard */}
              <Route path="/pmag" element={<PMAGDashboard />} />
              {/* Placeholder routes for other roles */}
              <Route path="/projects" element={<PMAGDashboard />} />
              <Route path="/tc-ordering" element={<PMAGDashboard />} />
              <Route path="/tc-stores" element={<PMAGDashboard />} />
              {/* Admin */}
              <Route path="/admin/*" element={<AdminDashboard />} />
            </Routes>
          </div>
        </ReactLenis>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;

