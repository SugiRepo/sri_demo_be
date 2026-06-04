# Secrets Management Guide

File ini adalah template untuk membuat `secrets.yaml` yang berisi credential sensitif.

## ⚠️ IMPORTANT
- File `secrets.yaml` adalah **LOCAL ONLY** dan **NOT tracked** di git (lihat `.gitignore`)
- **JANGAN pernah commit** secrets.yaml ke repository
- Setiap developer/environment harus membuat secrets.yaml sendiri dengan nilai yang sesuai

## Cara Membuat secrets.yaml

### Option 1: Manual Copy-Paste (Recommended untuk testing)

```bash
# Copy dari template
cp infra/secrets.yaml.example infra/secrets.yaml

# Edit dengan editor
nano infra/secrets.yaml
# atau
code infra/secrets.yaml

# Ganti semua placeholder dengan nilai actual
```

### Option 2: Automated dari Environment Variables

```bash
# Set environment variables
export DATABASE_URL="postgresql://user:pass@host:5432/db"
export ELASTICSEARCH_URL="https://xxxx.cloud.elastic-cloud.com:443"
export ELASTICSEARCH_API_KEY="your-api-key"
export API_KEYS="your-api-keys"
export GHCR_USERNAME="github-username"
export GHCR_PAT="ghp_xxxxxxxxxxxx"
export GHCR_AUTH="base64-encoded-username:pat"

# Generate secrets.yaml
./infra/generate-secrets.sh
```

## Required Values

### Database Connection
```
DATABASE_URL: postgresql://sri_demo:password@172.16.0.65:5432/sri_demo
```

### Elasticsearch
```
ELASTICSEARCH_URL: https://xxxx.cloud.elastic-cloud.com:443
ELASTICSEARCH_API_KEY: base64-encoded-key
```

### Application API Keys
```
API_KEYS: your-api-key-here
```

### GitHub Container Registry (GHCR)
```
GHCR_USERNAME: SugiRepo
GHCR_PAT: ghp_xxxxxxxxxxxxxxxx
GHCR_AUTH: base64(username:pat)
```

Generate GHCR_AUTH dengan command:
```bash
echo -n "SugiRepo:ghp_xxxxxxxxxxxxxxxx" | base64
```

## Apply ke Kubernetes

Setelah membuat secrets.yaml:

```bash
# Apply secrets ke cluster
kubectl apply -f infra/secrets.yaml

# Verify
kubectl get secrets -n default | grep sri-demo
kubectl describe secret sri-demo-secrets -n default
kubectl describe secret ghcr-pull-secret -n default
```

## GitHub Secrets Setup

Untuk GitHub Actions workflow, setup secrets di GitHub Repository:

1. Go to: **Settings > Secrets and variables > Actions**

2. Add these secrets:
   - `KUBE_CONFIG`: Base64-encoded kubeconfig
     ```bash
     cat ~/.kube/config | base64 -w 0
     ```

3. Workflow akan automatically login ke GHCR menggunakan `GITHUB_TOKEN` (built-in)

## Security Best Practices

1. **Never commit secrets** - selalu pastikan di `.gitignore`
2. **Rotate credentials** - ganti PAT dan credentials secara berkala
3. **Use strong passwords** - untuk database dan API credentials
4. **Limit access** - hanya share secrets dengan yang butuh
5. **Audit trail** - monitor yang access secrets di cluster:
   ```bash
   kubectl audit log | grep secrets
   ```

## Troubleshooting

### Secret Not Found
```bash
# Check if secret exists
kubectl get secret sri-demo-secrets -n default

# If not found, create it
kubectl apply -f infra/secrets.yaml
```

### Pod Image Pull Failed
```bash
# Check if GHCR pull secret exists
kubectl get secret ghcr-pull-secret -n default

# Check pod events
kubectl describe pod <pod-name> -n default

# Check imagePullSecrets in deployment
kubectl get deployment sri-demo-be -o yaml | grep -A 2 imagePullSecrets
```

### Base64 Decode untuk Verify
```bash
# Decode ELASTICSEARCH_API_KEY
kubectl get secret sri-demo-secrets -n default -o jsonpath="{.data.elasticsearch-api-key}" | base64 -d

# Decode GHCR auth
kubectl get secret ghcr-pull-secret -n default -o jsonpath="{.data.\.dockercfg}" | base64 -d | jq
```

## References

- [Kubernetes Secrets Documentation](https://kubernetes.io/docs/concepts/configuration/secret/)
- [Docker Credentials](https://docs.docker.com/engine/reference/commandline/login/)
- [GitHub Personal Access Tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
