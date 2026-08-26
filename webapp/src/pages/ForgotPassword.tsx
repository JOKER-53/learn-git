import { useState } from 'react';
import { Link } from 'react-router-dom';

export default function ForgotPassword() {
  const [regNo, setRegNo] = useState('');
  const [recoveryCode, setRecoveryCode] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);
  

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const res = await fetch('/api/auth/reset-password', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reg_no: regNo, recovery_code: recoveryCode, new_password: newPassword }),
      });
      const data = await res.json();

      if (!res.ok) {
        setError(data.error || 'Something went wrong');
        setLoading(false);
        return;
      }

      setSuccess(true);
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
        <p className="text-muted text-sm mb-6">Reset your password</p>

        {success ? (
          <div className="text-center">
            <div className="text-green text-sm mb-4">Password reset successfully!</div>
            <Link to="/login" className="w-full block py-2.5 bg-green text-white font-semibold rounded-md text-sm">
              Back to sign in
            </Link>
          </div>
        ) : (
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
                <label className="block text-xs text-muted mb-1.5" htmlFor="recovery_code">Recovery Code</label>
                <input
                  id="recovery_code"
                  type="text"
                  required
                  placeholder="The 12-character code you saved"
                  className="w-full p-2.5 bg-bg border border-border rounded-md text-sm font-mono focus:outline-none focus:border-green"
                  value={recoveryCode}
                  onChange={(e) => setRecoveryCode(e.target.value)}
                />
              </div>

              <div>
                <label className="block text-xs text-muted mb-1.5" htmlFor="new_password">New Password</label>
                <input
                  id="new_password"
                  type="password"
                  required
                  minLength={6}
                  className="w-full p-2.5 bg-bg border border-border rounded-md text-sm focus:outline-none focus:border-green"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                />
              </div>

              {error && <div className="text-red text-sm mt-3">{error}</div>}

              <button
                type="submit"
                disabled={loading}
                className="w-full mt-6 py-2.5 bg-yellow text-[#1c1500] font-semibold rounded-md text-sm disabled:opacity-50 disabled:cursor-not-allowed hover:bg-yellow/90"
              >
                {loading ? 'Resetting...' : 'Reset password'}
              </button>
            </form>

            <div className="mt-6 text-center">
              <Link to="/login" className="text-[12.5px] text-muted hover:text-text">
                Back to sign in
              </Link>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
