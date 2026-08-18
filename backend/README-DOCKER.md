# JuryAI Backend - Docker Deployment

One-shot deployment of the complete JuryAI legal RAG backend with all dependencies.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Network                            │
├─────────────┬─────────────┬─────────────┬─────────────┬────────┤
│  Backend    │  Postgres   │   Valkey    │   Qdrant    │ Quickwit│
│  (API)      │  (pgvector) │  (Cache)    │  (Vectors)  │ (BM25) │
│  :8000      │  :5432      │  :6379      │  :6333      │ :7280  │
└─────────────┴─────────────┴─────────────┴─────────────┴────────┘
         │
         ▼
┌─────────────────────┐
│   Lightpanda        │
│  (Headless Browser) │
│    :9222            │
└─────────────────────┘
```

## Quick Start

### 1. Prerequisites
- Docker Engine 24+
- Docker Compose v2 (included with Docker Desktop)
- 8GB+ RAM available for containers
- 10GB+ disk space for models and data

### 2. Configure Environment
```bash
cd backend
cp .env.example .env
# Edit .env with your API keys:
# - GROQ_API_KEY, MISTRAL_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY
# - TAVILY_API_KEY, BRAVE_SEARCH_API_KEY (for web search)
# - AWS credentials (for S3 document ingestion)
# - SECRET_KEY (generate a strong random key)
```

### 3. Start All Services
```bash
# Make startup script executable (first time only)
chmod +x start.sh

# Start everything
./start.sh up
```

This will:
1. Pull latest base images
2. Build the backend image with all ML dependencies
3. Start PostgreSQL, Valkey, Qdrant, Quickwit, Lightpanda
4. Start the backend API
5. Wait for all health checks to pass

### 4. Verify Deployment
```bash
# Check status
./start.sh status

# View logs
./start.sh logs

# Test API
curl http://localhost:8000/health
```

## Service Endpoints

| Service | URL | Purpose |
|---------|-----|---------|
| Backend API | http://localhost:8000 | Main API (REST + SSE streaming) |
| API Docs | http://localhost:8000/docs | Swagger UI |
| Qdrant Dashboard | http://localhost:6333/dashboard | Vector DB UI |
| Quickwit UI | http://localhost:7280 | Search engine UI |
| PostgreSQL | localhost:5432 | Audit logs, metadata |
| Valkey | localhost:6379 | Caching, sessions, rate limiting |
| Lightpanda | http://localhost:9222 | Headless browser for scraping |

## Common Commands

```bash
# Start services
./start.sh up

# Stop services
./start.sh down

# View all logs
./start.sh logs

# View specific service logs
./start.sh logs backend
./start.sh logs qdrant

# Restart a service
./start.sh restart backend

# Check status and resource usage
./start.sh status

# Rebuild backend (after code changes)
./start.sh build

# Pull latest base images
./start.sh pull

# Complete cleanup (removes all data!)
./start.sh clean
```

## Configuration

### Required API Keys (in `.env`)

| Variable | Purpose | Required |
|----------|---------|----------|
| `GROQ_API_KEY` | Fast LLM inference (fallback) | Yes* |
| `MISTRAL_API_KEY` | Mistral models (fallback) | Yes* |
| `OPENAI_API_KEY` | OpenAI models (fallback) | Yes* |
| `ANTHROPIC_API_KEY` | Claude models (fallback) | Yes* |
| `TAVILY_API_KEY` | Web search | No |
| `BRAVE_SEARCH_API_KEY` | Web search | No |
| `GATEWAY_URL` | LLM Gateway (260+ models) | No |
| `GATEWAY_KEY` | Gateway auth | No |
| `AWS_ACCESS_KEY_ID` | S3 document ingestion | No |
| `AWS_SECRET_ACCESS_KEY` | S3 document ingestion | No |
| `S3_BUCKET_NAME` | Source documents bucket | No |

*At least one LLM provider key is required.

### Model Configuration

```env
# Embedding model (768-dim, legal-tuned)
EMBED_MODEL=nlpaueb/legal-bert-base-uncased

# Cross-encoder reranker (22M params, fast)
RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L6-v2

# ColBERT late interaction (optional)
COLBERT_MODEL=colbert-ir/colbertv2.0
```

### Retrieval Tuning

```env
# How many chunks to retrieve initially
TOP_K_RETRIEVE=20

# Final chunks after reranking
TOP_K_FINAL=10

# Reranker token limit
RERANKER_MAX_LENGTH=512
RERANKER_BATCH_SIZE=8

# ColBERT second-stage candidates
COLBERT_TOP_K=50
COLBERT_MAX_LENGTH=180
```

### Authority Scoring Weights (must sum to 1.0)

```env
AUTHORITY_SCORE_ALPHA=0.50   # Query relevance
AUTHORITY_SCORE_BETA=0.25    # Citation graph PageRank
AUTHORITY_SCORE_GAMMA=0.15   # Recency decay
AUTHORITY_SCORE_DELTA=0.10   # Citation count quality
```

## Data Persistence

All data is stored in Docker volumes:

| Volume | Contents |
|--------|----------|
| `postgres_data` | Audit logs, conversations, ingestion manifest |
| `valkey_data` | Cache, rate limits, sessions |
| `qdrant_data` | Vector embeddings, payload |
| `quickwit_data` | BM25 index, metastore |
| `model_cache` | HuggingFace model cache (shared) |
| `document_cache` | Downloaded PDF cache |
| `session_store` | Per-session uploaded documents |

## S3 Document Ingestion

1. Configure AWS credentials and bucket in `.env`
2. Place PDFs in S3 under `S3_DOCUMENT_PREFIX` (default: `documents/`)
3. Trigger ingestion:
```bash
curl -X POST http://localhost:8000/api/v1/ingest/s3 \
  -H "Content-Type: application/json" \
  -d '{"prefix_filter": "", "sync_only": true}'
```
4. Check status:
```bash
curl http://localhost:8000/api/v1/ingest/status
```

## Health Checks

All services have health checks. The startup script waits for all to pass.

Manual checks:
```bash
# Backend
curl http://localhost:8000/health

# Qdrant
curl http://localhost:6333/health

# Quickwit
curl http://localhost:7280/health

# PostgreSQL
docker exec voidrag-postgres pg_isready -U postgres -d juryai

# Valkey
docker exec voidrag-valkey valkey-cli ping
```

## Troubleshooting

### Backend fails to start
```bash
# Check logs
./start.sh logs backend

# Common issues:
# - Missing API keys in .env
# - Port 8000 already in use
# - Insufficient memory (need 4GB+ for backend)
```

### Qdrant/Quickwit unhealthy
```bash
# Check logs
./start.sh logs qdrant
./start.sh logs quickwit

# Increase memory limits in docker-compose.yml if needed
```

### Model download fails
```bash
# Models are downloaded on first run to model_cache volume
# Check disk space: df -h
# Clear cache: docker volume rm backend_model_cache
```

### Out of memory
```bash
# Reduce memory limits in docker-compose.yml:
# - backend: 6G → 4G
# - qdrant: 2G → 1G
# - quickwit: 2G → 1G

# Or disable ColBERT:
COLBERT_MODEL=
```

## Production Deployment

For production, consider:

1. **Use external managed services:**
   - PostgreSQL: AWS RDS, Cloud SQL, Azure Database
   - Valkey/Redis: ElastiCache, Memorystore
   - Qdrant: Qdrant Cloud
   - Quickwit: Quickwit Cloud

2. **Set strong secrets:**
```env
SECRET_KEY=your-256-bit-random-key
POSTGRES_PASSWORD=strong-random-password
```

3. **Enable TLS:**
   - Use reverse proxy (nginx, Traefik) with Let's Encrypt
   - Configure Qdrant/Quickwit with TLS

4. **Resource limits:**
   - Set appropriate CPU/memory limits
   - Configure autoscaling for backend

5. **Monitoring:**
   - Add Prometheus metrics endpoint
   - Configure logging aggregation (ELK, Loki)
   - Set up alerting for health checks

## Development Mode

For local development with hot reload:

```bash
# Override backend to use local code
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

Create `docker-compose.dev.yml`:
```yaml
services:
  backend:
    volumes:
      - ./app:/app/app:ro
      - ./alembic:/app/alembic:ro
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    environment:
      PYTHONUNBUFFERED: 1
```

## License

MIT License - See LICENSE file for details.