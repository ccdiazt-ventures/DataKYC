# DataKYC

Document data extraction API for KYC onboarding powered by local Vision AI on DGX Spark.

Extracts structured data from Mexican identity and financial documents using Granite Vision 4.1 (OCR) and Gemma4 26B (cross-validation). Multi-tenant with tiered API key access — built for SOFOMes, fintechs, and compliance workflows.

## Architecture

```
Client → pfSense HAProxy (SSL wildcard) → nginx :80 → FastAPI :8002
                                                         ├── PostgreSQL 16
                                                         ├── Redis 7
                                                         ├── Granite Vision 4.1 (Spark :8004)
                                                         └── Gemma4 26B (Spark :8003)
```

## Features

- **7 document types**: INE (front/back), CURP, Passport, RFC, Proof of Address, Bank Statement
- **Vision AI extraction**: Granite Vision 4.1 4B ~92% accuracy on Mexican IDs
- **Cross-validation**: Gemma4 26B validates extracted data consistency
- **KYC form filling**: Maps extracted fields to CNBV/SOFOM form templates
- **Tier system**: FREE → BASIC → PRO → ENTERPRISE with per-endpoint feature gates
- **JWT Auth** for dashboard + **API Key** auth for programmatic access
- **Self-service**: Organizations register themselves via the web UI

## Quick Start

```bash
# Clone
git clone https://github.com/ccdiazt-ventures/DataKYC.git
cd DataKYC

# Configure
cp .env.example .env
# Edit .env with your Spark URLs and secrets

# Start
docker compose up -d --build
```

Open `http://localhost:80` and register an organization.

## Tiers

| Tier | Docs/month | Document Types | Cross-Validation | Form Fill |
|------|-----------|----------------|-----------------|-----------|
| FREE | 10 | INE front | ✗ | ✗ |
| BASIC | 100 | + INE back, CURP, RFC | ✗ | ✓ |
| PRO | 1000 | + Passport, Proof of Address, Bank Statement | ✓ | ✓ |
| ENTERPRISE | ∞ | All + batch | ✓ | ✓ |

## API Endpoints

### Public
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/health` | Health check with Spark model status |
| `POST` | `/api/v1/auth/login` | Login with email + password → JWT |
| `POST` | `/api/v1/admin/organizations` | Register new organization |

### Authenticated (JWT)
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/auth/me` | Current org info + API keys |
| `POST` | `/api/v1/admin/api-keys` | Create API key |
| `GET` | `/api/v1/admin/api-keys` | List your API keys |
| `POST` | `/api/v1/admin/api-keys/revoke` | Revoke API key |
| `GET` | `/api/v1/admin/usage` | Extraction usage stats |
| `GET` | `/api/v1/admin/quota` | Monthly quota status |

### API Key Required
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/extract/{doc_type}` | Extract data from document image |
| `POST` | `/api/v1/verify/ine-data` | Cross-validate INE data with Gemma4 (PRO+) |
| `POST` | `/api/v1/fill-form` | Fill KYC form from extracted data (BASIC+) |

## API Usage Example

```bash
# Extract INE data
curl -X POST https://datakyc.rockyguard.com/api/v1/extract/INE_FRONT \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dkc_live_xxxxxxxx" \
  -d '{"image_base64": "<base64-encoded-jpeg>"}'

# Response
{
  "document_type": "INE_FRONT",
  "status": "SUCCESS",
  "source_model": "granite-vision:4b",
  "fields": {
    "nombre": "CESAR CARLOS",
    "apellido_paterno": "DIAZ",
    "apellido_materno": "TORREJON",
    "curp": "DITC880211HDFZRS09",
    "clave_elector": "DITCDZ88021109H700",
    ...
  },
  "confidence_scores": { "curp": 1.0, "nombre": 0.95, ... },
  "overall_confidence": 0.92,
  "processing_time_ms": 5023
}
```

## Requirements

- Docker 24+ with Compose v2
- DGX Spark (or any server) running:
  - Granite Vision 4.1 at `:8004` (vLLM with `vllm/vllm-openai:nightly`)
  - Gemma4 26B at `:8003` (optional, for cross-validation)
- PostgreSQL and Redis containers are included in docker-compose

## Project Structure

```
DataKYC/
├── app/
│   ├── api/v1/          # Route handlers
│   │   ├── auth.py      # Login, JWT
│   │   ├── admin.py     # Org management, API keys, usage
│   │   ├── extract.py   # Document extraction
│   │   ├── verify.py    # Cross-validation
│   │   └── fill_form.py # KYC form filling
│   ├── models/          # SQLAlchemy models
│   ├── schemas/         # Pydantic schemas
│   ├── services/        # Business logic
│   │   ├── vision_client.py  # Granite Vision + Gemma4 HTTP client
│   │   ├── tier_service.py   # Tier checks, quotas
│   │   └── form_filler.py    # KYC template mapping
│   ├── middleware/       # API key auth, rate limiting
│   └── main.py           # FastAPI app
├── nginx/                # Reverse proxy config
├── web/                  # Frontend (Vanilla JS + Tailwind)
├── tests/
├── docker-compose.yml
└── Dockerfile
```

## License

MIT
