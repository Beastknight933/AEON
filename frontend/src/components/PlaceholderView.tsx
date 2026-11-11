import type { NavigationTab } from '../types';
import { IconLock, IconBot, IconFileText, IconScale, IconCreditCard, IconHistory } from './icons';

interface PlaceholderViewProps {
  tab: NavigationTab;
}

const tabMetadata: Record<
  Exclude<NavigationTab, 'overview'>,
  {
    title: string;
    phase: string;
    description: string;
    deliverables: string[];
    icon: (props: { className?: string }) => JSX.Element;
  }
> = {
  agents: {
    title: 'Agent Identity & Delegation Control',
    phase: 'Day 2 Architecture Deliverable',
    description: 'Manages agent credentials, cryptographic task identities, per-agent spending budgets, and approved supplier allowlists.',
    deliverables: [
      'POST /api/v1/agents registration endpoint',
      'Configurable daily spending limit & single transaction ceilings',
      'Vendor allowlist management (Provider A vs Provider C)',
      'Remaining budget tracking and exhaustion rules',
    ],
    icon: IconBot,
  },
  procurement: {
    title: 'Procurement Engine & Supplier Quote Comparison',
    phase: 'Day 2–3 Architecture Deliverable',
    description: 'Accepts purchase requests from registered agents, simulates two supplier quotes, normalizes responses, and utilizes Gemini LLM structured JSON output for quote recommendation.',
    deliverables: [
      'POST /api/v1/procurement/request endpoint',
      'Two simulated supplier quote generator (Provider A vs Provider B/C)',
      'Gemini structured JSON recommendation with audit justification',
      'Strict input schema validation & untrusted data isolation',
    ],
    icon: IconFileText,
  },
  policies: {
    title: 'Deterministic Policy Enforcement Engine',
    phase: 'Day 2–3 Architecture Deliverable',
    description: 'Mathematical and rule-based authorization that evaluates agent status, allowlists, and budget thresholds before any PayPal order can be created.',
    deliverables: [
      'Pure deterministic TypeScript evaluation logic',
      'Strict invariant: AI recommends; deterministic backend authorizes or blocks',
      'Explicit reason codes (APPROVED, REQUIRES_APPROVAL, BLOCKED)',
      'Immediate block before PayPal order creation for overspending or unapproved vendors',
    ],
    icon: IconScale,
  },
  transactions: {
    title: 'PayPal Orders v2 & Sandbox Settlement',
    phase: 'Day 4 Architecture Deliverable',
    description: 'Server-side PayPal integration executing OAuth2 token caching, Orders v2 creation with CAPTURE intent, human buyer approval redirect, and post-approval capture.',
    deliverables: [
      'Backend OAuth2 client credentials token caching',
      'POST /v2/checkout/orders (intent: CAPTURE, custom_id tracking)',
      'Human buyer sandbox approval interface (no silent unauthorized charging)',
      'Server-side order capture and PayPal order/capture ID persistence',
    ],
    icon: IconCreditCard,
  },
  audit: {
    title: 'Immutable Ledger & Verified Webhooks',
    phase: 'Day 5 Audit Ledger',
    description: 'Cryptographic webhook signature verification, idempotent event ingestion, and audit timeline connecting agent tasks to payment evidence.',
    deliverables: [
      'PayPal webhook signature verification endpoint',
      'Idempotent webhook deduplication via unique event ID index',
      'Append-only PostgreSQL audit timeline',
      'Strict separation of payment completion vs service delivery',
    ],
    icon: IconHistory,
  },
};

export function PlaceholderView({ tab }: PlaceholderViewProps) {
  if (tab === 'overview') return null;

  const meta = tabMetadata[tab];
  const Icon = meta.icon;

  return (
    <div className="space-y-6">
      {/* Module Overview Card */}
      <div className="p-6 rounded-xl bg-aeon-card border border-aeon-border">
        <div className="flex items-start justify-between border-b border-aeon-borderSubtle pb-4">
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-lg bg-aeon-surface border border-aeon-border text-aeon-cyan">
              <Icon className="w-5 h-5 text-aeon-cyan" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-white tracking-wide">
                {meta.title}
              </h2>
              <p className="text-xs text-aeon-textMuted mt-0.5">
                {meta.description}
              </p>
            </div>
          </div>
          <div className="flex items-center space-x-2">
            <IconLock className="w-3.5 h-3.5 text-amber-400" />
            <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20 font-medium">
              {meta.phase}
            </span>
          </div>
        </div>

        {/* Deliverables Checklist */}
        <div className="mt-5 space-y-3">
          <h3 className="text-[11px] font-semibold text-aeon-textSecondary uppercase font-mono tracking-wider">
            Planned Technical Deliverables
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
            {meta.deliverables.map((item, idx) => (
              <div
                key={idx}
                className="p-3 rounded-lg bg-aeon-surface border border-aeon-borderSubtle flex items-start space-x-2 text-xs"
              >
                <span className="text-aeon-cyan font-mono text-[11px] font-bold">0{idx + 1}.</span>
                <span className="text-slate-300 text-[11px]">{item}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Prototype Integrity Notice */}
        <div className="mt-5 p-3 rounded-lg bg-aeon-bg border border-aeon-borderSubtle text-[11px] text-aeon-textMuted flex items-center justify-between">
          <span className="font-mono">
            Integrity Guard: UI actions for this module are locked until backend endpoints and policy tests are implemented.
          </span>
          <span className="text-aeon-cyan font-mono text-[10px]">
            No mock actions allowed
          </span>
        </div>
      </div>
    </div>
  );
}
