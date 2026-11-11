import { FormEvent, useEffect, useState } from 'react';
import { AgentRecord, approvePurchase, createPayPalOrder, fetchAgents, PurchaseResult, submitPurchase } from '../services/api';

export function Day2Workbench() {
  const [agents, setAgents] = useState<AgentRecord[]>([]);
  const [agentId, setAgentId] = useState('');
  const [amount, setAmount] = useState('4');
  const [description, setDescription] = useState('Standard cloud API data package');
  const [category, setCategory] = useState('compute');
  const [result, setResult] = useState<PurchaseResult | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [checkoutMessage, setCheckoutMessage] = useState('');

  const refreshAgents = async () => {
    try { const rows = await fetchAgents(); setAgents(rows); if (!agentId && rows.length) setAgentId(rows[0].id); }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not load agents'); }
  };
  useEffect(() => { void refreshAgents(); }, []);

  const purchase = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError(''); setResult(null); setCheckoutMessage('');
    try {
      const response = await submitPurchase({ agent_id: agentId, amount: Number(amount), item_description: description, category });
      setResult(response); await refreshAgents();
    } catch (e) { setError(e instanceof Error ? e.message : 'Purchase request failed'); }
    finally { setBusy(false); }
  };

  const approveAndPay = async () => {
    if (!result || result.decision === 'BLOCKED') return;
    setBusy(true); setError(''); setCheckoutMessage('Submitting human approval, if required by policy…');
    try {
      await approvePurchase(result.transaction.id);
      setCheckoutMessage('Creating PayPal Orders v2 checkout…');
      const order = await createPayPalOrder(result.transaction.id);
      setCheckoutMessage(`PayPal order ${order.orderID} created. Redirecting to Sandbox…`);
      window.location.assign(order.approvalUrl);
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not start PayPal checkout'); setCheckoutMessage(''); }
    finally { setBusy(false); }
  };

  return <section className="space-y-5">
    <div className="flex items-center justify-between"><div><h2 className="text-lg font-semibold text-white">Procurement workbench</h2><p className="text-xs text-slate-400">FastAPI agent authentication, server-side quote collection, deterministic policy evaluation and PayPal Orders v2.</p></div><button onClick={() => void refreshAgents()} className="rounded-md border border-slate-700 px-3 py-2 text-xs text-slate-300">Refresh agents</button></div>
    {error && <div role="alert" className="rounded-lg border border-red-800 bg-red-950/40 p-3 text-sm text-red-300">{error}</div>}
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
      <div className="space-y-3 rounded-xl border border-slate-700 bg-slate-900/70 p-5">
        <h3 className="font-semibold text-white">Procurement request</h3>
        <p className="text-xs leading-5 text-slate-400">The authenticated agent API key is used server-side by this browser session. The Python procurement service collects quotes and runs its policy engine; the browser does not choose or authorize a supplier.</p>
        <form onSubmit={purchase} className="space-y-3">
          <label className="block text-xs text-slate-400">Agent<select required value={agentId} onChange={(e) => setAgentId(e.target.value)} className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 p-2.5 text-sm text-white"><option value="">Select an agent</option>{agents.map((a) => <option key={a.id} value={a.id}>{a.name} · ${a.remaining_budget.toFixed(2)} available</option>)}</select></label>
          <label className="block text-xs text-slate-400">Service / item description<input required minLength={2} maxLength={255} value={description} onChange={(e) => setDescription(e.target.value)} className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 p-2.5 text-sm text-white"/></label>
          <div className="grid grid-cols-2 gap-3"><label className="block text-xs text-slate-400">Category<input required minLength={2} value={category} onChange={(e) => setCategory(e.target.value)} className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 p-2.5 text-sm text-white"/></label><label className="block text-xs text-slate-400">Maximum budget (USD)<input required min="0.01" step="0.01" type="number" value={amount} onChange={(e) => setAmount(e.target.value)} className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 p-2.5 text-sm text-white"/></label></div>
          <button disabled={busy || !agents.length || !agentId} className="rounded-md bg-cyan-500 px-4 py-2.5 text-sm font-semibold text-slate-950 disabled:opacity-50">{busy ? 'Processing…' : 'Submit procurement request'}</button>
        </form>
      </div>
      <div className="space-y-3 rounded-xl border border-slate-700 bg-slate-900/70 p-5">
        <h3 className="font-semibold text-white">Procurement decision</h3>
        {!result ? <div className="rounded-lg border border-dashed border-slate-700 p-8 text-center text-xs text-slate-500">Submit a request to view quotes, recommendation and deterministic policy decision.</div> : <div role="status" className={`rounded-lg border p-4 ${result.decision === 'BLOCKED' ? 'border-red-700 bg-red-950/40' : 'border-emerald-700 bg-emerald-950/30'}`}>
          <div className={`text-sm font-bold tracking-wide ${result.decision === 'BLOCKED' ? 'text-red-300' : 'text-emerald-300'}`}>{result.decision === 'BLOCKED' ? 'BLOCKED BY POLICY' : result.decision === 'REQUIRES_APPROVAL' ? 'REQUIRES HUMAN APPROVAL' : 'POLICY AUTHORIZED'}</div>
          <p className="mt-1 text-sm text-slate-200">{result.message}</p><p className="mt-2 break-all text-[11px] text-slate-400">Purchase request: {result.transaction.id}</p>
          <div className="mt-4"><h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Backend supplier quote comparison</h4><div className="overflow-x-auto"><table className="w-full text-left text-xs"><thead className="text-slate-500"><tr><th className="py-2">Supplier</th><th>Price</th><th>Delivery</th><th>Currency</th></tr></thead><tbody>{result.quotes.map((q) => <tr key={q.id} className="border-t border-slate-800 text-slate-200"><td className="py-2">{q.provider}</td><td>{q.price.toFixed(2)}</td><td>{q.delivery_latency_hours ? `${q.delivery_latency_hours / 24} days` : '—'}</td><td>{q.currency}</td></tr>)}</tbody></table></div></div>
          {result.recommendation && <div className="mt-4 rounded-lg border border-cyan-900 bg-slate-950/60 p-3"><div className="flex flex-wrap items-center justify-between gap-2"><h4 className="text-sm font-semibold text-cyan-200">Procurement recommendation</h4><span className="rounded bg-slate-800 px-2 py-1 text-[10px] uppercase text-slate-400">{result.recommendation.source}</span></div><p className="mt-2 text-sm text-white">{result.recommendation.recommended_vendor} · ${result.recommendation.price.toFixed(2)}</p><ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-slate-300">{result.recommendation.rationale.map((line, i) => <li key={i}>{line}</li>)}</ul></div>}
          {result.decision !== 'BLOCKED' && <button type="button" disabled={busy} onClick={() => void approveAndPay()} className="mt-4 w-full rounded-md bg-[#0070ba] px-4 py-3 text-sm font-semibold text-white disabled:opacity-50">{busy ? 'Starting checkout…' : 'Human Review & Continue to PayPal'}</button>}
          {checkoutMessage && <p className="mt-3 text-xs text-cyan-200" role="status">{checkoutMessage}</p>}
        </div>}
      </div>
    </div>
  </section>;
}
