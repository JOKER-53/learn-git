import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

export default function Admin() {
  const [users, setUsers] = useState<any[]>([]);
  const [metrics, setMetrics] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [metricsLoading, setMetricsLoading] = useState(true);
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
      
      setMetricsLoading(true);
      const mReq = await fetch('/api/admin/metrics', { credentials: 'include' });
      if (mReq.ok) {
        setMetrics(await mReq.json());
      }
      setMetricsLoading(false);
    } catch (e) {
      console.error(e);
      setLoading(false);
      setMetricsLoading(false);
    }
  };

  useEffect(() => {
    fetchAdminData();
  }, [navigate]);

  const handleStopTerminal = async (regNo: string) => {
    if (!confirm(`Stop terminal for ${regNo}?`)) return;
    try {
      const r = await fetch(`/api/admin/users/${regNo}/stop-terminal`, {
        method: 'POST',
        credentials: 'include'
      });
      if (r.ok) fetchAdminData();
    } catch(e) {}
  };

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

  if (loading) return <div className="p-8 text-center text-muted">Loading admin panel...</div>;

  let coreData: any[] = [];
  let workspaceData: any[] = [];
  let cpuData: any[] = [];
  
  if (metrics) {
    coreData = Object.entries(metrics.core_services).map(([name, d]: any) => ({
      name,
      RAM: d.mem_used_mb,
      CPU: d.cpu_percent,
    }));
    
    workspaceData = metrics.workspaces.detail.map((w: any) => ({
      name: w.reg_no,
      RAM: w.mem_used_mb,
      CPU: w.cpu_percent,
    }));
    
    cpuData = [...coreData, ...workspaceData].sort((a, b) => b.CPU - a.CPU).slice(0, 5);
  }

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-panel border border-border p-3 rounded shadow-lg text-sm">
          <p className="font-semibold text-text mb-1">{label}</p>
          {payload.map((entry: any, index: number) => (
            <p key={`item-${index}`} style={{ color: entry.color }}>
              {entry.name}: {entry.value} {entry.name === 'RAM' ? 'MB' : '%'}
            </p>
          ))}
        </div>
      );
    }
    return null;
  };

  return (
    <div className="p-8 max-w-7xl mx-auto bg-bg min-h-screen text-text font-sans overflow-auto">
      <div className="flex justify-between items-center mb-6">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold text-white tracking-tight">Admin Dashboard</h1>
          <span className="px-2 py-1 bg-panel border border-border text-xs rounded text-muted font-mono">LIVE</span>
        </div>
        <button 
          onClick={async () => {
            await fetch('/api/auth/logout', { method: 'POST' });
            navigate('/login');
          }}
          className="px-4 py-2 bg-red text-white rounded hover:opacity-90 text-sm font-semibold transition-opacity"
        >
          Sign out
        </button>
      </div>

      {metricsLoading ? (
        <div className="mb-8">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            {[1,2,3,4].map(i => (
              <div key={i} className="bg-panel border border-border p-4 rounded-md flex flex-col justify-center items-center h-24 animate-pulse">
                <div className="h-3 w-24 bg-border rounded mb-3"></div>
                <div className="h-8 w-12 bg-border rounded"></div>
              </div>
            ))}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-panel border border-border p-4 rounded-md h-80 animate-pulse"></div>
            <div className="bg-panel border border-border p-4 rounded-md h-80 animate-pulse"></div>
          </div>
        </div>
      ) : metrics && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <div className="bg-panel border border-border p-4 rounded-md flex flex-col justify-center items-center h-24">
              <div className="text-xs font-semibold text-muted uppercase tracking-wide">Total Students</div>
              <div className="text-3xl font-bold text-green">{metrics.students.total}</div>
            </div>
            <div className="bg-panel border border-border p-4 rounded-md flex flex-col justify-center items-center h-24">
              <div className="text-xs font-semibold text-muted uppercase tracking-wide">Active (1h)</div>
              <div className="text-3xl font-bold text-yellow">{metrics.students.active_last_hour}</div>
            </div>
            <div className="bg-panel border border-border p-4 rounded-md flex flex-col justify-center items-center h-24">
              <div className="text-xs font-semibold text-muted uppercase tracking-wide">Running Terminals</div>
              <div className="text-3xl font-bold text-blue">{metrics.workspaces.running}</div>
            </div>
            <div className="bg-panel border border-border p-4 rounded-md flex flex-col justify-center items-center h-24">
              <div className="text-xs font-semibold text-muted uppercase tracking-wide">Total RAM Used</div>
              <div className="text-3xl font-bold text-orange">
                {Math.round(metrics.workspaces.total_mem_used_mb + coreData.reduce((acc, c) => acc + c.RAM, 0))} <span className="text-sm font-normal text-muted">MB</span>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
            <div className="bg-panel border border-border p-4 rounded-md h-80">
              <h3 className="text-sm font-semibold text-text mb-4 font-mono">Core Services RAM (MB)</h3>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={coreData} margin={{ top: 0, right: 0, left: -20, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#30363d" vertical={false} />
                  <XAxis dataKey="name" stroke="#8b949e" tick={{ fill: '#8b949e', fontSize: 12 }} axisLine={false} tickLine={false} />
                  <YAxis stroke="#8b949e" tick={{ fill: '#8b949e', fontSize: 12 }} axisLine={false} tickLine={false} />
                  <Tooltip content={<CustomTooltip />} cursor={{ fill: '#232529' }} />
                  <Bar dataKey="RAM" fill="#58a6ff" radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="bg-panel border border-border p-4 rounded-md h-80">
              <h3 className="text-sm font-semibold text-text mb-4 font-mono">Top CPU Usage (%)</h3>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={cpuData} margin={{ top: 0, right: 0, left: -20, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#30363d" vertical={false} />
                  <XAxis dataKey="name" stroke="#8b949e" tick={{ fill: '#8b949e', fontSize: 12 }} axisLine={false} tickLine={false} />
                  <YAxis stroke="#8b949e" tick={{ fill: '#8b949e', fontSize: 12 }} axisLine={false} tickLine={false} />
                  <Tooltip content={<CustomTooltip />} cursor={{ fill: '#232529' }} />
                  <Bar dataKey="CPU" fill="#f85149" radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </>
      )}

      <div className="bg-panel border border-border rounded-md overflow-hidden">
        <div className="px-4 py-3 border-b border-border bg-bg">
          <h3 className="text-sm font-semibold text-text font-mono">User Management</h3>
        </div>
        <table className="w-full text-left text-sm">
          <thead className="bg-panel border-b border-border">
            <tr>
              <th className="px-4 py-3 font-semibold text-muted">Reg No</th>
              <th className="px-4 py-3 font-semibold text-muted">Progress</th>
              <th className="px-4 py-3 font-semibold text-muted">Last Seen</th>
              <th className="px-4 py-3 font-semibold text-muted">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border bg-panel">
            {users.map((u: any) => (
              <tr key={u.reg_no} className="hover:bg-border/30 transition-colors">
                <td className="px-4 py-3 text-text font-mono">{u.reg_no} {u.is_admin ? <span className="text-yellow ml-2 text-xs">ADMIN</span> : ''}</td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <div className="w-24 h-2 bg-border rounded-full overflow-hidden">
                      <div className="h-full bg-green" style={{ width: `${(u.completed_count / u.total_tasks) * 100}%` }}></div>
                    </div>
                    <span className="text-xs text-muted">{u.completed_count}/{u.total_tasks}</span>
                  </div>
                </td>
                <td className="px-4 py-3 text-muted text-xs">{u.last_seen || 'Never'}</td>
                <td className="px-4 py-3 space-x-3 text-xs font-semibold">
                  <button onClick={() => handleStopTerminal(u.reg_no)} className="text-orange hover:text-white transition-colors">STOP TERMINAL</button>
                  <button onClick={() => setResetModal(u.reg_no)} className="text-blue hover:text-white transition-colors">RESET PASS</button>
                  <button onClick={() => handleDelete(u.reg_no)} className="text-red hover:text-white transition-colors">DELETE</button>
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
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-50 backdrop-blur-sm">
          <div className="bg-panel border border-border rounded-md p-6 w-full max-w-sm shadow-2xl">
            <h3 className="text-lg font-bold text-white mb-2">Reset password</h3>
            <p className="text-sm text-muted mb-4">Set a new password for <strong className="text-white">{resetModal}</strong>.</p>
            <form onSubmit={handleResetPassword}>
              <input 
                type="password" 
                placeholder="New password (min 6 chars)"
                className="w-full p-2.5 bg-bg border border-border text-text rounded-md text-sm mb-2 focus:outline-none focus:border-blue"
                value={newPassword}
                onChange={e => setNewPassword(e.target.value)}
              />
              {resetError && <div className="text-red text-xs mb-4">{resetError}</div>}
              <div className="flex justify-end space-x-3 mt-4">
                <button type="button" onClick={() => setResetModal(null)} className="px-4 py-2 text-sm text-muted hover:text-white transition-colors">Cancel</button>
                <button type="submit" className="px-4 py-2 text-sm bg-blue text-white font-semibold rounded-md hover:bg-blue/80 transition-colors">Apply</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
