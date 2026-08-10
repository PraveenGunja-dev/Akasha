import React, { Component, type ErrorInfo, type ReactNode } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import LandingPage from './pages/LandingPage';
import CEODashboard from './pages/CEODashboard';
import ProjectWorkspace from './features/projects/ProjectWorkspace';
import FloatingCopilot from './components/ui/FloatingCopilot';
import KnowledgeGraphPage from './pages/KnowledgeGraphPage';
import AdminDashboard from './pages/AdminDashboard';
import PMAGDashboard from './pages/PMAGDashboard';
import { Toaster } from 'sonner';
import { RefreshCw, AlertTriangle } from 'lucide-react';

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

class GlobalErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  public state: ErrorBoundaryState = {
    hasError: false,
    error: null
  };

  public static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Akasha Global Error Boundary caught an error:', error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-[#0F172A] text-white flex flex-col items-center justify-center p-6 text-center">
          <div className="w-16 h-16 rounded-2xl bg-red-500/10 border border-red-500/20 flex items-center justify-center mb-4">
            <AlertTriangle className="w-8 h-8 text-red-500" />
          </div>
          <h1 className="text-2xl font-bold mb-2">Akasha Dashboard Recovery</h1>
          <p className="text-sm text-slate-400 max-w-md mb-6">
            A temporary component initialization issue occurred while loading this view. Click below to refresh your session.
          </p>
          <button
            onClick={() => {
              sessionStorage.clear();
              window.location.href = '/akasha/ceo-dashboard';
            }}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-medium text-sm transition-all shadow-lg shadow-blue-500/25"
          >
            <RefreshCw className="w-4 h-4" />
            Reload Executive Dashboard
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

function App() {
  return (
    <GlobalErrorBoundary>
      <AuthProvider>
        <Toaster richColors position="bottom-right" />
        <BrowserRouter basename="/akasha">
          <div className="min-h-screen bg-background antialiased text-foreground flex flex-col">
            <Routes>
              <Route path="/" element={<LandingPage />} />
              {/* Executive / CEO Dashboard & Aliases */}
              <Route path="/ceo-dashboard" element={<CEODashboard />} />
              <Route path="/ceo%20dashboard" element={<Navigate to="/ceo-dashboard" replace />} />
              <Route path="/ceo dashboard" element={<Navigate to="/ceo-dashboard" replace />} />
              <Route path="/ceodashboard" element={<Navigate to="/ceo-dashboard" replace />} />
              <Route path="/ceo-dashboard/project/:projectId" element={<CEODashboard />} />
              <Route path="/ceo-dashboard/knowledge-graph" element={<KnowledgeGraphPage />} />
              {/* PMAG Dashboard */}
              <Route path="/pmag" element={<PMAGDashboard />} />
              {/* Placeholder routes */}
              <Route path="/projects" element={<PMAGDashboard />} />
              <Route path="/tc-ordering" element={<PMAGDashboard />} />
              <Route path="/tc-stores" element={<PMAGDashboard />} />
              {/* Admin */}
              <Route path="/admin/*" element={<AdminDashboard />} />
              {/* Catch-all Fallback: Redirect any unknown route to /ceo-dashboard */}
              <Route path="*" element={<Navigate to="/ceo-dashboard" replace />} />
            </Routes>
          </div>
        </BrowserRouter>
      </AuthProvider>
    </GlobalErrorBoundary>
  );
}

export default App;

