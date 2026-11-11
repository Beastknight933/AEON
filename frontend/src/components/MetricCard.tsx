interface MetricCardProps {
  title: string;
  value: string | number;
  subtitle: string;
  badgeText: string;
  badgeVariant?: 'neutral' | 'success' | 'warning' | 'danger' | 'cyan';
  icon: (props: { className?: string }) => JSX.Element;
}

export function MetricCard({
  title,
  value,
  subtitle,
  badgeText,
  badgeVariant = 'neutral',
  icon: Icon,
}: MetricCardProps) {
  const badgeClasses = {
    neutral: 'bg-aeon-surface border-aeon-border text-aeon-textMuted',
    success: 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400',
    warning: 'bg-amber-500/10 border-amber-500/20 text-amber-400',
    danger: 'bg-red-500/10 border-red-500/20 text-red-400',
    cyan: 'bg-aeon-cyan/10 border-aeon-cyan/20 text-aeon-cyan',
  }[badgeVariant];

  return (
    <div className="p-4 rounded-xl bg-aeon-card border border-aeon-border relative overflow-hidden transition-all hover:border-slate-700">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-semibold text-aeon-textMuted uppercase tracking-wider font-mono">
          {title}
        </span>
        <div className="p-1.5 rounded-md bg-aeon-surface border border-aeon-borderSubtle text-aeon-textSecondary">
          <Icon className="w-3.5 h-3.5" />
        </div>
      </div>

      <div className="mt-3">
        <div className="text-2xl font-bold font-mono tracking-tight text-white">
          {value}
        </div>
        <p className="text-[11px] text-aeon-textMuted mt-1">
          {subtitle}
        </p>
      </div>

      <div className="mt-3 pt-2.5 border-t border-aeon-borderSubtle flex items-center justify-between text-[10px]">
        <span className="text-aeon-textMuted font-mono">Integration State</span>
        <span className={`px-2 py-0.5 rounded border font-mono font-medium ${badgeClasses}`}>
          {badgeText}
        </span>
      </div>
    </div>
  );
}
