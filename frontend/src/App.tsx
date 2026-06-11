import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ReactLenis } from 'lenis/react';
import 'lenis/dist/lenis.css';
import LandingPage from './pages/LandingPage';
import CEODashboard from './pages/CEODashboard';
import ProjectWorkspace from './components/sections/ProjectWorkspace';
import FloatingCopilot from './components/ui/FloatingCopilot';
import KnowledgeGraphPage from './pages/KnowledgeGraphPage';

function App() {
  return (
    <BrowserRouter basename="/akasha">
      <ReactLenis root options={{ lerp: 0.08, smoothWheel: true }}>
        <div className="min-h-screen bg-background antialiased text-foreground flex flex-col">
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/dashboard" element={<CEODashboard />} />
            <Route path="/dashboard/project/:projectId" element={<CEODashboard />} />
            <Route path="/dashboard/knowledge-graph" element={<KnowledgeGraphPage />} />
          </Routes>
        </div>
      </ReactLenis>
    </BrowserRouter>
  );
}

export default App;
