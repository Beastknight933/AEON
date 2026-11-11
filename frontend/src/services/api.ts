import type {
  AgentRecord, AuditEvent, LedgerResponse, LedgerSummary, LedgerTransaction,
  PurchaseResult, ServiceHealthResponse,
} from '../types';

const API_PREFIX = '/api/v1';
const TOKEN_KEY = 'aeon_admin_access_token';
const AGENT_KEY_PREFIX = 'aeon_agent_api_key:';

export function getAccessToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}
export function setAccessToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY, token);
}
export function clearSession(): void {
  sessionStorage.removeItem(TOKEN_KEY);
  Object.keys(sessionStorage).filter((key) => key.startsWith(AGENT_KEY_PREFIX)).forEach((key) => sessionStorage.removeItem(key));
}
function agentKey(agentId: string): string | null {
  return sessionStorage.getItem(`${AGENT_KEY_PREFIX}${agentId}`);
}

async function request<T>(path: string, init: RequestInit = {}, options: { agentApiKey?: string; auth?: boolean } = {}): Promise<T> {
  const headers = new Headers(init.headers || {});
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  if (options.auth !== false) {
    const token = getAccessToken();
    if (token) headers.set('Authorization', `Bearer ${token}`);
  }
  if (options.agentApiKey) headers.set('X-Agent-API-Key', options.agentApiKey);

  const response = await fetch(path.startsWith('http') ? path : path, { ...init, headers });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const apiError = payload?.error;
    const message = apiError?.message || payload?.detail || payload?.message || `${response.status} ${response.statusText}`;
    const detail = apiError?.details ? ` (${JSON.stringify(apiError.details)})` : '';
    throw new Error(`${message}${detail}`);
  }
  return payload as T;
}

export async function fetchHealth(): Promise<ServiceHealthResponse> {
  return request<ServiceHealthResponse>('/health', {}, { auth: false });
}

export async function login(payload: { email: string; password: string }): Promise<{ access_token: string; token_type: string; expires_in_minutes: number }> {
  return request(`${API_PREFIX}/auth/login`, { method: 'POST', body: JSON.stringify(payload) }, { auth: false });
}
export async function registerAdmin(payload: { email: string; password: string; full_name: string; organization_name: string }): Promise<{ access_token: string; token_type: string; expires_in_minutes: number }> {
  return request(`${API_PREFIX}/auth/register`, { method: 'POST', body: JSON.stringify(payload) }, { auth: false });
}
export async function fetchCurrentUser(): Promise<any> {
  return request(`${API_PREFIX}/auth/me`);
}

interface RawAgent { id: string; name: string; description?: string | null; is_active: boolean; created_at: string; }
interface RawBudget { id: string; agent_id?: string | null; name: string; currency: string; allocated_amount: string | number; reserved_amount: string | number; spent_amount: string | number; available_amount: string | number; is_active: boolean; }
interface RawAgentSummary { agent_id: string; name: string; assigned_policy_name?: string | null; assigned_budget_allocated?: string | number | null; assigned_budget_spent?: string | number | null; total_spent?: string | number; currency?: string; }
interface RawPolicy { id: string; name: string; versions?: Array<{ version: number; allowed_suppliers: string[]; max_amount_per_day: string | number; max_amount_per_transaction: string | number; }>; }
const num = (v: unknown): number => Number(v ?? 0);

export async function fetchAgents(): Promise<AgentRecord[]> {
  const [agents, budgets, summaries, policies] = await Promise.all([
    request<RawAgent[]>(`${API_PREFIX}/agents`),
    request<RawBudget[]>(`${API_PREFIX}/budgets`),
    request<RawAgentSummary[]>(`${API_PREFIX}/dashboard/agents`),
    request<RawPolicy[]>(`${API_PREFIX}/policies`),
  ]);
  const latestPolicyVersion = (policy?: RawPolicy) => policy?.versions?.slice().sort((a, b) => b.version - a.version)[0];
  return agents.map((agent) => {
    const summary = summaries.find((item) => item.agent_id === agent.id);
    const activeBudgets = budgets.filter((item) => item.agent_id === agent.id && item.is_active);
    const budget = activeBudgets.reduce((sum, item) => sum + num(item.allocated_amount), 0)
      || num(summary?.assigned_budget_allocated);
    const available = activeBudgets.reduce((sum, item) => sum + num(item.available_amount), 0);
    const reserved = activeBudgets.reduce((sum, item) => sum + num(item.reserved_amount), 0);
    const spent = activeBudgets.reduce((sum, item) => sum + num(item.spent_amount), 0)
      || num(summary?.assigned_budget_spent ?? summary?.total_spent);
    const policy = policies.find((item) => item.name === summary?.assigned_policy_name);
    return {
      id: agent.id,
      name: agent.name,
      description: agent.description,
      is_active: agent.is_active,
      created_at: agent.created_at,
      budget,
      remaining_budget: activeBudgets.length ? available : Math.max(0, budget - spent - reserved),
      spent_amount: spent,
      reserved_amount: reserved,
      currency: activeBudgets[0]?.currency || summary?.currency || 'USD',
      allowed_vendors: latestPolicyVersion(policy)?.allowed_suppliers ?? [],
      assigned_policy_name: summary?.assigned_policy_name,
    } satisfies AgentRecord;
  });
}

export async function createAgent(payload: { name: string; budget: number; allowed_vendors: string[]; max_single_purchase?: number }): Promise<AgentRecord & { raw_api_key: string }> {
  const created = await request<{ agent: RawAgent; credentials: { raw_api_key: string } }>(`${API_PREFIX}/agents`, {
    method: 'POST', body: JSON.stringify({ name: payload.name, description: 'Provisioned from AEON procurement dashboard' }),
  });
  const agentId = created.agent.id;
  const key = created.credentials.raw_api_key;
  // The plaintext key is returned once by FastAPI; retain it only in this browser session.
  sessionStorage.setItem(`${AGENT_KEY_PREFIX}${agentId}`, key);
  try {
    const policy = await request<{ id: string }>(`${API_PREFIX}/policies`, {
      method: 'POST',
      body: JSON.stringify({
        name: `${payload.name} Procurement Policy`,
        description: `Budget and supplier controls for ${payload.name}`,
        max_amount_per_transaction: String(payload.max_single_purchase ?? payload.budget),
        max_amount_per_day: String(payload.budget),
        approval_threshold_amount: '0.00',
        allowed_suppliers: payload.allowed_vendors,
        allowed_currencies: ['USD'],
      }),
    });
    await request(`${API_PREFIX}/policies/assignments/${encodeURIComponent(agentId)}`, {
      method: 'POST', body: JSON.stringify({ policy_id: policy.id }),
    });
    await request(`${API_PREFIX}/budgets`, {
      method: 'POST',
      body: JSON.stringify({ name: `${payload.name} Operating Budget`, allocated_amount: String(payload.budget), currency: 'USD', agent_id: agentId }),
    });
  } catch (error) {
    throw new Error(`Agent was created and its one-time API key is saved in this browser session, but policy/budget setup was incomplete: ${error instanceof Error ? error.message : 'unknown error'}. Do not discard the key; finish setup in the Policies/Budgets API.`);
  }
  const rows = await fetchAgents();
  const result = rows.find((row) => row.id === agentId);
  if (!result) throw new Error('Agent created, but it was not returned by the agent listing endpoint.');
  return { ...result, raw_api_key: key };
}

export async function submitPurchase(payload: { agent_id: string; amount: number; item_description: string; category: string }): Promise<PurchaseResult> {
  const key = agentKey(payload.agent_id);
  if (!key) throw new Error('This browser session does not have the one-time API key for this agent. Create the agent from this dashboard in the current browser session, or provision/rotate an agent key and securely add it to this session.');
  const raw = await request<any>(`${API_PREFIX}/purchases`, {
    method: 'POST',
    body: JSON.stringify({
      item_description: payload.item_description,
      category: payload.category,
      max_budget: payload.amount.toFixed(2),
      currency: 'USD',
      requirements: { quantity: 1, source: 'AEON dashboard' },
    }),
  }, { auth: false, agentApiKey: key });
  const policy = raw.policy_decision ?? {};
  const decision: PurchaseResult['decision'] = !policy.allowed || raw.status === 'BLOCKED'
    ? 'BLOCKED'
    : policy.requires_approval || raw.status === 'REQUIRES_APPROVAL'
      ? 'REQUIRES_APPROVAL' : 'APPROVED';
  const selectedQuote = raw.quotes?.find((quote: any) => quote.id === raw.selected_quote_id)
    ?? raw.quotes?.[0];
  const reasoning = raw.recommendation?.reasoning || 'The procurement recommender selected the quote according to its configured scoring strategy.';
  const reasonCodes: string[] = policy.reason_codes ?? [];
  return {
    status: raw.status,
    decision,
    message: decision === 'BLOCKED'
      ? `Blocked by deterministic policy: ${reasonCodes.join(', ') || 'policy violation'}`
      : decision === 'REQUIRES_APPROVAL'
        ? 'Policy permits the request subject to an authorized human approval.'
        : 'Policy authorized the purchase. A human operator can now initiate PayPal checkout.',
    audit_reason: decision === 'BLOCKED' ? reasonCodes.join(', ') : undefined,
    transaction: { id: raw.id, status: raw.status, amount: num(raw.max_budget), vendor: selectedQuote?.supplier_name ?? 'Supplier selected by procurement', human_approved: false },
    quotes: (raw.quotes ?? []).map((quote: any) => ({
      id: quote.id,
      provider: quote.supplier_name,
      price: num(quote.total_amount),
      currency: quote.currency || raw.currency || 'USD',
      delivery_latency_hours: num(quote.estimated_delivery_days) * 24,
      reliability_rating: null,
    })),
    recommendation: {
      recommended_vendor: selectedQuote?.supplier_name ?? 'No supplier selected',
      price: num(selectedQuote?.total_amount ?? raw.max_budget),
      rationale: [reasoning, ...reasonCodes.map((code) => `Policy: ${code}`)],
      source: raw.recommendation?.provider_type ?? 'backend',
    },
  };
}

export async function approvePurchase(purchaseRequestId: string): Promise<void> {
  const approvals = await request<any[]>(`${API_PREFIX}/approvals`);
  const approval = approvals.find((item) => item.purchase_request_id === purchaseRequestId && ['PENDING', 'REQUIRES_APPROVAL'].includes(item.status));
  if (!approval) return; // The policy engine may have authorized the purchase without a separate approval record.
  await request(`${API_PREFIX}/approvals/${encodeURIComponent(approval.id)}/decide`, {
    method: 'POST', body: JSON.stringify({ decision: 'APPROVE', notes: 'Approved by an authorized dashboard operator.' }),
  });
}

export async function createPayPalOrder(purchaseRequestId: string): Promise<{ orderID: string; approvalUrl: string; paymentAttemptId: string }> {
  const result = await request<any>(`${API_PREFIX}/payments/create-order`, {
    method: 'POST', body: JSON.stringify({ purchase_request_id: purchaseRequestId }),
  });
  if (!result.approval_url) throw new Error('PayPal order was created but the API did not return an approval URL.');
  return { orderID: result.provider_order_id, approvalUrl: result.approval_url, paymentAttemptId: result.payment_attempt_id };
}

export async function capturePayPalOrder(providerOrderId: string): Promise<any> {
  return request(`${API_PREFIX}/payments/capture`, {
    method: 'POST', body: JSON.stringify({ provider_order_id: providerOrderId }),
  });
}
export async function fetchPayPalStatus(providerOrderId: string): Promise<any> {
  return request(`${API_PREFIX}/payments/${encodeURIComponent(providerOrderId)}`);
}
export async function reconcilePayPalOrder(providerOrderId: string): Promise<any> {
  return request(`${API_PREFIX}/payments/${encodeURIComponent(providerOrderId)}/reconcile`, { method: 'POST' });
}

interface RawTransaction { id: string; purchase_request_id: string; budget_id?: string | null; status: string; amount: string | number; currency: string; provider_transaction_id?: string | null; created_at: string; }
interface RawPurchase { id: string; agent_id: string; item_description: string; category: string; status: string; max_budget: string | number; currency: string; created_at: string; }
interface RawTransactionDetail extends RawTransaction { purchase_request?: { agent_id: string; agent_name?: string; supplier_name?: string | null; item_description?: string; category?: string }; payment_attempt?: { provider_order_id?: string; provider_capture_id?: string; status?: string }; }

export async function fetchTransactions(filters: { status?: string; agent_id?: string; search?: string } = {}): Promise<LedgerResponse> {
  const params = new URLSearchParams({ page: '1', page_size: '100', sort_by: 'created_at', sort_order: 'desc' });
  if (filters.status && filters.status !== 'ALL') params.set('status', filters.status);
  const [page, purchases, agents, budgets] = await Promise.all([
    request<{ items: RawTransaction[]; total: number }>(`${API_PREFIX}/transactions?${params.toString()}`),
    request<RawPurchase[]>(`${API_PREFIX}/purchases?skip=0&limit=100`),
    fetchAgents(),
    request<RawBudget[]>(`${API_PREFIX}/budgets`),
  ]);
  const details = await Promise.all(page.items.map((item) => request<RawTransactionDetail>(`${API_PREFIX}/transactions/${encodeURIComponent(item.id)}`).catch(() => item as RawTransactionDetail)));
  const purchaseMap = new Map(purchases.map((purchase) => [purchase.id, purchase]));
  const rows: LedgerTransaction[] = details.map((item) => {
    const purchase = item.purchase_request ?? purchaseMap.get(item.purchase_request_id);
    const agent = agents.find((candidate) => candidate.id === (purchase as any)?.agent_id);
    const budget = budgets.filter((candidate) => candidate.agent_id === agent?.id && candidate.is_active);
    const remaining = budget.length ? budget.reduce((sum, current) => sum + num(current.available_amount), 0) : null;
    return {
      id: item.id,
      purchase_request_id: item.purchase_request_id,
      agent_id: (purchase as any)?.agent_id ?? '',
      agent_name: (purchase as any)?.agent_name ?? agent?.name ?? 'Unknown agent',
      vendor: (purchase as any)?.supplier_name ?? (purchase as any)?.category ?? '—',
      item_description: (purchase as any)?.item_description ?? '—',
      amount: num(item.amount), currency: item.currency,
      status: item.status,
      policy_decision: (purchase as any)?.status ?? '—',
      created_at: item.created_at,
      remaining_budget: remaining,
      paypal_order_id: item.payment_attempt?.provider_order_id,
      paypal_capture_id: item.payment_attempt?.provider_capture_id ?? item.provider_transaction_id ?? undefined,
    };
  });
  const data = rows.filter((row) => {
    const matchesAgent = !filters.agent_id || filters.agent_id === 'ALL' || row.agent_id === filters.agent_id;
    const q = filters.search?.toLowerCase();
    const matchesSearch = !q || [row.agent_name, row.vendor, row.item_description, row.status, row.id, row.paypal_order_id, row.paypal_capture_id].some((v) => String(v ?? '').toLowerCase().includes(q));
    return matchesAgent && matchesSearch;
  });
  const summary: LedgerSummary = {
    total: page.total,
    pending: rows.filter((row) => ['PENDING', 'CAPTURE_PENDING', 'ORDER_CREATED', 'BUYER_APPROVAL_PENDING'].includes(row.status)).length,
    blocked: purchases.filter((row) => row.status === 'BLOCKED').length,
    completed: rows.filter((row) => ['SETTLED', 'COMPLETED'].includes(row.status)).length,
    failed: rows.filter((row) => ['FAILED', 'CANCELLED'].includes(row.status)).length,
    completed_amount: rows.filter((row) => ['SETTLED', 'COMPLETED'].includes(row.status)).reduce((sum, row) => sum + row.amount, 0),
  };
  return { status: 'success', count: data.length, data, summary };
}

export async function fetchAuditEvents(): Promise<{ status: string; count: number; data: AuditEvent[] }> {
  const result = await request<{ items: any[]; total: number }>(`${API_PREFIX}/audit?page=1&page_size=100&sort_by=created_at&sort_order=desc`);
  const data = result.items.map((event) => ({
    id: event.id,
    transaction_id: event.entity_id ?? '',
    agent_id: event.actor_type === 'AGENT' ? event.actor_id ?? '' : '',
    agent_name: event.actor_type === 'AGENT' ? event.actor_id ?? 'Agent' : event.actor_type,
    vendor: event.metadata_json?.supplier_name ?? event.metadata_json?.vendor ?? '—',
    amount: num(event.metadata_json?.amount),
    event: event.action,
    detail: JSON.stringify(event.metadata_json ?? {}),
    timestamp: event.created_at,
    status: event.metadata_json?.status ?? 'RECORDED',
    paypal_order_id: event.metadata_json?.order_id,
    paypal_capture_id: event.metadata_json?.capture_id,
  } satisfies AuditEvent));
  return { status: 'success', count: result.total, data };
}

export async function fetchTransactionTimeline(transactionId: string): Promise<any> {
  return request(`${API_PREFIX}/transactions/${encodeURIComponent(transactionId)}/timeline`);
}

export async function fetchDashboardStats(): Promise<any> {
  return request(`${API_PREFIX}/dashboard/stats`);
}
export async function fetchDashboardOverview(): Promise<any> {
  return request(`${API_PREFIX}/dashboard/overview`);
}
export async function fetchPolicies(): Promise<any[]> {
  return request(`${API_PREFIX}/policies`);
}

export type { AgentRecord, AuditEvent, LedgerResponse, LedgerSummary, LedgerTransaction, PurchaseResult, ServiceHealthResponse } from '../types';
