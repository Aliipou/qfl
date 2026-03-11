# QFL Platform — API Reference

**Base URL**: `http://localhost:8000`
**Interactive docs**: `http://localhost:8000/docs` (Swagger UI)

All endpoints return JSON. Timestamps are ISO 8601 UTC.

---

## Authentication

Phase 1 uses no authentication (internal network assumed). Phase 5 will add
JWT Bearer tokens via `Authorization: Bearer <token>`.

Rate limit: **200 requests per minute per IP** (hashed, GDPR-compliant).
Exceeded requests receive `429 Too Many Requests` with `Retry-After: 60`.

---

## GET /health

Liveness probe. Used by Kubernetes, Docker, and load balancers.

**Response 200:**
```json
{
  "status": "ok",
  "version": "0.1.0",
  "quantum_backend": "aer_simulator",
  "timestamp": "2026-03-11T12:00:00.000Z"
}
```

`quantum_backend` is `"aer_simulator"` when IBM Quantum is not connected,
or the IBM backend name (e.g. `"ibm_brisbane"`) when connected.

---

## POST /train

Trigger a new federated learning round.

**Request body:**
```json
{
  "config": {
    "num_clients":    3,       // integer [1, 100], required clients before aggregation
    "local_epochs":   5,       // integer [1, 100]
    "learning_rate":  0.01,    // float (0, 1.0]
    "aggregation":    "fed_avg",  // "fed_avg" | "q_fed_avg"
    "dp_epsilon":     1.0,     // float > 0, privacy budget (ε)
    "dp_delta":       1e-5,    // float (0, 1), DP failure probability (δ)
    "use_quantum":    false     // bool, enable VQC + QKD
  },
  "dataset":            "mnist",      // string, dataset identifier
  "model_architecture": "simple_cnn"  // string, model identifier
}
```

All fields are optional. Defaults: `num_clients=3, aggregation=fed_avg, dp_epsilon=1.0`.

**Response 202:**
```json
{
  "id":                       "uuid-v4",
  "status":                   "pending",
  "config":                   { ... },
  "dataset":                  "mnist",
  "model_architecture":       "simple_cnn",
  "created_at":               "2026-03-11T12:00:00Z",
  "started_at":               null,
  "completed_at":             null,
  "global_accuracy":          null,
  "privacy_budget_used":      null,
  "num_clients_participated": 0
}
```

---

## POST /train/{round_id}/update

Submit a local model weight update from a FL client.

Aggregation triggers automatically when `num_clients_participated == config.num_clients`.

**Path parameter:** `round_id` — UUID of the target round.

**Request body:**
```json
{
  "client_id":        "client_01",    // string, unique client identifier
  "round_id":         "uuid-v4",      // must match path parameter
  "tenant_id":        "tenant_a",     // string, tenant namespace
  "weights_hash":     "sha256hex",    // string, SHA-256 of serialized weight tensor
  "num_samples":      5000,           // integer > 0, local training set size
  "local_loss":       0.342,          // float, final training loss
  "local_accuracy":   0.891,          // float, final training accuracy
  "dp_noise_applied": true,           // bool, whether DP-SGD was applied
  "qkd_key_id":       "bb84_key_001"  // string | null, QKD key used for encryption
}
```

**Response 200 (accepted):**
```json
{
  "round_id":  "uuid-v4",
  "client_id": "client_01",
  "accepted":  true,
  "message":   "Update accepted"
}
```

**Response 200 (rejected):**
```json
{
  "round_id":  "uuid-v4",
  "client_id": "client_01",
  "accepted":  false,
  "message":   "Round is completed, not accepting updates"
}
```

**Response 400:** `round_id` in path and body do not match.

---

## GET /status/{round_id}

Get detailed status for a specific FL round.

**Response 200:**
```json
{
  "id":                       "uuid-v4",
  "status":                   "completed",
  "config":                   { "num_clients": 3, "aggregation": "fed_avg", ... },
  "dataset":                  "mnist",
  "model_architecture":       "simple_cnn",
  "created_at":               "2026-03-11T12:00:00Z",
  "started_at":               "2026-03-11T12:00:01Z",
  "completed_at":             "2026-03-11T12:00:04Z",
  "global_accuracy":          0.923,
  "privacy_budget_used":      1.0,
  "num_clients_participated": 3
}
```

**Status values:**

| Value | Meaning |
|---|---|
| `pending` | Created, waiting for first client update |
| `running` | At least one client has submitted |
| `aggregating` | All clients submitted, aggregation in progress |
| `completed` | Aggregation done, `global_accuracy` available |
| `failed` | Aggregation raised an exception |

**Response 404:** Round not found.

---

## GET /status

List all FL rounds.

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `limit` | integer | 20 | Max number of rounds to return |
| `status_filter` | string | null | Filter by status value |

**Example:**
```
GET /status?limit=10&status_filter=completed
```

**Response 200:** Array of FLRound objects, sorted newest first.

---

## GET /audit/report/{tenant_id}

Generate EU AI Act Article 9 compliance report for a tenant.

**Path parameter:** `tenant_id` — string tenant identifier.

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `from_date` | datetime | 30 days ago | Report start time (ISO 8601) |
| `to_date` | datetime | now | Report end time (ISO 8601) |

**Example:**
```
GET /audit/report/tenant_a?from_date=2026-01-01T00:00:00&to_date=2026-12-31T23:59:59
```

**Response 200:**
```json
{
  "tenant_id":                 "tenant_a",
  "from_date":                 "2026-01-01T00:00:00Z",
  "to_date":                   "2026-12-31T23:59:59Z",
  "total_rounds":              12,
  "total_dp_budget_consumed":  12.0,
  "events":                    [ ... ],
  "risk_classification":       "limited",
  "gdpr_compliant":            true,
  "technical_doc_ref":         null
}
```

`risk_classification` values: `"minimal"` | `"limited"` | `"high"` | `"unacceptable"`

---

## GET /audit/events

Stream individual audit log entries.

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `tenant_id` | string | null | Filter by tenant |
| `round_id` | UUID | null | Filter by FL round |
| `limit` | integer | 50 | Max entries (max 500) |

**Response 200:**
```json
[
  {
    "id":            "uuid-v4",
    "event":         "round_completed",
    "round_id":      "uuid-v4",
    "client_id":     null,
    "tenant_id":     "tenant_a",
    "timestamp":     "2026-03-11T12:00:04Z",
    "details": {
      "global_accuracy": 0.923,
      "dp_epsilon_used": 1.0,
      "clients": 3
    },
    "risk_level":    "limited",
    "model_card_ref": null
  }
]
```

**Audit event types:**

| Event | Description |
|---|---|
| `round_started` | New FL round created |
| `client_joined` | First update from a tenant received |
| `client_update_received` | Model weight update submitted |
| `aggregation_completed` | FedAvg/q-FedAvg finished |
| `round_completed` | Round finalized with global accuracy |
| `round_failed` | Aggregation raised exception |
| `dp_budget_consumed` | DP ε deducted from tenant budget |
| `model_deployed` | Model moved to production (Phase 5) |
| `erasure_request` | GDPR Article 17 right-to-erasure request |

---

## Data Models

### FLRound

| Field | Type | Description |
|---|---|---|
| `id` | UUID | Unique round identifier |
| `status` | RoundStatus | Current lifecycle state |
| `config` | FLRoundConfig | Training configuration |
| `dataset` | string | Dataset identifier |
| `model_architecture` | string | Model architecture name |
| `created_at` | datetime | Creation timestamp |
| `started_at` | datetime? | When first client joined |
| `completed_at` | datetime? | When aggregation finished |
| `global_accuracy` | float? | Weighted average accuracy |
| `privacy_budget_used` | float? | ε consumed this round |
| `num_clients_participated` | int | Clients that submitted |

### FLRoundConfig

| Field | Type | Default | Constraint |
|---|---|---|---|
| `num_clients` | int | 3 | [1, 100] |
| `local_epochs` | int | 5 | [1, 100] |
| `learning_rate` | float | 0.01 | (0, 1.0] |
| `aggregation` | AggregationMethod | `fed_avg` | `fed_avg` \| `q_fed_avg` |
| `dp_epsilon` | float | 1.0 | > 0 |
| `dp_delta` | float | 1e-5 | > 0 |
| `use_quantum` | bool | false | — |

### ClientUpdate

| Field | Type | Required | Description |
|---|---|---|---|
| `client_id` | string | yes | Unique client identifier |
| `round_id` | UUID | yes | Target round (must match URL) |
| `tenant_id` | string | yes | Tenant namespace |
| `weights_hash` | string | yes | SHA-256 of weight tensor |
| `num_samples` | int | yes | Local training samples (> 0) |
| `local_loss` | float | yes | Final local training loss |
| `local_accuracy` | float | yes | Final local training accuracy |
| `dp_noise_applied` | bool | no | Was DP-SGD applied? |
| `qkd_key_id` | string? | no | BB84 key used for encryption |

### AuditLog

| Field | Type | Description |
|---|---|---|
| `id` | UUID | Unique entry identifier |
| `event` | AuditEvent | Event type (see table above) |
| `round_id` | UUID? | Associated FL round |
| `client_id` | string? | Associated client |
| `tenant_id` | string? | Associated tenant |
| `timestamp` | datetime | Event time (immutable) |
| `details` | object | Event-specific data |
| `risk_level` | RiskLevel | EU AI Act risk classification |
| `model_card_ref` | string? | Reference to model card document |

---

## Error Responses

All errors follow the FastAPI default format:

```json
{
  "detail": "Human-readable error message"
}
```

| Status | When |
|---|---|
| `400 Bad Request` | `round_id` mismatch in path vs body |
| `404 Not Found` | Round or resource not found |
| `422 Unprocessable Entity` | Request body validation failed (Pydantic) |
| `429 Too Many Requests` | Rate limit exceeded |
| `500 Internal Server Error` | Unexpected server error |

For `422` errors, the response includes field-level details:

```json
{
  "detail": [
    {
      "loc": ["body", "config", "num_clients"],
      "msg": "Input should be greater than or equal to 1",
      "type": "greater_than_equal"
    }
  ]
}
```
