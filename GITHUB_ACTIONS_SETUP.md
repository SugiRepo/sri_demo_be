# GitHub Actions Setup: Build & Deploy to GHCR

## Workflow Overview
Workflow ini melakukan dua step otomatis saat ada push/merge ke branch `staging`:

1. **Build Step**: Build Docker image dan push ke GHCR menggunakan PAT
2. **Deploy Step**: Update deployment image dan trigger rolling restart pod tanpa downtime

## Setup yang Diperlukan

### 1. GitHub Secrets Configuration
Tambahkan secret berikut di GitHub Repository Settings > Secrets and variables > Actions:

- **`KUBE_CONFIG`**: Base64-encoded kubeconfig file
  ```bash
  # Generate:
  cat ~/.kube/config | base64 -w 0 | pbcopy
  ```

- **`GITHUB_TOKEN`**: Default secret yang sudah ada di setiap GitHub repo (tidak perlu dikonfigurasi manual)

### 2. Kubernetes Configuration
Secrets sudah ditambahkan ke `infra/secrets.yaml`:

- **`sri-demo-secrets`**: Application secrets (database, elasticsearch, api-keys)
- **`ghcr-pull-secret`**: Docker registry credentials untuk pull dari GHCR

#### Apply secrets ke cluster:
```bash
kubectl apply -f infra/secrets.yaml
```

### 3. Deployment Configuration
`infra/deployment.yaml` sudah di-update dengan:

- **`imagePullSecrets`**: Reference ke `ghcr-pull-secret` untuk pull image dari GHCR
- **`image`**: Updated ke `ghcr.io/sugiRepo/sri_demo_be:be-latest`

## Workflow Steps Breakdown

### Build Step (`build` job)
- Checkout code dari staging branch
- Setup Docker Buildx untuk building multi-platform images
- Login ke GHCR dengan GitHub token
- Generate image tag dengan format: `staging-{short-sha}-{timestamp}`
- Build dan push image dengan 2 tags:
  - `ghcr.io/sugiRepo/sri_demo_be:staging-{short-sha}-{timestamp}` (unique tag)
  - `ghcr.io/sugiRepo/sri_demo_be:be-latest` (latest tag untuk rolling update)

### Deploy Step (`deploy` job)
- Depends on `build` job (berjalan setelah build selesai)
- Setup kubectl dan configure context menggunakan KUBE_CONFIG secret
- Update deployment image ke `be-latest` menggunakan `kubectl set image`
- Trigger rolling restart dengan update annotation (no downtime strategy):
  - Menambah annotation `deployment.kubernetes.io/restart` dengan timestamp
  - Ini memicu rolling restart pod tanpa merubah replicas
- Verify rollout status (timeout 5 menit)

## Cara Kerja Rolling Restart (No Downtime)

```bash
# Step 1: Set new image
kubectl set image deployment/sri-demo-be-deployment \
  sri-demo-be=ghcr.io/sugiRepo/sri_demo_be:be-latest \
  -n default

# Step 2: Trigger rolling restart dengan annotation
kubectl patch deployment sri-demo-be-deployment \
  -p "{\"spec\":{\"template\":{\"metadata\":{\"annotations\":{\"deployment.kubernetes.io/restart\":\"$(date +%s)\"}}}}}" \
  -n default

# Step 3: Monitor
kubectl rollout status deployment/sri-demo-be-deployment -n default --timeout=5m
```

Karena deployment sudah dikonfigurasi dengan:
- `replicas: 2`
- `maxSurge: 1` (dapat scale up 1 pod)
- `maxUnavailable: 0` (tidak ada pod yang di-terminate dulu)

Proses rolling update dijamin tanpa downtime.

## Trigger Workflow

Workflow otomatis trigger ketika:
1. Push/Merge ke branch `staging`

Atau bisa trigger manual di GitHub Actions tab.

## Monitoring

1. **GitHub Actions Tab**: Lihat progress build dan deploy
2. **Kubernetes**: Monitor pod status
   ```bash
   kubectl get deployment sri-demo-be-deployment -w
   kubectl get pods -l app=sri-demo-be -w
   kubectl logs -l app=sri-demo-be -f
   ```

## Security Notes

⚠️ **IMPORTANT**: PAT sudah disimpan dalam workflow file. Untuk production:
1. Rotate PAT secara berkala
2. Pertimbangkan menggunakan GitHub App Authentication
3. Gunakan branch protection rules untuk staging branch
4. Audit access ke GitHub Secrets

## Troubleshooting

### Image Pull Failed
```bash
# Check if secret exists
kubectl get secret ghcr-pull-secret -n default

# Check pod events
kubectl describe pod <pod-name> -n default
```

### Deploy Stuck
```bash
# Check rollout status
kubectl rollout status deployment/sri-demo-be-deployment -n default

# Rollback if needed
kubectl rollout undo deployment/sri-demo-be-deployment -n default
```

### Pod Not Restarting
- Pastikan annotation format benar
- Check deployment events: `kubectl describe deployment sri-demo-be-deployment`
