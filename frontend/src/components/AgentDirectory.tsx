import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { AgentRecord, createAgent, fetchAgents } from '../services/api';

const money = (n: number, currency = 'USD') => new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(n);
export function AgentDirectory() {
  const [agents, setAgents] = useState<AgentRecord[]>([]);
  const [name, setName] = useState('Research Agent');
  const [budget, setBudget] = useState('10');
  const [singleLimit, setSingleLimit] = useState('5');
  const [vendors, setVendors] = useState('mock_supplier_a, mock_supplier_b');
  const [rawKey, setRawKey] = useState('');
  const [createdAgent, setCreatedAgent] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const refresh = useCallback(async () => { try { setAgents(await fetchAgents()); setError(''); } catch (e) { setError(e instanceof Error ? e.message : 'Unable to load agents'); } finally { setLoading(false); } }, []);
  useEffect(() => { void refresh(); const timer = window.setInterval(() => void refresh(), 10000); return () => window.clearInterval(timer); }, [refresh]);

  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError(''); setRawKey('');
    try {
      const created = await createAgent({ name, budget: Number(budget), max_single_purchase: Number(singleLimit), allowed_vendors: vendors.split(',').map((v) => v.trim()).filter(Boolean) });
      setCreatedAgent(created.name); setRawKey(created.raw_api_key); await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : 'Agent provisioning failed'); }
    finally { setBusy(false); }
  };

  return <section className="space-y-5">
    <div><h2 className="text-lg font-semibold text-white">Agent Identity & Budget Control</h2><p className="mt-1 text-xs text-aeon-textMuted">Agents are provisioned through FastAPI. Provisioning creates an agent identity, a deterministic policy assignment, a scoped budget and a one-time API key.</p></div>
    <form onSubmit={submit} className="grid gap-3 rounded-xl border border-aeon-border bg-aeon-card p-5 md:grid-cols-2">
      <label className="block text-xs text-aeon-textSecondary">Agent name<input required minLength={2} value={name} onChange={(e) => setName(e.target.value)} className="mt-1 w-full rounded-md border border-aeon-border bg-aeon-bg p-2.5 text-sm text-white"/></label>
      <label className="block text-xs text-aeon-textSecondary">Allocated budget (USD)<input required min="0.01" step="0.01" type="number" value={budget} onChange={(e) => setBudget(e.target.value)} className="mt-1 w-full rounded-md border border-aeon-border bg-aeon-bg p-2.5 text-sm text-white"/></label>
      <label className="block text-xs text-aeon-textSecondary">Maximum single purchase (USD)<input required min="0.01" step="0.01" type="number" value={singleLimit} onChange={(e) => setSingleLimit(e.target.value)} className="mt-1 w-full rounded-md border border-aeon-border bg-aeon-bg p-2.5 text-sm text-white"/></label>
      <label className="block text-xs text-aeon-textSecondary">Allowed suppliers (comma-separated)<input required value={vendors} onChange={(e) => setVendors(e.target.value)} className="mt-1 w-full rounded-md border border-aeon-border bg-aeon-bg p-2.5 text-sm text-white"/></label>
      <div className="md:col-span-2"><button disabled={busy} className="rounded-md bg-cyan-500 px-4 py-2.5 text-sm font-semibold text-slate-950 disabled:opacity-50">{busy ? 'Provisioning…' : 'Create agent + policy + budget'}</button></div>
    </form>
    {error && <div role="alert" className="rounded-md border border-red-800 bg-red-950/30 p-3 text-xs text-red-300">{error}</div>}
    {rawKey && <div className="rounded-xl border border-amber-700 bg-amber-950/20 p-4"><h3 className="text-sm font-semibold text-amber-200">One-time agent API key created for {createdAgent}</h3><p className="mt-1 text-xs text-slate-300">The FastAPI backend returns this raw key only once. It is stored in this browser tab's session storage for the procurement workbench. Copy it to your secure agent configuration now; it will not be recoverable from the backend.</p><div className="mt-3 flex flex-wrap items-center gap-2"><code className="min-w-0 flex-1 break-all rounded bg-slate-950 p-3 text-xs text-emerald-200">{rawKey}</code><button onClick={() => void navigator.clipboard.writeText(rawKey)} className="rounded border border-amber-700 px-3 py-2 text-xs text-amber-200">Copy key</button><button onClick={() => setRawKey('')} className="rounded border border-aeon-border px-3 py-2 text-xs text-slate-300">Hide</button></div></div>}
    <div className="flex items-center justify-between"><h3 className="text-xs font-semibold uppercase tracking-wider text-white">Registered agents</h3><button onClick={() => void refresh()} className="rounded-md border border-aeon-border px-3 py-2 text-xs text-aeon-textSecondary">Refresh</button></div>
    {loading ? <p className="text-xs text-aeon-textMuted">Loading agent registry…</p> : agents.length === 0 ? <p className="rounded-xl border border-aeon-border bg-aeon-card p-7 text-center text-sm text-aeon-textMuted">No agents registered yet.</p> : <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{agents.map((agent) => {
      const used = Math.max(0, agent.budget - agent.remaining_budget); const pct = agent.budget > 0 ? Math.min(100, used / agent.budget * 100) : 0;
      return <article key={agent.id} className="rounded-xl border border-aeon-border bg-aeon-card p-5"><div className="flex items-start justify-between gap-3"><div><h3 className="font-semibold text-white">{agent.name}</h3><p className="mt-1 break-all font-mono text-[10px] text-aeon-textMuted">{agent.id}</p></div><span className={`rounded border px-2 py-1 text-[10px] ${agent.is_active ? 'border-emerald-700/50 bg-emerald-950/30 text-emerald-300' : 'border-red-700 bg-red-950/30 text-red-300'}`}>{agent.is_active ? 'ACTIVE' : 'INACTIVE'}</span></div><div className="mt-5 grid grid-cols-2 gap-3"><div className="rounded-lg bg-aeon-bg p-3"><p className="text-[10px] uppercase text-aeon-textMuted">Allocated</p><p className="mt-1 text-xl font-bold font-mono text-white">{money(agent.budget, agent.currency)}</p></div><div className="rounded-lg bg-aeon-bg p-3"><p className="text-[10px] uppercase text-aeon-textMuted">Available</p><p className="mt-1 text-xl font-bold font-mono text-emerald-300">{money(agent.remaining_budget, agent.currency)}</p></div></div><div className="mt-4"><div className="mb-2 flex justify-between text-[10px] text-aeon-textMuted"><span>Spent / reserved</span><span>{pct.toFixed(0)}%</span></div><div className="h-2 overflow-hidden rounded-full bg-slate-800"><div className="h-full bg-cyan-500" style={{ width: `${pct}%` }}/></div></div><div className="mt-4 border-t border-aeon-borderSubtle pt-3"><p className="text-[10px] uppercase text-aeon-textMuted">Allowed suppliers</p><div className="mt-2 flex flex-wrap gap-1.5">{agent.allowed_vendors.length ? agent.allowed_vendors.map((vendor) => <span key={vendor} className="rounded border border-aeon-border bg-aeon-bg px-2 py-1 text-[10px] text-slate-300">{vendor}</span>) : <span className="text-[10px] text-slate-500">Policy not assigned / unavailable</span>}</div><p className="mt-2 text-[10px] text-aeon-textMuted">Policy: {agent.assigned_policy_name ?? '—'}</p></div><p className="mt-4 text-[10px] text-aeon-textMuted">Registered {new Date(agent.created_at).toLocaleString()}</p></article>;
    })}</div>}
  </section>;
}
