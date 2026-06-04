# Sri Demo BE - Kubernetes Deployment

Manifest Kubernetes untuk mendeploy aplikasi Sri Demo BE dengan konfigurasi production-ready.

## Struktur File

```
infra/
├── deployment.yaml          # Deployment dengan 2 replika
├── service.yaml             # ClusterIP Service
├── ingress.yaml             # Traefik IngressRoute
├── secrets.yaml             # Secret untuk credentials
├── tika-deployment.yaml     # Apache Tika untuk OCR
├── kustomization.yaml       # Kustomize configuration
└── README.md               # File ini
```

## Spesifikasi

### Deployment
- **Replicas**: 2 untuk high availability
- **Image**: `ghcr.io/danielyericho/sri_demo_registry:be-latest`
- **Port**: 8000 (HTTP)
- **Health Check**: Liveness & Readiness probe ke `/health`

### Ingress
- **Type**: Traefik IngressRoute
- **Hostname**: `sri-demo-api.saecloud.com`
- **Entry Points**: `web` dan `websecure`

### Resources
- **Requests**: 250m CPU, 512Mi Memory
- **Limits**: 500m CPU, 1Gi Memory

## Prerequisites

1. Kubernetes cluster yang sudah berjalan
2. Traefik Ingress Controller sudah terinstall
3. PostgreSQL instance (local atau managed service)
4. Elasticsearch instance (local atau Elastic Cloud)

## Deployment Steps

### 1. Konfigurasi Secrets

Buka `secrets.yaml` dan update nilai-nilai:

```bash
cd infra/
vim secrets.yaml
```

Ubah nilai untuk:
- `database-url`: PostgreSQL connection string
- `elasticsearch-url`: URL Elasticsearch
- `elasticsearch-api-key`: API key (jika menggunakan Elastic Cloud)

### 2. Deploy menggunakan kubectl

```bash
# Apply semua manifest
kubectl apply -k .

# Atau manual apply per file
kubectl apply -f secrets.yaml
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl apply -f tika-deployment.yaml
kubectl apply -f ingress.yaml
```

### 3. Verifikasi Deployment

```bash
# Cek status deployment
kubectl get deployment sri-demo-be

# Lihat pods
kubectl get pods -l app=sri-demo-be

# Lihat logs
kubectl logs -f deployment/sri-demo-be

# Cek service
kubectl get svc sri-demo-be

# Cek ingress
kubectl get ingressroute
```

## Konfigurasi Ingress

### Update Hostname

Edit `ingress.yaml` dan ubah hostname:

```yaml
match: Host(`your-domain.com`)
```

### Enable HTTPS/TLS

Uncomment bagian TLS dan konfigurasi cert resolver:

```yaml
tls:
  certResolver: letsencrypt
  domains:
  - main: sri-demo-api.saecloud.com
```

## Environment Variables

Semua environment variable diatur di Deployment:

| Variable | Source | Default |
|----------|--------|---------|
| `DATABASE_URL` | Secret | Required |
| `ELASTICSEARCH_URL` | Secret | Required |
| `ELASTICSEARCH_API_KEY` | Secret | Optional (Elastic Cloud) |
| `TIKA_ENDPOINT` | Hardcoded | `http://sri-demo-tika:9998/tika` |
| `TIKA_PDF_OCR_ENABLED` | Hardcoded | `true` |
| `TIKA_OCR_LANGUAGE` | Hardcoded | `eng+ind` |
| `TIKA_OCR_MAX_FILE_SIZE` | Hardcoded | `52428800` (50MB) |

## Scaling

### Scale Replicas

```bash
kubectl scale deployment sri-demo-be --replicas=3
```

### Update Image

```bash
kubectl set image deployment/sri-demo-be \
  sri-demo-be=ghcr.io/danielyericho/sri_demo_registry:be-v2.0.0
```

## Monitoring

### Pod Logs

```bash
# Tail logs
kubectl logs -f deployment/sri-demo-be

# Specific pod
kubectl logs -f pod/sri-demo-be-xxxx
```

### Events

```bash
kubectl describe deployment sri-demo-be
kubectl describe pod <pod-name>
```

### Health Check

```bash
# Port forward untuk testing
kubectl port-forward svc/sri-demo-be 8000:80

# Test health endpoint
curl http://localhost:8000/health

# Test API docs
curl http://localhost:8000/docs
```

## Troubleshooting

### Pod tidak starting

```bash
# Lihat detail pod
kubectl describe pod <pod-name>

# Lihat logs
kubectl logs <pod-name>

# Debug ke pod
kubectl exec -it <pod-name> -- sh
```

### Secret tidak ditemukan

```bash
# Verifikasi secret exists
kubectl get secrets sri-demo-secrets

# Lihat isi secret
kubectl describe secret sri-demo-secrets
```

### Ingress tidak working

```bash
# Verifikasi ingress route
kubectl get ingressroute

# Cek traefik logs
kubectl logs -f -n traefik deployment/traefik

# Describe ingress route
kubectl describe ingressroute sri-demo-be
```

## Cleanup

```bash
# Delete semua resources
kubectl delete -k .

# Atau manual
kubectl delete deployment sri-demo-be
kubectl delete svc sri-demo-be
kubectl delete ingressroute sri-demo-be
kubectl delete secret sri-demo-secrets
```

## Notes

- Pods menggunakan `podAntiAffinity` untuk distribusi optimal
- Storage volumes menggunakan `emptyDir` untuk logs dan storage (temporary)
- Untuk persistent storage, gunakan PersistentVolumeClaim
- Health check timeout 5s, initial delay 90s untuk startup
- Image pull policy `Always` untuk latest image
