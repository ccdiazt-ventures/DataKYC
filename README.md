# DataKYC

Document data extraction API for KYC onboarding powered by local Vision AI on NVIDIA DGX Spark.

Extracts structured data from Mexican identity and financial documents using Granite Vision 4.1 (OCR) and Gemma4 26B (cross-validation). Multi-tenant with tiered API key access — built for SOFOMes, fintechs, and compliance workflows.

## Architecture

```
Client → pfSense HAProxy (SSL wildcard) → nginx :80 → FastAPI :8002
                                                         ├── PostgreSQL 16
                                                         ├── Redis 7
                                                         ├── Granite Vision 4.1 (Spark :8004)
                                                         └── Gemma4 26B (Spark :8003)
```

## Organization Model

Organizations have **roles** and **statuses**:

| Role | Description |
|------|-------------|
| `SUPER_ADMIN` | Platform administrator — approves new organizations, manages all orgs |
| `ADMIN` | Organization administrator (future: manage org members) |
| `USER` | Standard organization user |

| Status | Description |
|--------|-------------|
| `PENDING` | Awaiting SUPER_ADMIN approval (new registrations) |
| `APPROVED` | Active — can log in and use the API |
| `REJECTED` | Registration denied |

### Registration Flow

1. **Public signup:** `POST /api/v1/auth/register` — creates org with `PENDING` status
2. **Admin review:** SUPER_ADMIN logs into dashboard, sees pending orgs
3. **Approve/Reject:** `PATCH /api/v1/admin/organizations/{id}/approve`
4. **Login:** Only `APPROVED` orgs can authenticate

## Quick Start

### Prerequisites
- DGX Spark (or compatible server) running Vision AI models:
  - Granite Vision 4.1 at port `:8004` (vLLM with `vllm/vllm-openai:nightly`)
  - Gemma4 26B at port `:8003` (optional, for cross-validation on PRO+ tiers)

### Setup

```bash
# Clone
git clone https://github.com/ccdiazt-ventures/DataKYC.git
cd DataKYC

# Configure environment
cp .env.example .env
# Edit .env — set DATABASE_URL, SECRET_KEY, Spark URLs

# Start services
docker compose up -d --build
```

### Seed SUPER_ADMIN

After first deploy, create the platform administrator:

```bash
docker compose exec api python -m app.seed_admin
```

Default SUPER_ADMIN credentials are set via environment variables:
- `SUPER_ADMIN_EMAIL` (default: cesar.diaz@rockyguard.com)
- `SUPER_ADMIN_PASSWORD` (default: Admin2026!)

### Registration

Open `http://localhost` and click **"Create new organization"**. Registration creates a PENDING account — the SUPER_ADMIN must approve it before login.

## Features

- **7 document types**: INE (front/back), CURP, Passport, RFC, Proof of Address, Bank Statement
- **Vision AI extraction**: Granite Vision 4.1 4B ~92% accuracy on Mexican IDs
- **Cross-validation**: Gemma4 26B validates extracted data consistency (PRO+)
- **KYC form filling**: Maps extracted fields to CNBV/SOFOM form templates (BASIC+)
- **Tier system**: FREE → BASIC → PRO → ENTERPRISE with per-endpoint feature gates
- **JWT Auth** for dashboard + **API Key** auth for programmatic access
- **Approval workflow**: Admin-controlled organization registration
- **Role-based access**: SUPER_ADMIN manages platform; ORDINARY users manage their API keys

## Tiers

| Tier | Docs/month | Document Types | Cross-Validation | Form Fill |
|------|-----------|----------------|-----------------|-----------|
| FREE | 10 | INE front | ✗ | ✗ |
| BASIC | 100 | + INE back, CURP, RFC | ✗ | ✓ |
| PRO | 1000 | + Passport, Proof of Address, Bank Statement | ✓ | ✓ |
| ENTERPRISE | ∞ | All + batch | ✓ | ✓ |

## API Endpoints

### Public (no auth)
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/health` | Health check with Spark model status |
| `POST` | `/api/v1/auth/register` | Register new organization (creates PENDING) |
| `POST` | `/api/v1/auth/login` | Login with email + password → JWT |

### Authenticated (JWT — all approved orgs)
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/auth/me` | Current org info + API keys |
| `GET` | `/api/v1/admin/organizations/me` | Get own organization details |
| `PATCH` | `/api/v1/admin/organizations/me` | Update own organization |
| `POST` | `/api/v1/admin/api-keys` | Create API key |
| `GET` | `/api/v1/admin/api-keys` | List your API keys |
| `POST` | `/api/v1/admin/api-keys/revoke` | Revoke API key |
| `GET` | `/api/v1/admin/usage` | Extraction usage stats |
| `GET` | `/api/v1/admin/quota` | Monthly quota status |

### SUPER_ADMIN only (JWT + SUPER_ADMIN role)
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/admin/organizations` | List all organizations (filter by `?status=`) |
| `GET` | `/api/v1/admin/organizations/pending` | List pending approvals |
| `POST` | `/api/v1/admin/organizations` | Create organization directly (pre-approved) |
| `PATCH` | `/api/v1/admin/organizations/{id}/approve` | Approve or reject a pending org |

### API Key Required
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/extract/{doc_type}` | Extract data from document image |
| `POST` | `/api/v1/verify/ine-data` | Cross-validate INE data with Gemma4 (PRO+) |
| `POST` | `/api/v1/fill-form` | Fill KYC form from extracted data (BASIC+) |

## API Usage Example

### Registration
```bash
curl -X POST https://datakyc.rockyguard.com/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"name":"Mi SOFOM","email":"admin@misofom.mx","password":"secure123","plan":"FREE"}'

# Response
{
  "id": "...",
  "name": "Mi SOFOM",
  "email": "admin@misofom.mx",
  "plan": "FREE",
  "status": "PENDING",
  "message": "Registration received. Awaiting platform administrator approval."
}
```

### Extraction
```bash
# Extract INE data (after approval + API key creation)
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
    "clave_elector": "DITCDZ88021109H700"
  },
  "confidence_scores": { "curp": 1.0, "nombre": 0.95 },
  "overall_confidence": 0.92,
  "processing_time_ms": 5023
}
```

### Admin: Approve Organization
```bash
# Login as SUPER_ADMIN
TOKEN=$(curl -s -X POST https://datakyc.rockyguard.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"cesar.diaz@rockyguard.com","password":"Admin2026!"}' | jq -r '.access_token')

# List pending orgs
curl -s https://datakyc.rockyguard.com/api/v1/admin/organizations/pending \
  -H "Authorization: Bearer $TOKEN"

# Approve
curl -X PATCH https://datakyc.rockyguard.com/api/v1/admin/organizations/{org_id}/approve \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status":"APPROVED"}'
```

## Requirements

- Docker 24+ with Compose v2
- NVIDIA DGX Spark running:
  - Granite Vision 4.1 at `:8004` (vLLM with `vllm/vllm-openai:nightly`)
  - Gemma4 26B at `:8003` (optional, for cross-validation)
- PostgreSQL and Redis containers included in docker-compose

## Project Structure

```
DataKYC/
├── app/
│   ├── api/v1/          # Route handlers
│   │   ├── auth.py      # Login, registration, JWT
│   │   ├── admin.py     # Org management, API keys, usage, approvals
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
│   ├── core/             # Constants, security utilities
│   ├── seed_admin.py     # SUPER_ADMIN bootstrap script
│   └── main.py           # FastAPI app
├── nginx/                # Reverse proxy config
├── web/                  # Frontend (Vanilla JS + Tailwind)
├── tests/
├── docker-compose.yml
└── Dockerfile
```

## License

MIT
