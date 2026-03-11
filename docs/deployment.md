# QFL Platform — Deployment Guide

## Environments

| Environment | How | When |
|---|---|---|
| **Local dev** | `make dev` (uvicorn --reload) | Feature development |
| **Local full stack** | `make docker-up` | Integration testing |
| **Staging** | kind cluster via CI/CD | Pre-merge validation |
| **Production** | Kubernetes (Helm) | Real workloads |

---

## Local Development

```bash
# Install
make install

# Start coordinator only (hot-reload)
make dev
# → http://localhost:8000/docs

# Run all tests
make test

# Lint
make lint

# Format code
make format
```

---

## Docker Compose (Full Stack)

```bash
# Create .env file
cat > .env << 'EOF'
IBM_QUANTUM_TOKEN=
GRAFANA_ADMIN_PASSWORD=admin
POSTGRES_PASSWORD=qfl_secret
REDIS_PASSWORD=redis_secret
QFL_BACKUP_PASSPHRASE=changeme
EOF

# Start all 7 services
make docker-up

# Verify health
curl http://localhost:8000/health

# View all logs
make docker-logs

# Stop and remove volumes
make docker-down
```

### Service URLs

| Service | URL | Notes |
|---|---|---|
| Coordinator API | http://localhost:8000 | FastAPI |
| Swagger UI | http://localhost:8000/docs | Interactive API |
| Prometheus | http://localhost:9090 | Metrics |
| Grafana | http://localhost:3000 | Dashboards (admin/admin) |

---

## Kubernetes with Helm

### Prerequisites

```bash
# Install tools
brew install kubectl helm kind

# Create local cluster (or use your cloud cluster)
kind create cluster --name qfl

# Verify
kubectl cluster-info --context kind-qfl
```

### Deploy coordinator

```bash
# Add dependencies (PostgreSQL + Redis sub-charts)
helm dependency update infra/helm/coordinator

# Deploy to qfl namespace
helm upgrade --install qfl-coordinator infra/helm/coordinator \
  --namespace qfl \
  --create-namespace \
  --set image.tag=latest \
  --set secrets.postgresPassword=strong_password \
  --set secrets.redisPassword=strong_password \
  --wait \
  --timeout 5m

# Verify
kubectl get pods -n qfl
kubectl get svc -n qfl
```

### Port-forward for local access

```bash
kubectl port-forward -n qfl svc/qfl-coordinator 8000:8000 &
curl http://localhost:8000/health
```

### Apply tenant isolation

```bash
kubectl apply -f infra/networkpolicies/tenant-isolation.yaml

# Verify isolation (should fail)
kubectl run test --image=alpine --rm -it \
  --namespace=tenant-a \
  -- wget -qO- http://client-b.tenant-b.svc.cluster.local:8000/health
# → Connection refused (blocked by NetworkPolicy)
```

### Scaling

The Helm chart includes HPA (Horizontal Pod Autoscaler):

```bash
# Manual scale
kubectl scale deployment qfl-coordinator -n qfl --replicas=5

# Check HPA
kubectl get hpa -n qfl
# Autoscales 2–10 replicas at 70% CPU
```

---

## CI/CD Pipeline

The GitHub Actions workflow (`.github/workflows/ci.yml`) runs automatically.

### Triggering manually

```bash
# Push to develop triggers lint + tests
git push origin develop

# Push to main triggers full pipeline + deployment
git push origin main
```

### Required GitHub Secrets

| Secret | Description |
|---|---|
| `CODECOV_TOKEN` | Coverage upload (optional) |
| `IBM_QUANTUM_TOKEN` | IBM Quantum connection (optional) |

GitHub automatically provides `GITHUB_TOKEN` for GHCR image push.

---

## Backup & Recovery

### Scheduled backup (cron)

```bash
# Run daily at 2 AM
echo "0 2 * * * QFL_S3_BACKUP_BUCKET=s3://your-bucket QFL_BACKUP_PASSPHRASE=passphrase /path/to/infra/backup/backup.sh" | crontab -

# Or as a Kubernetes CronJob
kubectl apply -f - << 'EOF'
apiVersion: batch/v1
kind: CronJob
metadata:
  name: qfl-backup
  namespace: qfl
spec:
  schedule: "0 2 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: backup
              image: qfl-coordinator:latest
              command: ["/app/infra/backup/backup.sh"]
              env:
                - name: QFL_S3_BACKUP_BUCKET
                  value: "s3://your-bucket"
          restartPolicy: OnFailure
EOF
```

### Manual restore

```bash
# List available backups
aws s3 ls s3://your-bucket/backups/

# Restore a specific backup
QFL_S3_BACKUP_BUCKET=s3://your-bucket \
QFL_BACKUP_PASSPHRASE=passphrase \
./infra/backup/restore.sh 20260311_020000
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `IBM_QUANTUM_TOKEN` | — | IBM Quantum API token |
| `POSTGRES_DSN` | `postgresql+asyncpg://qfl:qfl_secret@postgres:5432/qfldb` | Database connection |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `PORT` | `8000` | Coordinator listen port |
| `GRAFANA_ADMIN_PASSWORD` | `admin` | Grafana admin password |
| `QFL_S3_BACKUP_BUCKET` | — | S3 bucket for backups |
| `QFL_BACKUP_PASSPHRASE` | `changeme` | GPG passphrase for backup encryption |
| `QFL_BACKUP_RETENTION_DAYS` | `30` | Days to keep backups in S3 |

---

## Production Checklist

Before deploying to production:

- [ ] Set strong passwords for PostgreSQL, Redis, Grafana
- [ ] Generate real TLS certificates (Let's Encrypt or corporate CA)
- [ ] Store IBM Quantum token in Kubernetes secret, not environment variable
- [ ] Set `exit-code: 1` in Trivy scan to block deployments with critical CVEs
- [ ] Enable HSTS preload in Nginx (already configured in `nginx.conf`)
- [ ] Set `GF_ANALYTICS_REPORTING_ENABLED=false` in Grafana (already configured)
- [ ] Configure S3 bucket with versioning + MFA delete for backups
- [ ] Set up PagerDuty / Alertmanager for Prometheus alerts
- [ ] Review and tighten CSP headers for your specific domains
- [ ] Set `POSTGRES_PASSWORD` to a cryptographically random value (32+ chars)
- [ ] Enable PostgreSQL SSL (`sslmode=require` in `POSTGRES_DSN`)
- [ ] Set Redis `maxmemory` and `maxmemory-policy` appropriate to your workload
- [ ] Rotate `QFL_BACKUP_PASSPHRASE` every 90 days
