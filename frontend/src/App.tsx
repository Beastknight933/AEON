import { useCallback, useEffect, useState } from 'react';
import type { NavigationTab, ServiceHealthResponse } from './types';
import { clearSession, fetchCurrentUser, fetchHealth, getAccessToken } from './services/api';
import { AuthScreen } from './components/AuthScreen';
import { Header } from './components/Header';
import { Sidebar } from './components/Sidebar';
import { DashboardMetrics } from './components/DashboardMetrics';
import { TransactionLedger } from './components/TransactionLedger';
import { AgentDirectory } from './components/AgentDirectory';
import { RecentActivity } from './components/RecentActivity';
import { Day2Workbench } from './components/Day2Workbench';
import { PoliciesDirectory } from './components/PoliciesDirectory';
import { PaymentReturnPanel } from './components/PaymentReturnPanel';
import { IconShield } from './components/icons';

export function App() {
  const [activeTab, setActiveTab] = useState<NavigationTab>('overview');
  const [health, setHealth] = useState<ServiceHealthResponse | null>(null);
  const [healthLoading, setHealthLoading] = useState(true);
  const [authLoading, setAuthLoading] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadHealth = useCallback(async () => {
    setHealthLoading(true); setError(null);
    try { setHealth(await fetchHealth()); }
    catch (err) { setHealth(null); setError(err instanceof Error ? err.message : 'Unable to connect to FastAPI'); }
    finally { setHealthLoading(false); }
  }, []);

  useEffect(() => {
    void loadHealth();
    const token = getAccessToken();
    if (!token) { setAuthLoading(false); return; }
    fetchCurrentUser().then(() => setAuthenticated(true)).catch(() => { clearSession(); setAuthenticated(false); }).finally(() => setAuthLoading(false));
  }, [loadHealth]);

  const onAuthenticated = () => { setAuthenticated(true); void loadHealth(); };
  const logout = () => { clearSession(); setAuthenticated(false); setActiveTab('overview'); };
  const paymentRoute = ['/payments/success', '/payments/cancel'].includes(window.location.pathname.replace(/\/$/, ''));

  if (authLoading) return <div className="flex min-h-screen items-center justify-center bg-aeon-bg text-xs text-aeon-textMuted">Checking AEON administrator session…</div>;
  if (!authenticated) return <AuthScreen onAuthenticated={onAuthenticated}/>;

  return <div className="flex h-screen w-screen overflow-hidden bg-aeon-bg text-slate-100 font-sans">
    <Sidebar activeTab={activeTab} onTabChange={setActiveTab} health={health} loading={healthLoading}/>
    <div className="flex-1 flex flex-col overflow-hidden">
      <Header health={health} loading={healthLoading} onRefresh={loadHealth} onLogout={logout}/>
      <main className="flex-1 overflow-y-auto p-6 space-y-6">
        {error && <div className="rounded-lg border border-red-800 bg-red-950/40 p-3 text-xs text-red-300 flex items-center justify-between"><span>Backend connection warning: {error}</span><button onClick={loadHealth} className="rounded border border-red-700 px-2.5 py-1 text-white">Retry</button></div>}
        {paymentRoute ? <PaymentReturnPanel/> : activeTab === 'transactions' ? <TransactionLedger mode="transactions"/> : activeTab === 'audit' ? <TransactionLedger mode="audit"/> : activeTab === 'agents' ? <AgentDirectory/> : activeTab === 'procurement' ? <Day2Workbench/> : activeTab === 'policies' ? <PoliciesDirectory/> : <div className="space-y-6">
          <div className="rounded-xl border border-aeon-border bg-aeon-card p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3"><div className="flex items-center gap-3"><div className="rounded-lg border border-aeon-border bg-aeon-surface p-2 text-aeon-cyan"><IconShield className="h-4 w-4"/></div><div><h2 className="text-xs font-bold uppercase tracking-wider text-white font-mono">AEON · FastAPI + PostgreSQL Control Plane</h2><p className="mt-0.5 text-[11px] text-aeon-textMuted">AI recommends. Deterministic policy authorizes. PayPal executes. The backend ledger is authoritative.</p></div></div><span className="rounded border border-emerald-700/50 bg-emerald-950/30 px-2 py-1 text-[10px] font-mono text-emerald-300">Authenticated dashboard</span></div>
          <DashboardMetrics/>
          <Day2Workbench/>
          <RecentActivity/>
        </div>}
      </main>
    </div>
  </div>;
}
