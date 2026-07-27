import { useState } from 'react';
import { Loader2, Lock } from 'lucide-react';
import { useAuth } from '../context/AuthContext';


export default function LoginPage() {
  const { authMode, login } = useAuth();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const handleLogin = async (role?: 'executive' | 'pmag') => {
    setLoading(true);
    setError('');
    const result = await login(role);
    if (!result.success) setError(result.message);
    setLoading(false);
  };
  return (
    <div className="min-h-screen flex items-center justify-center bg-[#060b18] px-4">
      <div className="w-full max-w-md rounded-3xl border border-white/10 bg-white/5 p-8 text-center">
        <Lock className="w-10 h-10 text-primary mx-auto mb-4" />
        <h1 className="text-2xl font-bold text-white">Sign in to Akasha</h1>
        <p className="text-sm text-white/45 mt-2 mb-6">{authMode === 'development' ? 'Select a temporary development role.' : 'Use your organization Microsoft account.'}</p>
        {authMode === 'development' ? (
          <div className="space-y-3">
            <button onClick={() => handleLogin('executive')} disabled={loading} className="w-full py-3 rounded-xl bg-primary text-white font-semibold flex items-center justify-center gap-2">{loading && <Loader2 className="w-4 h-4 animate-spin" />} Continue as CEO</button>
            <button onClick={() => handleLogin('pmag')} disabled={loading} className="w-full py-3 rounded-xl bg-[#75479c] text-white font-semibold flex items-center justify-center gap-2">{loading && <Loader2 className="w-4 h-4 animate-spin" />} Continue as PMAG</button>
          </div>
        ) : (
          <button onClick={() => handleLogin()} disabled={loading} className="w-full py-3 rounded-xl bg-primary text-white font-semibold flex items-center justify-center gap-2">
            {loading && <Loader2 className="w-4 h-4 animate-spin" />}
            Sign in with Microsoft
          </button>
        )}
        {error && <p className="text-sm text-red-300 mt-4">{error}</p>}
      </div>
    </div>
  );
}
