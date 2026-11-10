# AEON Database Schema & Entities

The AEON backend uses **Supabase PostgreSQL** via SQLAlchemy 2.x async (`asyncpg`) and Alembic for schema migrations.

All primary keys are UUIDs (`uuid.uuid4`). All financial quantities use `NUMERIC(12, 2)` (never floating point).

---

## 1. Entity Catalog (19 Tables)

| Table | Purpose | Key Constraints |
|---|---|---|
| `organizations` | Tenant organization boundaries | `UNIQUE(name)`, `UNIQUE(slug)` |
| `users` | Dashboard administrator accounts | `UNIQUE(email)`, indexed |
| `memberships` | User-Organization RBAC mapping | `UNIQUE(user_id, organization_id)`, `role` enum |
| `agents` | Autonomous AI agents | FK to `organizations.id` |
| `agent_credentials` | Agent API key hashes & prefixes | `UNIQUE(key_hash)`, `INDEX(key_prefix)` |
| `policies` | Procurement governance rules | FK to `organizations.id` |
| `policy_versions` | Immutable versioned policy limits | `UNIQUE(policy_id, version)` |
| `agent_policy_assignments` | Active policy assigned to an agent | `UNIQUE(agent_id, policy_id)` |
| `budgets` | Financial allocations & caps | `allocated_amount`, `reserved_amount`, `spent_amount` |
| `purchase_requests` | Agent purchase requests | Status enum, foreign keys to agent and org |
| `suppliers` | Registered supplier providers | `UNIQUE(code)` |
| `supplier_quotes` | Normalized quotes for a purchase | `NUMERIC(12, 2)` prices |
| `recommendations` | ML recommendation decisions & scores | FK to `purchase_requests.id` |
| `budget_reservations` | Active reservations before capture | Status enum (`ACTIVE`, `SETTLED`, `RELEASED`) |
| `approvals` | Human approval workflows | Status enum (`PENDING`, `APPROVED`, `REJECTED`) |
| `transactions` | Immutable financial ledger | Status and Type enums |
| `payment_attempts` | PayPal order and capture records | `UNIQUE(idempotency_key)`, `UNIQUE(provider_order_id)` |
| `webhook_events` | Webhook ingestion log & idempotency | `UNIQUE(provider_event_id)` |
| `audit_events` | Append-only governance audit trail | Indexed by `actor_id`, `action`, `created_at` |

---

## 2. Key Database Constraints & Integrity Rules

1. **Deterministic Money Calculation**:
   - `available_amount = allocated_amount - reserved_amount - spent_amount`
   - Every reservation checks `available_amount >= requested_amount` under a row-level lock (`with_for_update()`).
2. **Provider Event Idempotency**:
   - `webhook_events.provider_event_id` is unique. Duplicate deliveries are detected and rejected before mutation.
3. **No Direct Key Storage**:
   - `agent_credentials` stores only `key_prefix` (16 chars) and `key_hash` (SHA-256). Raw keys are never stored.
4. **Append-Only Audit Ledger**:
   - The application provides no update or delete operations on `audit_events`.
