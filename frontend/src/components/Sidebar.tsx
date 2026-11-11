import type { NavigationTab, ServiceHealthResponse } from '../types';
import {
  IconShield,
  IconBot,
  IconFileText,
  IconScale,
  IconCreditCard,
  IconHistory,
} from './icons';

interface NavItem {
  id: NavigationTab;
  label: string;
  badge: string;
  icon: (props: { className?: string }) => JSX.Element;
}

const navItems: NavItem[] = [
  { id: 'overview', label: 'Overview', badge: 'Live', icon: IconShield },
  { id: 'agents', label: 'Agents', badge: 'Day 2', icon: IconBot },
  { id: 'procurement', label: 'Procurement', badge: 'Day 2-3', icon: IconFileText },
  { id: 'policies', label: 'Policies', badge: 'Day 2-3', icon: IconScale },
  { id: 'transactions', label: 'Transactions', badge: 'Day 4–5', icon: IconCreditCard },
  { id: 'audit', label: 'Audit Log', badge: 'Day 5', icon: IconHistory },
];

interface SidebarProps {
  activeTab: NavigationTab;
  onTabChange: (tab: NavigationTab) => void;
  health: ServiceHealthResponse | null;
  loading: boolean;
}

export function Sidebar({ activeTab, onTabChange, health, loading }: SidebarProps) {
  return (
    <aside className="w-64 border-r border-aeon-border bg-aeon-card flex flex-col justify-between select-none">
      <div>
        {/* Navigation Section Title */}
        <div className="px-4 py-3 border-b border-aeon-borderSubtle">
          <span className="text-[10px] uppercase font-bold tracking-wider text-aeon-textMuted font-mono">
            Navigation
          </span>
        </div>

        {/* Navigation List */}
        <nav className="p-2 space-y-1">
          {navItems.map((item) => {
            const isActive = activeTab === item.id;
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                onClick={() => onTabChange(item.id)}
                className={`w-full flex items-center justify-between px-3 py-2 rounded-md text-xs font-medium transition-all ${
                  isActive
                    ? 'bg-aeon-surface border border-aeon-border text-aeon-cyan'
                    : 'text-aeon-textSecondary hover:text-white hover:bg-aeon-surfaceHover/60 border border-transparent'
                }`}
              >
                <div className="flex items-center space-x-2.5">
                  <Icon className={`w-4 h-4 ${isActive ? 'text-aeon-cyan' : 'text-aeon-textMuted'}`} />
                  <span>{item.label}</span>
                </div>
                <span
                  className={`text-[9px] font-mono px-1.5 py-0.5 rounded ${
                    item.badge === 'Live'
                      ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                      : 'bg-aeon-bg text-aeon-textMuted border border-aeon-borderSubtle'
                  }`}
                >
                  {item.badge}
                </span>
              </button>
            );
          })}
        </nav>
      </div>

      {/* System Telemetry in Footer */}
      <div className="p-3 m-3 rounded-lg bg-aeon-bg border border-aeon-borderSubtle text-[11px] font-mono space-y-2">
        <div className="flex items-center justify-between border-b border-aeon-borderSubtle pb-1.5">
          <span className="text-[10px] text-aeon-textMuted uppercase">Service Telemetry</span>
          <span className={`h-1.5 w-1.5 rounded-full ${health?.status === 'healthy' ? 'bg-emerald-400' : 'bg-red-500'}`} />
        </div>
        {loading ? (
          <p className="text-aeon-textMuted text-[10px]">Polling telemetry...</p>
        ) : health ? (
          <div className="space-y-1 text-[10px] text-aeon-textSecondary">
            <div className="flex justify-between">
              <span className="text-aeon-textMuted">Service:</span>
              <span className="text-white truncate max-w-[110px]">{health.app ?? health.service ?? 'AEON API'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-aeon-textMuted">Version:</span>
              <span className="text-aeon-cyan">{health.version ?? 'v1'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-aeon-textMuted">Uptime:</span>
              <span>{health.uptimeSeconds ?? '—'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-aeon-textMuted">Env:</span>
              <span className="capitalize">{health.environment ?? 'unknown'}</span>
            </div>
          </div>
        ) : (
          <p className="text-red-400 text-[10px]">Backend unreachable on :8000</p>
        )}
      </div>
    </aside>
  );
}
