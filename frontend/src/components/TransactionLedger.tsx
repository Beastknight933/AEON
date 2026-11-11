import { useCallback, useEffect, useMemo, useState } from 'react';
import { AgGridReact } from 'ag-grid-react';
import { AllCommunityModule, ColDef, ModuleRegistry, themeQuartz } from 'ag-grid-community';
import { AgentRecord, AuditEvent, fetchAgents, fetchAuditEvents, fetchTransactions, LedgerTransaction, LedgerSummary } from '../services/api';
ModuleRegistry.registerModules([AllCommunityModule]);
type LedgerMode = 'transactions' | 'audit';
const gridTheme = themeQuartz.withParams({ backgroundColor: '#0b1220', foregroundColor: '#e2e8f0', headerBackgroundColor: '#111c2e', borderColor: '#26364d', rowHoverColor: '#14253a', fontSize: 12 });
const money = (value: number | null | undefined, currency = 'USD') => value === null || value === undefined ? '—' : new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(value);
function Metric({ label, value, detail }: { label: string; value: string | number; detail: string }) { return <div className="rounded-xl border border-aeon-border bg-aeon-card p-4"><p className="text-[10px] uppercase tracking-wider font-mono text-aeon-textMuted">{label}</p><p className="mt-2 text-2xl font-bold font-mono text-white">{value}</p><p className="mt-1 text-[10px] text-aeon-textMuted">{detail}</p></div>; }

export function TransactionLedger({ mode }: { mode: LedgerMode }) {
  const [transactions, setTransactions] = useState<LedgerTransaction[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [agents, setAgents] = useState<AgentRecord[]>([]);
  const [summary, setSummary] = useState<LedgerSummary>({ total: 0, pending: 0, blocked: 0, completed: 0, failed: 0, completed_amount: 0 });
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [agentFilter, setAgentFilter] = useState('ALL');
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<LedgerTransaction | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const refresh = useCallback(async () => {
    try {
      const [ledger, agentRows, audit] = await Promise.all([fetchTransactions(), fetchAgents(), fetchAuditEvents()]);
      setTransactions(ledger.data); setSummary(ledger.summary); setAgents(agentRows); setAuditEvents(audit.data); setError('');
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to load ledger'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void refresh(); const timer = window.setInterval(() => void refresh(), 8000); return () => window.clearInterval(timer); }, [refresh]);
  const visibleTransactions = useMemo(() => transactions.filter((row) => (statusFilter === 'ALL' || row.status === statusFilter) && (agentFilter === 'ALL' || row.agent_id === agentFilter) && (!search || [row.id, row.agent_name, row.vendor, row.status, row.item_description, row.paypal_order_id, row.paypal_capture_id].some((v) => String(v ?? '').toLowerCase().includes(search.toLowerCase())))), [transactions, statusFilter, agentFilter, search]);
  const transactionColumns = useMemo<ColDef<LedgerTransaction>[]>(() => [
    { field: 'created_at', headerName: 'Created At', minWidth: 170, valueFormatter: (p) => p.value ? new Date(p.value).toLocaleString() : '—' },
    { field: 'agent_name', headerName: 'Agent', minWidth: 150 },
    { field: 'vendor', headerName: 'Supplier', minWidth: 150 },
    { field: 'item_description', headerName: 'Requested Item', minWidth: 210, flex: 1 },
    { field: 'amount', headerName: 'Amount', minWidth: 110, valueFormatter: (p) => money(Number(p.value), p.data?.currency) },
    { field: 'status', headerName: 'Ledger Status', minWidth: 135 },
    { field: 'policy_decision', headerName: 'Purchase State', minWidth: 145 },
    { field: 'paypal_order_id', headerName: 'PayPal Order ID', minWidth: 180 },
    { field: 'paypal_capture_id', headerName: 'Capture / Provider ID', minWidth: 190 },
    { field: 'remaining_budget', headerName: 'Budget Available', minWidth: 140, valueFormatter: (p) => money(p.value, p.data?.currency) },
  ], []);
  const auditColumns = useMemo<ColDef<AuditEvent>[]>(() => [
    { field: 'timestamp', headerName: 'Timestamp', minWidth: 180, valueFormatter: (p) => p.value ? new Date(p.value).toLocaleString() : '—' },
    { field: 'event', headerName: 'Action', minWidth: 190 },
    { field: 'agent_name', headerName: 'Actor', minWidth: 130 },
    { field: 'detail', headerName: 'Event Metadata', minWidth: 360, flex: 1 },
    { field: 'status', headerName: 'Status', minWidth: 120 },
    { field: 'transaction_id', headerName: 'Entity ID', minWidth: 220 },
  ], []);
  const displayedEvents = useMemo(() => auditEvents.filter((row) => (agentFilter === 'ALL' || row.agent_id === agentFilter || !row.agent_id) && (!search || [row.event, row.detail, row.agent_name, row.transaction_id].some((v) => String(v ?? '').toLowerCase().includes(search.toLowerCase())))), [auditEvents, agentFilter, search]);

  return <div className="space-y-5">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-lg font-semibold text-white">{mode === 'transactions' ? 'Financial Transaction Ledger' : 'Immutable Audit Trail'}</h2><p className="mt-1 text-xs text-aeon-textMuted">Live data from FastAPI, PostgreSQL ledger and append-only audit APIs. Refreshes every 8 seconds.</p></div><button onClick={() => void refresh()} disabled={loading} className="rounded-md border border-aeon-border px-3 py-2 text-xs text-aeon-textSecondary">{loading ? 'Refreshing…' : 'Refresh'}</button></div>
    {error && <div role="alert" className="rounded-lg border border-red-800 bg-red-950/40 p-3 text-xs text-red-300">{error}</div>}
    {mode === 'transactions' && <div className="grid grid-cols-2 gap-3 xl:grid-cols-5"><Metric label="Transactions" value={summary.total} detail="Paginated financial ledger"/><Metric label="Pending" value={summary.pending} detail="Unsettled / in-flight"/><Metric label="Blocked" value={summary.blocked} detail="Purchase requests denied"/><Metric label="Settled" value={summary.completed} detail="Completed captures"/><Metric label="Net captured" value={money(summary.completed_amount)} detail={`${summary.failed} failed / cancelled`}/></div>}
    <section className="rounded-xl border border-aeon-border bg-aeon-card p-4"><div className="mb-4 flex flex-wrap gap-3"><input aria-label="Search ledger" placeholder="Search agent, supplier, description or PayPal ID…" value={search} onChange={(e) => setSearch(e.target.value)} className="min-w-[230px] flex-1 rounded-md border border-aeon-border bg-aeon-bg px-3 py-2 text-xs text-white"/>{mode === 'transactions' && <select aria-label="Filter by status" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="rounded-md border border-aeon-border bg-aeon-bg px-3 py-2 text-xs text-white"><option value="ALL">All statuses</option>{['SETTLED','PENDING','FAILED','REFUNDED'].map((status) => <option key={status}>{status}</option>)}</select>}<select aria-label="Filter by agent" value={agentFilter} onChange={(e) => setAgentFilter(e.target.value)} className="rounded-md border border-aeon-border bg-aeon-bg px-3 py-2 text-xs text-white"><option value="ALL">All agents</option>{agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}</select></div>
      <div className="ag-theme-quartz-dark w-full" style={{ height: 480 }}>{mode === 'transactions' ? <AgGridReact<LedgerTransaction> theme={gridTheme} rowData={visibleTransactions} columnDefs={transactionColumns} defaultColDef={{ sortable: true, filter: true, resizable: true, floatingFilter: true }} pagination paginationPageSize={10} animateRows onRowClicked={(event) => setSelected(event.data ?? null)} getRowId={(params) => params.data.id}/> : <AgGridReact<AuditEvent> theme={gridTheme} rowData={displayedEvents} columnDefs={auditColumns} defaultColDef={{ sortable: true, filter: true, resizable: true, floatingFilter: true }} pagination paginationPageSize={12} animateRows getRowId={(params) => params.data.id}/>}</div>
      <p className="mt-3 text-[10px] text-aeon-textMuted font-mono">{mode === 'transactions' ? `Showing ${visibleTransactions.length} of ${summary.total} ledger transactions` : `Showing ${displayedEvents.length} audit events`}</p>
    </section>
    {mode === 'transactions' && <section className="rounded-xl border border-aeon-border bg-aeon-card p-4"><h3 className="text-xs font-semibold uppercase tracking-wider text-white font-mono">Agent budget position</h3><p className="mt-1 text-[11px] text-aeon-textMuted">Balances come from server-side budget records. Active reservations remain unavailable until settlement or release.</p><div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{agents.map((agent) => { const used = Math.max(0, agent.budget - agent.remaining_budget); const pct = agent.budget > 0 ? Math.min(100, used / agent.budget * 100) : 0; return <div key={agent.id} className="rounded-lg border border-aeon-borderSubtle bg-aeon-bg p-3"><div className="flex justify-between gap-2 text-xs"><span className="font-semibold text-white">{agent.name}</span><span className="font-mono text-cyan-300">{money(agent.remaining_budget, agent.currency)} available</span></div><div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-800"><div className="h-full rounded-full bg-cyan-500" style={{ width: `${pct}%` }}/></div><div className="mt-2 flex justify-between text-[10px] text-aeon-textMuted"><span>Allocated {money(agent.budget, agent.currency)}</span><span>Used / reserved {money(used, agent.currency)}</span></div></div>; })}</div></section>}
    {selected && mode === 'transactions' && <section className="rounded-xl border border-aeon-border bg-aeon-card p-4"><h3 className="text-xs font-semibold uppercase tracking-wider text-white font-mono">Selected ledger record</h3><p className="mt-1 break-all font-mono text-[10px] text-aeon-textMuted">{selected.id}</p><div className="mt-3 grid gap-2 text-xs sm:grid-cols-2"><p className="text-slate-300">Purchase request: <span className="font-mono text-white">{selected.purchase_request_id}</span></p><p className="text-slate-300">Status: <span className="font-semibold text-cyan-200">{selected.status}</span></p><p className="text-slate-300">Supplier: {selected.vendor}</p><p className="text-slate-300">Amount: {money(selected.amount, selected.currency)}</p><p className="text-slate-300">PayPal order: {selected.paypal_order_id ?? 'Not available'}</p><p className="text-slate-300">Capture / provider ID: {selected.paypal_capture_id ?? 'Not available'}</p></div></section>}
  </div>;
}
