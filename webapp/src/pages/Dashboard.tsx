import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';

interface Task {
  id: string;
  tier: string;
  title: string;
  description: string;
  hint: string;
  completed: boolean;
  unlocked: boolean;
}

interface User {
  reg_no: string;
  terminal_path?: string;
}

export default function Dashboard() {
  const [user, setUser] = useState<User | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [panelWidth, setPanelWidth] = useState(400); // Default left panel width
  const [checking, setChecking] = useState<Record<string, 'checking' | 'failed'>>({});
  const [openHints, setOpenHints] = useState<Record<string, boolean>>({});
  
  const navigate = useNavigate();
  const isDragging = useRef(false);

  const fetchTasks = async () => {
    try {
      const r = await fetch('/api/tasks', { credentials: 'include' });
      if (r.status === 401) {
        navigate('/login');
        return;
      }
      const data = await r.json();
      setTasks(data);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    const auth = async () => {
      try {
        const r = await fetch('/api/auth/me', { credentials: 'include' });
        if (!r.ok) {
          navigate('/login');
          return;
        }
        const me = await r.json();
        setUser(me);
        await fetchTasks();
        setLoading(false);
      } catch (e) {
        navigate('/login');
      }
    };
    auth();
  }, [navigate]);

  const handleLogout = async () => {
    await fetch('/api/auth/logout', { method: 'POST' });
    navigate('/login');
  };

  const checkTask = async (taskId: string) => {
    setChecking(prev => ({ ...prev, [taskId]: 'checking' }));
    try {
      const r = await fetch(`/api/tasks/${taskId}/check`, { method: 'POST' });
      const d = await r.json();
      if (d.passed) {
        await fetchTasks();
        setChecking(prev => {
          const next = { ...prev };
          delete next[taskId];
          return next;
        });
      } else {
        setChecking(prev => ({ ...prev, [taskId]: 'failed' }));
      }
    } catch (e) {
      setChecking(prev => ({ ...prev, [taskId]: 'failed' }));
    }
  };

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isDragging.current) return;
      setPanelWidth(Math.max(250, e.clientX));
    };

    const handleMouseUp = () => {
      if (isDragging.current) {
        isDragging.current = false;
        document.body.style.cursor = '';
        const iframe = document.getElementById('terminal-iframe');
        if (iframe) iframe.style.pointerEvents = 'auto';
      }
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, []);

  if (loading) return null;

  const done = tasks.filter(t => t.completed).length;
  const progressPercent = tasks.length ? (done / tasks.length) * 100 : 0;
  
  const tasksByTier = tasks.reduce((acc, t) => {
    acc[t.tier] = acc[t.tier] || [];
    acc[t.tier].push(t);
    return acc;
  }, {} as Record<string, Task[]>);

  const TIERS = ["beginner", "intermediate", "advanced", "expert"];

  const formatText = (text: string) => {
    if (!text) return text;
    const parts = text.split(/`([^`]+)`/g);
    return parts.map((part, i) => 
      i % 2 === 1 ? <code key={i} className="bg-[#1c2129] border border-border px-1.5 py-[1px] rounded text-[11.5px] text-[#e6edf3]">{part}</code> : part
    );
  };

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <header className="shrink-0 px-6 py-3 border-b border-border flex items-center justify-between bg-bg/95 backdrop-blur">
        <h1 className="text-[17px] font-semibold m-0">learn<span className="text-green">-git</span></h1>
        <div className="flex items-center gap-5">
          <div className="flex items-center gap-2.5 min-w-[180px]">
            <div className="flex-1 h-[7px] bg-border rounded-full overflow-hidden">
              <div 
                className="h-full bg-gradient-to-r from-green to-[#3fb950] transition-all duration-400" 
                style={{ width: `${progressPercent}%` }}
              />
            </div>
            <span className="text-xs text-muted whitespace-nowrap">{done} / {tasks.length}</span>
          </div>
          <div className="text-[13px] text-muted">
            {user?.reg_no} <button onClick={handleLogout} className="text-red hover:underline ml-2.5 cursor-pointer bg-transparent border-none p-0">Sign out</button>
          </div>
        </div>
      </header>

      <div className="flex flex-1 min-h-0 overflow-hidden">
        <div 
          className="overflow-y-auto px-4 pt-3.5 pb-8 shrink-0" 
          style={{ width: `${panelWidth}px`, flexBasis: `${panelWidth}px` }}
        >
          {TIERS.map(tier => {
            if (!tasksByTier[tier]) return null;
            return (
              <div key={tier}>
                <div className="flex items-center gap-2 mt-5 mb-2.5 text-[11px] uppercase tracking-wider text-muted after:content-[''] after:flex-1 after:h-[1px] after:bg-border">
                  <span className={`w-[7px] h-[7px] rounded-full ${
                    tier === 'beginner' ? 'bg-green' : 
                    tier === 'intermediate' ? 'bg-blue' : 
                    tier === 'advanced' ? 'bg-purple' : 'bg-orange'
                  }`} />
                  {tier}
                </div>
                {tasksByTier[tier].map(t => {
                  const checkStatus = checking[t.id];
                  
                  return (
                    <div 
                      key={t.id} 
                      className={`border border-border bg-panel rounded-lg p-3.5 mb-2 transition-all duration-200 ${
                        !t.unlocked ? 'opacity-40 grayscale-[0.4]' : 
                        t.completed ? 'border-green bg-gradient-to-b from-green-dim to-panel' : 'hover:border-[#444c56]'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-[3px]">
                        <span className="text-[10px] uppercase text-muted tracking-wide">{t.tier}</span>
                        {t.completed && <span className="text-[11px] text-green font-semibold">✓ complete</span>}
                      </div>
                      <div className="text-sm font-semibold mb-1.5">{t.title}</div>
                      <div className="text-[12.5px] text-muted leading-relaxed">
                        {formatText(t.description)}
                      </div>
                      
                      {t.hint && openHints[t.id] && (
                        <div className="mt-2 px-2.5 py-2 bg-[#1a1500] border border-[#3d3000] rounded-md text-xs text-yellow leading-relaxed">
                          {formatText(t.hint)}
                        </div>
                      )}

                      {t.unlocked && !t.completed && (
                        <div className="flex items-center gap-2 mt-2.5">
                          <button 
                            onClick={() => checkTask(t.id)}
                            disabled={checkStatus === 'checking'}
                            className={`px-3.5 py-1.5 rounded-md text-[12.5px] font-semibold text-white transition-colors ${
                              checkStatus === 'checking' ? 'bg-border text-muted cursor-not-allowed' :
                              checkStatus === 'failed' ? 'bg-red hover:bg-red/90' : 'bg-green hover:bg-[#2fb84f]'
                            }`}
                          >
                            {checkStatus === 'checking' ? 'Checking...' :
                             checkStatus === 'failed' ? 'Not yet — try again' : 'Check progress'}
                          </button>
                          {t.hint && (
                            <button 
                              onClick={() => setOpenHints(prev => ({ ...prev, [t.id]: !prev[t.id] }))}
                              className="px-2.5 py-1.5 bg-transparent border border-[#3d3000] text-yellow rounded-md cursor-pointer text-[11.5px] hover:bg-[#1a1500]"
                            >
                              {openHints[t.id] ? 'Hide' : '💡 Hint'}
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
        
        <div 
          className="w-[6px] bg-bg border-r border-border cursor-col-resize shrink-0 transition-colors hover:bg-blue active:bg-blue"
          onMouseDown={() => {
            isDragging.current = true;
            document.body.style.cursor = 'col-resize';
            const iframe = document.getElementById('terminal-iframe');
            if (iframe) iframe.style.pointerEvents = 'none';
          }}
        />

        <div className="flex-1 flex flex-col min-h-0 bg-black">
          <div className="shrink-0 px-3.5 py-2 border-b border-border bg-panel flex justify-between items-center">
            <span className="text-xs text-muted">your terminal</span>
            {user?.terminal_path && (
              <a href={user.terminal_path} target="_blank" rel="noreferrer" className="text-xs text-blue no-underline">
                open full screen ↗
              </a>
            )}
          </div>
          <div className="shrink-0 px-3.5 py-[7px] bg-[#140d00] border-b border-[#5a3a00] text-xs text-[#c98a2e] leading-relaxed">
            ⚠ <strong className="text-orange">Always work inside </strong><code className="bg-[#1f1400] border border-[#5a3a00] px-1.5 py-[1px] rounded text-orange text-[11.5px]">/data/repo</code>
            — the platform checks only that folder. All remote tasks use the <strong className="text-orange">built-in git-server</strong> — no internet needed.
          </div>
          <iframe 
            id="terminal-iframe" 
            src={user?.terminal_path || 'about:blank'} 
            title="terminal"
            className="flex-1 border-none w-full min-h-0 bg-black"
          />
        </div>
      </div>
    </div>
  );
}
