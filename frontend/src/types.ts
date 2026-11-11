export type NavigationTab = 'overview' | 'agents' | 'procurement' | 'policies' | 'transactions' | 'audit';

export interface ServiceHealthResponse {
  status: 'healthy' | 'ready' | 'not_ready' | 'degraded' | 'unhealthy';
  app?: string;
  environment?: string;
  service?: string;
  version?: string;
  uptimeSeconds?: number;
  timestamp?: string;
  database?: string;
}

export interface AgentRecord {
  id: string;
  name: string;
  description?: string | null;
  is_active: boolean;
  created_at: string;
  budget: number;
  remaining_budget: number;
  spent_amount: number;
  reserved_amount: number;
  currency: string;
  allowed_vendors: string[];
  assigned_policy_name?: string | null;
}

export interface SupplierQuote {
  id: string;
  provider: string;
  price: number;
  currency: string;
  delivery_latency_hours: number;
  reliability_rating?: number | null;
}

export interface Recommendation {
  recommended_vendor: string;
  price: number;
  rationale: string[];
  source: string;
}

export interface PurchaseResult {
  status: string;
  decision: 'APPROVED' | 'REQUIRES_APPROVAL' | 'BLOCKED';
  message: string;
  audit_reason?: string;
  transaction: { id: string; status: string; amount: number; vendor: string; human_approved?: boolean; paypal_order_id?: string };
  quotes: SupplierQuote[];
  recommendation: Recommendation;
}

export interface LedgerTransaction {
  id: string;
  purchase_request_id: string;
  agent_id: string;
  agent_name: string;
  vendor: string;
  item_description: string;
  amount: number;
  currency: string;
  status: string;
  policy_decision: string;
  reason?: string | null;
  created_at: string;
  remaining_budget: number | null;
  paypal_order_id?: string;
  paypal_capture_id?: string;
}

export interface LedgerSummary {
  total: number;
  pending: number;
  blocked: number;
  completed: number;
  failed: number;
  completed_amount: number;
}

export interface LedgerResponse {
  status: string;
  count: number;
  data: LedgerTransaction[];
  summary: LedgerSummary;
}

export interface AuditEvent {
  id: string;
  transaction_id: string;
  agent_id: string;
  agent_name: string;
  vendor: string;
  amount: number;
  event: string;
  detail: string;
  timestamp: string;
  status: string;
  paypal_order_id?: string;
  paypal_capture_id?: string;
}
