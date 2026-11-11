import { FormEvent, useState } from 'react';
import { login, registerAdmin, setAccessToken } from '../services/api';

export function AuthScreen({ onAuthenticated }: { onAuthenticated: () => void }) {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [organizationName, setOrganizationName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const result = mode === 'login'
        ? await login({ email, password })
        : await registerAdmin({ email, password, full_name: fullName, organization_name: organizationName });
      setAccessToken(result.access_token);
      onAuthenticated();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Authentication failed');
    } finally { setBusy(false); }
  };

  return <div className="min-h-screen flex items-center justify-center bg-aeon-bg px-4 py-10">
    <div className="w-full max-w-md rounded-2xl border border-aeon-border bg-aeon-card p-7 shadow-2xl">
      <div className="mb-7 flex items-center gap-3"><div className="flex h-10 w-10 items-center justify-center rounded-xl border border-aeon-border bg-aeon-surface text-aeon-cyan">◆</div><div><h1 className="text-xl font-extrabold tracking-wide text-white">AEON</h1><p className="text-[11px] text-aeon-textMuted">Agent Procurement Control Plane</p></div></div>
      <h2 className="text-lg font-semibold text-white">{mode === 'login' ? 'Administrator sign in' : 'Create your organization'}</h2>
      <p className="mt-1 text-xs text-aeon-textMuted">The dashboard uses the FastAPI backend's administrator JWT authentication.</p>
      <form className="mt-6 space-y-4" onSubmit={submit}>
        {mode === 'register' && <>
          <label className="block text-xs text-aeon-textSecondary">Full name<input required value={fullName} onChange={(e) => setFullName(e.target.value)} className="mt-1 w-full rounded-md border border-aeon-border bg-aeon-bg p-3 text-sm text-white" /></label>
          <label className="block text-xs text-aeon-textSecondary">Organization name<input required value={organizationName} onChange={(e) => setOrganizationName(e.target.value)} className="mt-1 w-full rounded-md border border-aeon-border bg-aeon-bg p-3 text-sm text-white" /></label>
        </>}
        <label className="block text-xs text-aeon-textSecondary">Email<input type="email" required autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} className="mt-1 w-full rounded-md border border-aeon-border bg-aeon-bg p-3 text-sm text-white" /></label>
        <label className="block text-xs text-aeon-textSecondary">Password<input type="password" required minLength={8} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} value={password} onChange={(e) => setPassword(e.target.value)} className="mt-1 w-full rounded-md border border-aeon-border bg-aeon-bg p-3 text-sm text-white" /></label>
        {error && <div role="alert" className="rounded-md border border-red-800 bg-red-950/40 p-3 text-xs text-red-300">{error}</div>}
        <button disabled={busy} className="w-full rounded-md bg-cyan-500 px-4 py-3 text-sm font-semibold text-slate-950 disabled:opacity-50">{busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Register organization'}</button>
      </form>
      <button onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(''); }} className="mt-5 w-full text-xs text-aeon-cyan hover:text-white">{mode === 'login' ? 'New to AEON? Register an organization' : 'Already registered? Sign in'}</button>
      <p className="mt-6 border-t border-aeon-borderSubtle pt-4 text-[10px] leading-5 text-aeon-textMuted">Administrator credentials are sent only to your AEON API. The access token is kept in this browser tab's session storage.</p>
    </div>
  </div>;
}
