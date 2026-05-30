# DataKYC — Manual de Uso

Guía completa para desarrolladores y usuarios de DataKYC.

---

## Índice

1. [Instalación y despliegue](#1-instalación-y-despliegue)
2. [Uso del Dashboard Web](#2-uso-del-dashboard-web)
3. [API — Integración programática](#3-api--integración-programática)
4. [Tipos de documento soportados](#4-tipos-de-documentos-soportados)
5. [Tiers y límites](#5-tiers-y-límites)
6. [Arquitectura de seguridad](#6-arquitectura-de-seguridad)
7. [Solución de problemas](#7-solución-de-problemas)

---

## 1. Instalación y despliegue

### Requisitos

- Docker 24+ con Compose v2
- Acceso a una DGX Spark corriendo:
  - Granite Vision 4.1 en puerto 8004 (vLLM)
  - Gemma4 26B en puerto 8003 (opcional, para cross-validation)
- Ubuntu 24.04 LTS (recomendado para el host)

### Despliegue rápido

```bash
git clone https://github.com/ccdiazt-ventures/DataKYC.git
cd DataKYC
cp .env.example .env
```

Editar `.env` con las URLs correctas de Spark y credenciales:

```env
API_HOST=0.0.0.0
API_PORT=8002
DATABASE_URL=postgresql+asyncpg://datakyc:<password>@postgres:5432/datakyc
REDIS_URL=redis://redis:6379/0
GRANITE_VISION_URL=http://10.0.0.100:8004/v1
GEMMA4_URL=http://10.0.0.100:8003/v1
SECRET_KEY=<generar-string-aleatorio>
```

```bash
docker compose up -d --build
```

La aplicación estará disponible en `http://localhost:80`.

### Configuración de dominio con SSL

DataKYC está diseñado para usar terminación SSL externa vía pfSense HAProxy con certificados wildcard Let's Encrypt:

```
Internet → pfSense HAProxy :443 (*.rockyguard.com)
         → LXC 10.0.0.122:80
         → nginx (datakyc_nginx)
         → FastAPI (datakyc_api:8002)
```

El nginx incluido en docker-compose sirve como reverse proxy interno. No requiere certificados propios — HAProxy maneja SSL.

---

## 2. Uso del Dashboard Web

### Registro

1. Abrir `http://datakyc.rockyguard.com/` (o `http://IP:80`)
2. Hacer clic en **"Create new organization"**
3. Llenar nombre, email, password y seleccionar plan
4. Hacer clic en **Register**
5. Iniciar sesión con el email y password registrados

### Dashboard

Una vez autenticado:

- **API Key**: Se muestra tu API key activa. Puedes crear nuevas con el botón **+ New Key**
- **Document Type**: Selecciona el tipo de documento a extraer
- **Upload**: Arrastra una imagen o haz clic para seleccionar
- **Quick Test Images**: Carga INEs de prueba pre-cargadas con un clic
- **Extract Data**: Envía la imagen a Granite Vision para extracción
- **Results**: Los resultados aparecen como JSON + tabla de campos con scores de confianza

### Atajos de teclado

- `Ctrl+Enter` — Extraer documento

---

## 3. API — Integración programática

### Autenticación

La API usa dos mecanismos de autenticación independientes:

| Mecanismo | Header | Uso |
|-----------|--------|-----|
| **API Key** | `X-API-Key: dkc_live_xxx` | Extracción, verificación, form-fill |
| **JWT Bearer** | `Authorization: Bearer <token>` | Dashboard, gestión de API keys |

### Obtener JWT (login)

```bash
curl -X POST https://datakyc.rockyguard.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "org@example.com", "password": "your-password"}'
```

Respuesta:
```json
{
  "access_token": "eyJhbG...",
  "token_type": "bearer",
  "organization": {
    "id": "uuid",
    "name": "My Org",
    "email": "org@example.com",
    "plan": "PRO"
  },
  "expires_in": 86400
}
```

El token expira en 24 horas. Guardarlo en `sessionStorage` o variable de entorno.

### Obtener/Crear API Key

```bash
# Ver info de la org y API keys existentes
curl https://datakyc.rockyguard.com/api/v1/auth/me \
  -H "Authorization: Bearer eyJhbG..."

# Crear nueva API key
curl -X POST https://datakyc.rockyguard.com/api/v1/admin/api-keys \
  -H "Authorization: Bearer eyJhbG..." \
  -H "Content-Type: application/json" \
  -d '{
    "organization_id": "your-org-uuid",
    "scopes": ["extract", "verify", "fill-form"],
    "is_live": true
  }'
```

La API key se muestra **una sola vez**. Guardarla inmediatamente.

### Extraer datos de documento

```bash
curl -X POST https://datakyc.rockyguard.com/api/v1/extract/INE_FRONT \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dkc_live_xxx" \
  -d '{
    "image_base64": "/9j/4AAQ...(imagen JPEG en base64)..."
  }'
```

### Validación cruzada con Gemma4 (PRO+)

```bash
curl -X POST https://datakyc.rockyguard.com/api/v1/verify/ine-data \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dkc_live_xxx" \
  -d '{
    "pre_extracted_data": {
      "nombre": "CESAR CARLOS",
      "curp": "DITC880211HDFZRS09",
      "fecha_nacimiento": "11/02/1988",
      "sexo": "H"
    }
  }'
```

### Rellenar formato KYC (BASIC+)

```bash
curl -X POST https://datakyc.rockyguard.com/api/v1/fill-form \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dkc_live_xxx" \
  -d '{
    "extracted_data": { "nombre": "CESAR", "curp": "DITC..." },
    "form_template": "sofom_standard"
  }'
```

Templates disponibles: `sofom_standard`, `cnbv_basic`, `cnbv_advanced`.

### Códigos de error comunes

| Código | Significado | Acción |
|--------|-------------|--------|
| `401` | API key inválida o expirada | Verificar `X-API-Key` header |
| `403` | Feature no disponible en tu plan | Hacer upgrade de tier |
| `429` | Rate limit o cuota mensual excedida | Esperar o hacer upgrade |
| `400` | Datos inválidos (imagen corrupta, campo faltante) | Revisar request body |

---

## 4. Tipos de documentos soportados

### `INE_FRONT` — Frente de INE mexicana

Campos extraídos: `nombre`, `apellido_paterno`, `apellido_materno`, `curp`, `clave_elector`, `seccion`, `vigencia`, `domicilio` (calle, número, colonia, CP, municipio, estado), `fecha_nacimiento`, `sexo`, `emision`

### `INE_BACK` — Reverso de INE mexicana

Campos: `cic`, `mrz_linea1`, `mrz_linea2`, `mrz_linea3`, `anio_registro`, `localidad`

### `CURP`

Campos: `curp`, `nombre`, `apellido_paterno`, `apellido_materno`, `fecha_nacimiento`, `sexo`, `entidad_nacimiento`, `nacionalidad`, `documento_probatorio`

### `PASSPORT` — Pasaporte mexicano

Campos: `numero_pasaporte`, `nombre`, `apellidos`, `nacionalidad`, `fecha_nacimiento`, `sexo`, `fecha_emision`, `fecha_expiracion`, `autoridad_emisora`, `mrz_linea1`, `mrz_linea2`

### `RFC` — Cédula de Identificación Fiscal

Campos: `rfc`, `nombre`, `apellido_paterno`, `apellido_materno`, `fecha_emision`, `regimen_fiscal`

### `COMPROBANTE_DOMICILIO`

Campos: `nombre`, `direccion_completa`, `codigo_postal`, `municipio`, `estado`, `tipo_comprobante`, `fecha_emision`, `emisor`

Tipos detectados: CFE, AGUA, TELEFONO, PREDIAL, GAS, OTRO

### `ESTADO_CUENTA` — Estado de cuenta bancario

Campos: `banco`, `nombre_titular`, `numero_cuenta`, `clabe`, `periodo`, `saldo_promedio`, `tipo_cuenta`

---

## 5. Tiers y límites

| Característica | FREE | BASIC | PRO | ENTERPRISE |
|---|---|---|---|---|
| **Docs/mes** | 10 | 100 | 1,000 | Ilimitado |
| **Rate/min** | 5 | 20 | 60 | 120 |
| **INE Front** | ✓ | ✓ | ✓ | ✓ |
| **INE Back** | ✗ | ✓ | ✓ | ✓ |
| **CURP** | ✗ | ✓ | ✓ | ✓ |
| **RFC** | ✗ | ✓ | ✓ | ✓ |
| **Pasaporte** | ✗ | ✗ | ✓ | ✓ |
| **Comprobante** | ✗ | ✗ | ✓ | ✓ |
| **Edo. Cuenta** | ✗ | ✗ | ✓ | ✓ |
| **Cross-validation** | ✗ | ✗ | ✓ | ✓ |
| **Form fill** | ✗ | ✓ | ✓ | ✓ |
| **Batch** | ✗ | ✗ | ✗ | ✓ |

El conteo de extracciones se reinicia el primer día de cada mes. Las solicitudes que excedan el rate limit reciben HTTP 429.

---

## 6. Arquitectura de seguridad

### API Keys

- Formato: `dkc_live_<40-char-hex>` (producción) o `dkc_test_<40-char-hex>` (sandbox)
- Almacenadas como SHA-256 hash en PostgreSQL (nunca en texto plano)
- Se muestran una sola vez al crearse
- Revocables desde el dashboard (`POST /api/v1/admin/api-keys/revoke`)

### JWT

- Algoritmo: HS256
- Expiración: 24 horas
- Claims: `sub` (org UUID), `exp`, `iat`, `jti`
- Secreto configurable vía `SECRET_KEY` en `.env`

### Passwords

- Hasheados con bcrypt (gensalt automático)
- Nunca almacenados en texto plano
- Mínimo sin restricción forzada (se recomienda ≥8 caracteres)

### Red

- Solo nginx expone puerto 80 al exterior
- API (8002), PostgreSQL (5432) y Redis (6379) en red Docker interna
- SSL terminado en pfSense HAProxy (certificados wildcard Let's Encrypt)

---

## 7. Solución de problemas

### La API no arranca

```bash
docker compose logs api
```

Causas comunes:
- PostgreSQL no accesible: verificar que `DATABASE_URL` use el nombre del servicio (`postgres`) no `localhost`
- `SECRET_KEY` demasiado corto: mínimo 32 caracteres

### Error "email-validator is not installed"

El contenedor se reconstruyó sin la dependencia. Asegurar que `requirements.txt` tenga `pydantic[email]` y reconstruir sin cache:

```bash
docker compose build --no-cache api
docker compose up -d
```

### Extracción devuelve campos vacíos

- La imagen puede ser de muy baja calidad — verificar que sea ≥200 DPI
- El modelo Granite Vision puede estar frío (primera solicitud ~5-10s)
- Verificar conectividad a la Spark: `curl http://10.0.0.100:8004/health`

### nginx devuelve 502 Bad Gateway

```bash
docker compose restart api
```

Si persiste, verificar que la red Docker interna funcione:

```bash
docker exec datakyc_nginx wget -qO- http://datakyc_api:8002/api/v1/health
```

### Cuota mensual excedida antes de tiempo

El conteo es por mes calendario. Si necesitas reiniciar:

```sql
-- Conectarse a PostgreSQL y reiniciar
UPDATE monthly_quotas SET extractions_used = 0 
WHERE organization_id = '<org-uuid>' 
  AND year = 2026 AND month = 5;
```

---

## Mantenimiento

### Actualizar la aplicación

```bash
cd /home/ccdiazt/DataKYC
git pull
docker compose up -d --build
```

### Respaldar la base de datos

```bash
docker exec datakyc_postgres pg_dump -U datakyc datakyc > backup_$(date +%Y%m%d).sql
```

### Ver logs

```bash
# Todos los servicios
docker compose logs --tail=100

# Solo la API
docker compose logs api --tail=50 -f
```
