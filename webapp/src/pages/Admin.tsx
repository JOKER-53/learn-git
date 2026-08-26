import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

export default function Admin() {
  const [users, setUsers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
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
      } catch (e) {
        console.error(e);
      }
    };
    fetchAdminData();
  }, [navigate]);

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

      <div className="bg-panel rounded-lg border border-border overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="bg-[#161b22] border-b border-border">
            <tr>
              <th className="px-4 py-3 font-semibold text-muted">Reg No</th>
              <th className="px-4 py-3 font-semibold text-muted">Progress</th>
              <th className="px-4 py-3 font-semibold text-muted">Last Seen</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {users.map((u: any) => (
              <tr key={u.reg_no} className="hover:bg-bg/50">
                <td className="px-4 py-3">{u.reg_no} {u.is_admin ? '(Admin)' : ''}</td>
                <td className="px-4 py-3">{u.completed_count} / {u.total_tasks}</td>
                <td className="px-4 py-3 text-muted">{u.last_seen || 'Never'}</td>
              </tr>
            ))}
            {users.length === 0 && (
              <tr><td colSpan={3} className="px-4 py-8 text-center text-muted">No users found</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
