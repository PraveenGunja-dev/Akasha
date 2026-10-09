import type { ReactNode } from 'react';
import { Link, Navigate, useLocation } from 'react-router-dom';
import { ShieldOff } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { Loader as AkLoader } from '../ui/primitives';

/* Keeps a page behind sign-in and, when `anyOf` is given, behind a permission.
   - checking the session: spinner
   - no session: to /login, then back here
   - a password change pending: to /account/password
   - signed in without the permission: an access-denied page
   The server enforces the same rules on every API call; this only decides
   what to render. */
export default function RequireAuth({ children, anyOf }: { children: ReactNode; anyOf?: string[] }) {
  const { user, isLoading, canAny } = useAuth();
  const location = useLocation();
  const here = `${location.pathname}${location.search}`;

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background text-muted-foreground">
        <AkLoader size="md" label="Checking your session…" />
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace state={{ from: here }} />;
  if (user.must_change_password && location.pathname !== '/account/password') {
    return <Navigate to="/account/password" replace state={{ from: here }} />;
  }
  if (anyOf && !canAny(anyOf)) return <AccessDenied />;
  return <>{children}</>;
}

function AccessDenied() {
  const { user } = useAuth();
  const home = user && user.dashboards.length > 1 ? '/workspaces' : user?.dashboards[0]?.route ?? '/workspaces';
  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="bento-card w-full max-w-md p-6 text-center">
        <ShieldOff className="mx-auto h-8 w-8 text-muted-foreground" aria-hidden />
        <h1 className="mt-3 text-base font-semibold text-foreground">You don't have access to this page</h1>
        <p className="mt-1.5 text-sm text-muted-foreground">
          Your role ({user?.role_name}) does not include it. Ask an administrator if you need it.
        </p>
        <Link to={home} className="mt-5 inline-flex rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2">
          Go to my dashboards
        </Link>
      </div>
    </main>
  );
}
