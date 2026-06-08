import { BrowserRouter, Routes, Route } from 'react-router-dom';
import LandingPage from './pages/LandingPage';
import CEODashboard from './pages/CEODashboard';
import ProjectWorkspace from './components/sections/ProjectWorkspace';
import FloatingCopilot from './components/ui/FloatingCopilot';

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-background antialiased text-foreground">
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/dashboard" element={<CEODashboard />} />
          <Route path="/dashboard/project/:projectId" element={<ProjectWorkspace />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;
