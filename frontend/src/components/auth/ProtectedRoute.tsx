import type { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';


const ROLE_ROUTES: Record<string, string> = {
  executive: '/ceo-dashboard',
  pmag: '/pmag',
};

export default function ProtectedRoute({ children, roles }: { children: ReactNode; roles: string[] }) {
  const { user, isAuthenticated, isLoading } = useAuth();
  if (isLoading) {
    return <div className="min-h-screen flex items-center justify-center bg-background"><Loader2 className="w-7 h-7 animate-spin text-primary" /></div>;
  }
  if (!isAuthenticated || !user) return <Navigate to="/" replace />;
  if (!roles.includes(user.role)) return <Navigate to={ROLE_ROUTES[user.role] || '/'} replace />;
  return children;
}
