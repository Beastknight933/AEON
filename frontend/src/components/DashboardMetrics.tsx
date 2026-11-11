import { useCallback, useEffect, useState } from 'react';
import { fetchDashboardStats } from '../services/api';
import { MetricCard } from './MetricCard';
import { IconBot, IconFileText, IconScale, IconCreditCard } from './icons';
export function DashboardMetrics() {
  const [stats, setStats] = useState<any>(null);
  const [error, setError] = useState('');
  const refresh = useCallback(async () => { try { setStats(await fetchDashboardStats()); setError(''); } catch (e) { setError(e instanceof Error ? e.message : 'Unable to load dashboard metrics'); } }, []);
  useEffect(() => { void refresh(); const timer = window.setInterval(() => void refresh(), 8000); return () => window.clearInterval(timer); }, [refresh]);
  const currency = stats?.currency ?? 'USD';
  const money = (v: number) => new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(v);
  return <div className="space-y-2"><div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4"><MetricCard title="Active Agents" value={stats?.active_agents ?? '—'} subtitle={`${stats?.total_agents ?? 0} registered agents`} badgeText="Database-backed" badgeVariant="neutral" icon={IconBot}/><MetricCard title="Pending Approvals" value={stats?.pending_approvals_count ?? '—'} subtitle={`${stats?.total_purchases_count ?? 0} total purchases`} badgeText="Approval queue" badgeVariant="warning" icon={IconFileText}/><MetricCard title="Budget Available" value={stats ? money(Number(stats.total_budget_available)) : '—'} subtitle={`${money(Number(stats?.total_budget_reserved ?? 0))} reserved`} badgeText="Atomic budget" badgeVariant="success" icon={IconScale}/><MetricCard title="Budget Spent" value={stats ? money(Number(stats.total_budget_spent)) : '—'} subtitle={`${stats?.completed_purchases_count ?? 0} completed purchases`} badgeText="Ledger-backed" badgeVariant="cyan" icon={IconCreditCard}/></div>{error && <p className="text-[10px] text-amber-300">Metrics unavailable: {error}</p>}</div>;
}
