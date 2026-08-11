# JURYAI — Intelligent Legal Research Assistant

JURYAI is a Retrieval-Augmented Generation (RAG) system for legal document analysis and Q&A. It combines semantic search (Qdrant), full-text search (Quickwit), and LLM inference to answer complex legal questions with cited sources.

## Prerequisites

- **Python 3.12+** with `uv` package manager
- **Docker** and **Docker Compose** (for Qdrant and Quickwit)
- **Node.js 18+** (for frontend)
- **PostgreSQL 13+** (reused from legal-platform)
- **Redis** (reused from legal-platform)

### Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Quick Start

### 1. Start Infrastructure

JURYAI runs two search backends (Qdrant and Quickwit) independently:

```bash
cd /home/jishh/Desktop/legal-platform
docker compose -f JURYAI/docker-compose.juryai.yml up -d
```

Verify services are healthy:
```bash
docker ps --filter "label=io.docker.compose.project=legal-platform"
curl http://localhost:6333/livez    # Qdrant
curl http://localhost:7280/health   # Quickwit
```

### 2. Configure Environment

Copy the example environment file and fill in API keys:

```bash
cd JURYAI/backend
cp .env.juryai.example .env
# Edit .env and add:
#   - OPENAI_API_KEY or GROQ_API_KEY or MISTRAL_API_KEY
#   - AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY (for S3)
#   - TAVILY_API_KEY or BRAVE_SEARCH_API_KEY (optional, for web search)
nano .env
```

### 3. Start Backend

```bash
cd JURYAI/backend
uv sync                                    # Install dependencies
uv run python -m app.main                 # Starts on http://localhost:8100
```

Check health:
```bash
curl http://localhost:8100/health
```

API endpoints:
- `POST /api/v1/chat` — Synchronous Q&A (returns full response)
- `POST /api/v1/chat/stream` — Server-Sent Events streaming (for progressive UI updates)

### 4. Start Frontend

```bash
cd JURYAI/frontend
npm install                                # Install dependencies
npm run dev                                # Starts on http://localhost:5174
```

Open http://localhost:5174 in your browser.

## Architecture

### Backend (FastAPI)

- **State Machine** (`app/core/graph/workflow.py`): LangGraph-based workflow orchestrating intent classification, retrieval, evidence merging, and answer generation.
- **Search** (`app/services/qdrant_service.py`, `app/services/quickwit_service.py`): Vector and full-text search over legal documents.
- **LLM Integration** (`app/services/llm_router.py`): Routes to available LLM providers (Groq, Mistral, OpenAI, Anthropic).
- **API** (`app/api/v1/chat.py`): REST and SSE endpoints with error handling.

### Frontend (React + TypeScript)

- **Chat Panel**: Real-time message streaming with citation highlights.
- **Source Panel**: Document browser with page-level navigation.
- **Settings Drawer**: Model selection, web search toggle, theme switch.

### Storage

- **Qdrant**: Vector embeddings for semantic search (~384-dim vectors, `juryai_legal` collection).
- **Quickwit**: Full-text index for keyword search (`juryai_legal` index).
- **PostgreSQL**: Document metadata and conversation history (via legal-platform).

## Development

### Run Tests

```bash
cd JURYAI/backend
uv run pytest tests/ -v
```

### Code Quality

```bash
cd JURYAI/backend
uv run ruff check app/
uv run mypy app/ --no-error-summary 2>&1 | head -20  # First 20 type errors
```

## Environment Variables Reference

| Variable | Required | Example |
|----------|----------|---------|
| `GROQ_API_KEY` | No* | `gsk_...` |
| `OPENAI_API_KEY` | No* | `sk-...` |
| `MISTRAL_API_KEY` | No* | `api_...` |
| `ANTHROPIC_API_KEY` | No* | `sk-ant-...` |
| `TAVILY_API_KEY` | No | (for Tavily web search) |
| `QDRANT_URL` | Yes | `http://localhost:6333` |
| `QDRANT_COLLECTION` | Yes | `juryai_legal` |
| `QUICKWIT_URL` | Yes | `http://localhost:7280` |
| `QUICKWIT_INDEX` | Yes | `juryai_legal` |
| `AWS_ACCESS_KEY_ID` | Yes | (for S3 document retrieval) |
| `AWS_SECRET_ACCESS_KEY` | Yes | (for S3 document retrieval) |
| `S3_BUCKET_NAME` | Yes | `legal-platform-docs` |
| `POSTGRES_HOST` | Yes | `localhost` |
| `REDIS_URL` | Yes | `redis://localhost:6379/1` |

*At least one LLM API key is required.

## Troubleshooting

### Backend won't start
```bash
# Check ports are free
lsof -i :8100
# Check dependencies
uv sync --refresh
# Check logs
docker compose -f JURYAI/docker-compose.juryai.yml logs
```

### No search results
- Verify Qdrant and Quickwit are healthy
- Check that documents are indexed (via legal-platform backfill scripts)
- Try a different query with more specific keywords

### LLM errors
- Verify API key is set and has quota
- Check network/firewall allows outbound to LLM provider
- See backend logs for detailed error

## License

Part of the legal-platform monorepo. See root `LICENSE` for details.
