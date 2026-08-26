import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';

export default function Login() {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [regNo, setRegNo] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [recoveryCode, setRecoveryCode] = useState('');
  const [pendingRedirect, setPendingRedirect] = useState('/');
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const res = await fetch(`/api/auth/${mode}`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reg_no: regNo, password }),
      });
      const data = await res.json();

      if (!res.ok) {
        setError(data.error || 'Something went wrong');
        setLoading(false);
        return;
      }

      const redirectUrl = data.is_admin ? '/admin' : '/';
      setPendingRedirect(redirectUrl);

      if (mode === 'register' && data.recovery_code) {
        setRecoveryCode(data.recovery_code);
        return;
      }

      navigate(redirectUrl);
    } catch (err) {
      setError('Could not reach the server.');
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-[380px] bg-panel border border-border rounded-xl p-8">
        <h1 className="text-xl font-semibold mb-1">
          learn<span className="text-green">-git</span>
        </h1>
        <p className="text-muted text-sm mb-6">
          {mode === 'login' ? 'Sign in with your registration number' : 'Register with your registration number'}
        </p>

        {!recoveryCode ? (
          <>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-xs text-muted mb-1.5" htmlFor="reg_no">Registration Number</label>
                <input
                  id="reg_no"
                  type="text"
                  required
                  placeholder="e.g. 21CS045"
                  className="w-full p-2.5 bg-bg border border-border rounded-md text-sm focus:outline-none focus:border-green"
                  value={regNo}
                  onChange={(e) => setRegNo(e.target.value)}
                />
              </div>

              <div>
                <label className="block text-xs text-muted mb-1.5" htmlFor="password">Password</label>
                <input
                  id="password"
                  type="password"
                  required
                  minLength={6}
                  className="w-full p-2.5 bg-bg border border-border rounded-md text-sm focus:outline-none focus:border-green"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>

              {error && <div className="text-red text-sm mt-3">{error}</div>}

              <button
                type="submit"
                disabled={loading}
                className="w-full mt-6 py-2.5 bg-green text-white font-semibold rounded-md text-sm disabled:bg-border disabled:cursor-not-allowed hover:bg-green/90"
              >
                {loading ? 'Please wait...' : mode === 'login' ? 'Sign in' : 'Create account'}
              </button>
            </form>

            <div className="mt-6 text-sm text-muted text-center">
              <span>{mode === 'login' ? 'New here? ' : 'Already have an account? '}</span>
              <button
                type="button"
                className="text-green hover:underline"
                onClick={() => {
                  setMode(mode === 'login' ? 'register' : 'login');
                  setError('');
                }}
              >
                {mode === 'login' ? 'Create an account' : 'Sign in'}
              </button>
            </div>
            
            <div className="mt-2.5 text-center">
              <Link to="/forgot-password" className="text-[12.5px] text-muted hover:text-text">
                Forgot your password?
              </Link>
            </div>
          </>
        ) : (
          <div className="mt-4 p-4 bg-[#1c1500] border border-yellow rounded-lg">
            <div className="text-[11px] text-yellow uppercase tracking-wider mb-1.5">Save your recovery code</div>
            <code className="block text-lg tracking-wider text-white bg-bg p-2.5 rounded-md text-center mb-2">
              {recoveryCode}
            </code>
            <p className="text-xs text-muted leading-relaxed mb-4">
              This is the only time you'll see this. If you forget your password, you'll need this code (and your reg no) to set a new one — there's no email recovery.
            </p>
            <button
              onClick={() => navigate(pendingRedirect)}
              className="w-full py-2 bg-yellow text-[#1c1500] font-semibold rounded-md text-sm"
            >
              I've saved it — continue
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
