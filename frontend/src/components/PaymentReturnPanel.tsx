import { useEffect, useState } from 'react';
import { capturePayPalOrder, fetchPayPalStatus, reconcilePayPalOrder } from '../services/api';

export function PaymentReturnPanel() {
  const successRoute = window.location.pathname.replace(/\/$/, '') === '/payments/success';
  const cancelRoute = window.location.pathname.replace(/\/$/, '') === '/payments/cancel';
  const params = new URLSearchParams(window.location.search);
  const orderId = params.get('token') || params.get('order_id');
  const [payment, setPayment] = useState<any>(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!successRoute || !orderId) return;
    let active = true;
    let timer: number | undefined;
    const refresh = async () => {
      try {
        const next = await fetchPayPalStatus(orderId);
        if (!active) return;
        setPayment(next); setError('');
        if (!['COMPLETED', 'FAILED', 'CANCELLED', 'VOIDED'].includes(next.status)) {
          timer = window.setTimeout(refresh, 4000);
        }
      } catch (e) {
        if (active) { setError(e instanceof Error ? e.message : 'Unable to retrieve payment status'); timer = window.setTimeout(refresh, 5000); }
      }
    };
    const capture = async () => {
      try {
        // Read the persisted attempt before capturing. A browser refresh must not blindly re-submit a capture.
        const prior = await fetchPayPalStatus(orderId);
        if (!active) return;
        setPayment(prior);
        if (prior.status === 'COMPLETED') { setMessage('PayPal already reports a completed capture.'); return; }
        if (prior.status === 'CAPTURE_PENDING') {
          setMessage('PayPal capture is already pending review. AEON will retain the budget reservation and will not send another capture request.');
          return;
        }
        if (!['ORDER_CREATED', 'BUYER_APPROVAL_PENDING'].includes(prior.status)) {
          setMessage(`Payment attempt is currently ${prior.status}. No new capture request was submitted.`);
          return;
        }
        setMessage('PayPal buyer approval returned. AEON is requesting server-side capture…');
        try {
          const result = await capturePayPalOrder(orderId);
          if (!active) return;
          setPayment(result); setMessage('Capture request returned. Refreshing the authoritative payment status…');
        } catch (e) {
          if (!active) return;
          // Capture may legitimately remain CAPTURE_PENDING / PENDING_REVIEW. Query the server status; never assume the redirect means paid.
          setMessage('Capture is not confirmed yet. AEON is checking PayPal payment status; reserved funds remain protected.');
          setError(e instanceof Error ? e.message : 'Capture is pending or failed');
        }
        await refresh();
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : 'Unable to inspect payment attempt before capture');
      }
    };
    void capture();
    return () => { active = false; if (timer !== undefined) window.clearTimeout(timer); };
  }, [successRoute, orderId]);

  if (!successRoute && !cancelRoute) return null;
  if (cancelRoute) return <section className="mx-auto max-w-3xl rounded-xl border border-amber-800 bg-amber-950/20 p-6">
    <h2 className="text-lg font-bold text-amber-200">PayPal checkout cancelled</h2>
    <p className="mt-2 text-sm text-slate-300">The buyer returned from PayPal without completing checkout. AEON has not treated the redirect as payment confirmation.</p>
    {orderId && <p className="mt-3 break-all font-mono text-xs text-slate-400">Order: {orderId}</p>}
    <a href="/" className="mt-5 inline-block rounded-md border border-aeon-border px-4 py-2 text-xs text-white">Return to dashboard</a>
  </section>;

  const status = payment?.status;
  const completed = status === 'COMPLETED';
  const failed = ['FAILED', 'DENIED', 'VOIDED', 'CANCELLED'].includes(status);
  const reconcile = async () => {
    if (!orderId) return; setBusy(true); setError('');
    try { const result = await reconcilePayPalOrder(orderId); setPayment(result); setMessage('PayPal reconciliation request completed.'); }
    catch (e) { setError(e instanceof Error ? e.message : 'Reconciliation failed'); }
    finally { setBusy(false); }
  };

  return <section className={`mx-auto max-w-3xl rounded-xl border p-6 ${completed ? 'border-emerald-700 bg-emerald-950/25' : failed ? 'border-red-800 bg-red-950/20' : 'border-cyan-800 bg-slate-900/70'}`} aria-live="polite">
    <h2 className={`text-lg font-bold ${completed ? 'text-emerald-300' : failed ? 'text-red-300' : 'text-cyan-200'}`}>{completed ? 'PAYMENT CAPTURE CONFIRMED' : failed ? 'PAYMENT FAILED' : 'VERIFYING PAYMENT WITH PAYPAL'}</h2>
    <p className="mt-2 text-sm text-slate-300">{completed ? 'The backend reports a completed PayPal capture and settled ledger transaction.' : failed ? 'PayPal reported a terminal failure. The backend controls reservation release.' : 'Buyer approval is not proof of payment. AEON is checking its server-side capture and PayPal status.'}</p>
    {message && <p className="mt-3 text-xs text-cyan-200">{message}</p>}
    {error && <p className="mt-3 text-xs text-amber-300">{error}</p>}
    {orderId && <p className="mt-4 break-all font-mono text-xs text-slate-400">PayPal Order ID: {orderId}</p>}
    {payment && <div className="mt-4 grid gap-3 sm:grid-cols-2">
      <div className="rounded-lg bg-slate-950/50 p-3"><p className="text-[10px] uppercase text-slate-500">Payment status</p><p className="mt-1 font-mono text-sm text-white">{payment.status ?? 'Unknown'}</p></div>
      <div className="rounded-lg bg-slate-950/50 p-3"><p className="text-[10px] uppercase text-slate-500">Capture ID</p><p className="mt-1 break-all font-mono text-xs text-white">{payment.provider_capture_id ?? 'Not issued yet'}</p></div>
    </div>}
    {!completed && !failed && orderId && <button disabled={busy} onClick={() => void reconcile()} className="mt-5 rounded-md border border-cyan-700 px-4 py-2 text-xs font-semibold text-cyan-200 disabled:opacity-50">{busy ? 'Reconciling…' : 'Reconcile with PayPal now'}</button>}
    <a href="/" className="mt-5 ml-3 inline-block text-xs text-slate-300 underline">Return to dashboard</a>
  </section>;
}
