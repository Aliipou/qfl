# QFL Platform — Security Reference

## Security Architecture Overview

```
                        ┌──────────────────────┐
Internet ──── HTTPS ───►│  Nginx (TLS 1.3)     │
                        │  Rate limiting        │
                        │  Security headers     │
                        └──────────┬───────────┘
                                   │ HTTP (internal)
                        ┌──────────▼───────────┐
                        │  FastAPI Coordinator  │
                        │  SecurityHeaders MW   │
                        │  RateLimit MW         │
                        │  RequestID MW         │
                        │  AccessLog MW         │
                        └──────────┬───────────┘
                                   │
               ┌───────────────────┼───────────────────┐
               │                   │                   │
     ┌─────────▼──────┐   ┌───────▼──────┐   ┌───────▼──────┐
     │  PostgreSQL     │   │  Redis       │   │  IBM Quantum  │
     │  (audit log)    │   │  (state)     │   │  (optional)   │
     │  append-only    │   │  auth=on     │   │  token auth   │
     └────────────────┘   └─────────────┘   └─────────────┘
```

---

## HTTP Security Headers

Every response includes:

| Header | Value | Protection |
|---|---|---|
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains; preload` | Forces HTTPS for 2 years, blocks SSL stripping |
| `Content-Security-Policy` | See below | XSS prevention |
| `X-Frame-Options` | `DENY` | Clickjacking prevention |
| `X-Content-Type-Options` | `nosniff` | MIME-type sniffing prevention |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Information leakage prevention |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` | Disables browser APIs |
| `Cache-Control` | `no-store, max-age=0` | Prevents sensitive data caching |

**Content-Security-Policy:**
```
default-src 'self';
script-src 'self' 'unsafe-inline';
style-src 'self' 'unsafe-inline';
img-src 'self' data:;
connect-src 'self';
frame-ancestors 'none';
```

---

## Rate Limiting

### API Level (FastAPI middleware)

- Window: 60 seconds (sliding)
- Limit: 200 requests per IP
- Key: SHA-256(IP) — raw IP is never stored (GDPR compliance)
- Response on exceeded: `429 Too Many Requests` + `Retry-After: 60`
- Remaining requests: `X-RateLimit-Remaining` response header

### Nginx Level (additional layer)

```nginx
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=50r/m;
limit_req_zone $binary_remote_addr zone=train_limit:10m rate=10r/m;
limit_conn_zone $binary_remote_addr zone=conn_limit:10m;
```

The `/train` endpoint has a tighter limit (10 req/min) since FL rounds are
computationally expensive. General API calls allow 50 req/min at the nginx
layer, with the FastAPI middleware providing a secondary 200 req/min per IP.

---

## TLS Configuration

Nginx is configured for maximum TLS security:

```nginx
ssl_protocols TLSv1.3;                               # TLS 1.0/1.1/1.2 disabled
ssl_ciphers ECDHE-ECDSA-AES256-GCM-SHA384:           # Forward secrecy
            ECDHE-RSA-AES256-GCM-SHA384;
ssl_prefer_server_ciphers on;
ssl_session_cache shared:SSL:10m;
ssl_stapling on;                                     # OCSP stapling
ssl_stapling_verify on;
```

HSTS preload means browsers will refuse to connect over HTTP even on first visit.

### Generating self-signed certificates (development)

```bash
mkdir -p infra/nginx/certs
openssl req -x509 -nodes -days 365 -newkey rsa:4096 \
  -keyout infra/nginx/certs/qfl.key \
  -out infra/nginx/certs/qfl.crt \
  -subj "/C=FI/ST=CentralOstrobothnia/L=Kokkola/O=Centria/CN=qfl.local"
```

For production: use Let's Encrypt or a corporate CA.

---

## Container Security

### Dockerfile hardening

```dockerfile
# 1. Multi-stage build — attack surface reduced to runtime deps only
FROM python:3.11-slim AS runtime

# 2. Non-root user (UID 1001, no shell)
RUN groupadd -r qfl && useradd -r -g qfl -u 1001 qfl
USER qfl

# 3. Read-only filesystem (tmpfs at /tmp only via docker-compose.yml)
# 4. No new privileges
```

### Docker Compose security settings

```yaml
security_opt:
  - no-new-privileges:true    # Process cannot gain new capabilities
read_only: true                # Root filesystem is read-only
tmpfs:
  - /tmp                      # Only /tmp is writable
```

### Kubernetes Pod Security

```yaml
containerSecurityContext:
  allowPrivilegeEscalation: false   # setuid/setgid blocked
  readOnlyRootFilesystem: true
  capabilities:
    drop: [ALL]                     # All Linux capabilities dropped
  runAsNonRoot: true
  runAsUser: 1001
```

---

## Tenant Isolation

### Docker Compose (development)

Each client runs on a dedicated bridge network:

```yaml
tenant_a_net: { driver: bridge, internal: true }
tenant_b_net: { driver: bridge, internal: true }
tenant_c_net: { driver: bridge, internal: true }
```

`internal: true` means containers on tenant networks cannot reach the internet.
Cross-tenant traffic is impossible since containers are on separate networks.

### Kubernetes (production)

`infra/networkpolicies/tenant-isolation.yaml` implements:

1. **Default deny all** — no traffic in or out of `qfl` namespace
2. **Coordinator ingress** — only Nginx ingress controller can reach port 8000
3. **Coordinator egress** — only to PostgreSQL (5432) and Redis (6379), plus DNS
4. **Tenant isolation** — each tenant namespace can only reach coordinator, never other tenants

Verify isolation:
```bash
# This should FAIL (cross-tenant blocked)
kubectl exec -n tenant-a deployment/client-a -- \
  curl http://client-b.tenant-b.svc.cluster.local:8000/health

# This should SUCCEED (coordinator access allowed)
kubectl exec -n tenant-a deployment/client-a -- \
  curl http://qfl-coordinator.qfl.svc.cluster.local:8000/health
```

---

## Data Security

### Model Weights

Clients never send raw model weights to the coordinator. They send:
- `weights_hash`: SHA-256 of the serialized weight tensor
- The actual weights are encrypted with the QKD key and transmitted over a
  separate secure channel (Phase 2 implementation)

This means the coordinator cannot recover individual client data from
the weight update alone.

### Differential Privacy

Ensures that the global model reveals nothing about any individual's data:

```
ε-differential privacy: For any two datasets D, D' differing in one record,
and any output S:

P[M(D) ∈ S] ≤ e^ε × P[M(D') ∈ S] + δ

With ε=1.0, δ=1e-5: very strong privacy guarantee.
```

The `DPBudget` class enforces per-tenant ε limits. Once exhausted,
no further rounds are accepted until the budget resets.

### Audit Log Integrity

PostgreSQL rules prevent any modification to `audit_log`:

```sql
CREATE RULE no_update_audit AS ON UPDATE TO audit_log DO INSTEAD NOTHING;
CREATE RULE no_delete_audit AS ON DELETE TO audit_log DO INSTEAD NOTHING;
```

For stronger guarantees in production, consider:
- Write to an append-only S3 bucket simultaneously
- Hash-chain entries (each log entry includes SHA-256 of the previous)
- Use PostgreSQL logical replication to a write-only replica

### GDPR Compliance

- **Zero raw data** leaves tenant namespace (only weight hashes transmitted)
- **IP addresses** are hashed before logging (SHA-256, not reversible)
- **Right to erasure**: POST an `erasure_request` audit event; model unlearning
  is queued (Phase 5 implementation via gradient reversal)
- **Data minimization**: audit log stores only what is required by EU AI Act

---

## Supply Chain Security

### SBOM and Provenance

The CI/CD pipeline builds Docker images with:

```yaml
- uses: docker/build-push-action@v5
  with:
    provenance: true   # SLSA provenance attestation
    sbom: true         # Software Bill of Materials
```

This generates a cryptographically signed attestation of what went into
the image, enabling downstream verification.

### Pre-commit Hooks

`.pre-commit-config.yaml` blocks commits with:

```
bandit      → Python SAST (SQL injection, shell injection, hardcoded passwords)
detect-private-key → blocks PEM/key files from being committed
ruff        → catches common Python security anti-patterns
mypy        → catches type errors that can lead to security issues
```

### Dependency Scanning

Trivy scans the container image in CI:

```yaml
- uses: aquasecurity/trivy-action@master
  with:
    severity: CRITICAL,HIGH
    exit-code: 0   # warn only (set to 1 for blocking)
```

For production: set `exit-code: 1` to block deployments with critical CVEs.

---

## Secrets Management

### Development

Use `.env` file (gitignored):
```bash
IBM_QUANTUM_TOKEN=your_token
POSTGRES_PASSWORD=strong_password
REDIS_PASSWORD=strong_password
GRAFANA_ADMIN_PASSWORD=strong_password
QFL_BACKUP_PASSPHRASE=encryption_passphrase
```

### Production (Kubernetes)

```bash
kubectl create secret generic qfl-secrets \
  --namespace qfl \
  --from-literal=ibm-quantum-token="$IBM_QUANTUM_TOKEN" \
  --from-literal=postgres-password="$POSTGRES_PASSWORD" \
  --from-literal=redis-password="$REDIS_PASSWORD"
```

Reference in Helm `values.yaml`:
```yaml
secrets:
  postgresPassword: ""   # populated from K8s secret
  ibmQuantumToken: ""
```

**Never** commit secrets to git. The pre-commit `detect-private-key` hook
and `.gitignore` provide two layers of protection.
