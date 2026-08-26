import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

export default function Admin() {
  const [users, setUsers] = useState<any[]>([]);
  const [metrics, setMetrics] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [resetModal, setResetModal] = useState<string | null>(null);
  const [newPassword, setNewPassword] = useState('');
  const [resetError, setResetError] = useState('');
  const navigate = useNavigate();

  const fetchAdminData = async () => {
    try {
      const r = await fetch('/api/admin/users', { credentials: 'include' });
      if (r.status === 401 || r.status === 403) {
        navigate('/login');
        return;
      }
      const data = await r.json();
      setUsers(data);
      setLoading(false);
      
      const mReq = await fetch('/api/admin/metrics', { credentials: 'include' });
      if (mReq.ok) {
        setMetrics(await mReq.json());
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchAdminData();
  }, [navigate]);

  const handleDelete = async (regNo: string) => {
    if (!confirm(`Are you sure you want to delete ${regNo}? This cannot be undone.`)) return;
    try {
      const r = await fetch(`/api/admin/users/${regNo}`, { 
        method: 'DELETE',
        credentials: 'include'
      });
      if (r.ok) {
        fetchAdminData();
      } else {
        const err = await r.json();
        alert(err.detail?.error || err.error || 'Failed to delete user');
      }
    } catch (e) {
      alert('Error deleting user');
    }
  };

  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPassword.length < 6) {
      setResetError("Password must be at least 6 characters.");
      return;
    }
    setResetError('');
    try {
      const r = await fetch(`/api/admin/users/${resetModal}/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ new_password: newPassword })
      });
      if (r.ok) {
        const data = await r.json();
        alert(`Password reset successful!\nNew recovery code: ${data.new_recovery_code}\nSAVE THIS CODE!`);
        setResetModal(null);
        setNewPassword('');
      } else {
        const err = await r.json();
        setResetError(err.detail?.error || err.error || 'Failed to reset password');
      }
    } catch (err) {
      setResetError('Error resetting password');
    }
  };

  if (loading) return <div className="p-8 text-center">Loading admin panel...</div>;

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Admin Dashboard</h1>
        <button 
          onClick={async () => {
            await fetch('/api/auth/logout', { method: 'POST' });
            navigate('/login');
          }}
          className="px-4 py-2 bg-border rounded-md hover:bg-border/80"
        >
          Sign out
        </button>
      </div>

      {metrics && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
          <div className="bg-panel p-4 rounded-lg border border-border">
            <h3 className="text-sm font-semibold text-muted uppercase tracking-wider mb-2">Students</h3>
            <p className="text-2xl">{metrics.students.total}</p>
            <p className="text-xs text-muted mt-1">{metrics.students.active_last_hour} active last hour</p>
          </div>
          <div className="bg-panel p-4 rounded-lg border border-border">
            <h3 className="text-sm font-semibold text-muted uppercase tracking-wider mb-2">Workspaces</h3>
            <p className="text-2xl">{metrics.workspaces.running} <span className="text-sm text-muted font-normal">/ {metrics.workspaces.total_ever_created} total</span></p>
            <p className="text-xs text-muted mt-1">{metrics.workspaces.total_mem_used_mb}MB / {metrics.workspaces.total_mem_cap_mb}MB RAM</p>
          </div>
          <div className="bg-panel p-4 rounded-lg border border-border">
            <h3 className="text-sm font-semibold text-muted uppercase tracking-wider mb-2">System</h3>
            <p className="text-sm text-muted mt-1">Idle timeout: {metrics.idle_workspace_hours}h</p>
          </div>
        </div>
      )}

      <div className="bg-panel rounded-lg border border-border overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="bg-[#161b22] border-b border-border">
            <tr>
              <th className="px-4 py-3 font-semibold text-muted">Reg No</th>
              <th className="px-4 py-3 font-semibold text-muted">Progress</th>
              <th className="px-4 py-3 font-semibold text-muted">Last Seen</th>
              <th className="px-4 py-3 font-semibold text-muted">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {users.map((u: any) => (
              <tr key={u.reg_no} className="hover:bg-bg/50">
                <td className="px-4 py-3">{u.reg_no} {u.is_admin ? '(Admin)' : ''}</td>
                <td className="px-4 py-3">{u.completed_count} / {u.total_tasks}</td>
                <td className="px-4 py-3 text-muted">{u.last_seen || 'Never'}</td>
                <td className="px-4 py-3 space-x-2">
                  <button onClick={() => setResetModal(u.reg_no)} className="text-yellow hover:underline">Reset Pass</button>
                  <button onClick={() => handleDelete(u.reg_no)} className="text-red hover:underline">Delete</button>
                </td>
              </tr>
            ))}
            {users.length === 0 && (
              <tr><td colSpan={4} className="px-4 py-8 text-center text-muted">No users found</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {resetModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className="bg-panel border border-border rounded-xl p-6 w-full max-w-sm">
            <h3 className="text-lg font-bold mb-2">Reset password</h3>
            <p className="text-sm text-muted mb-4">Set a new password for <strong>{resetModal}</strong>.</p>
            <form onSubmit={handleResetPassword}>
              <input 
                type="password" 
                placeholder="New password (min 6 chars)"
                className="w-full p-2.5 bg-bg border border-border rounded-md text-sm mb-2 focus:outline-none focus:border-green"
                value={newPassword}
                onChange={e => setNewPassword(e.target.value)}
              />
              {resetError && <div className="text-red text-xs mb-4">{resetError}</div>}
              <div className="flex justify-end space-x-3 mt-4">
                <button type="button" onClick={() => setResetModal(null)} className="px-4 py-2 text-sm text-muted hover:text-white">Cancel</button>
                <button type="submit" className="px-4 py-2 text-sm bg-yellow text-[#1c1500] font-semibold rounded-md">Reset password</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
