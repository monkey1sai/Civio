# CLAUDE.md — Civio Community SIP Platform

## Project overview
Civio is a multi-tenant community SIP communication platform. It provides SIP-based voice calling, announcement, task management, and a Token-based economy for residential communities. The platform serves 台灣國際物業 (Taiwan International Property) as a SaaS product for building management companies.

Three deployable units:
- `civio-cloud` — Python FastAPI control plane, master database, SIP proxy (OpenSIPS), message bus
- `civio-edge` — Docker Compose bundle deployed per-community: Asterisk PJSIP, local cache DB, sync agent, event publisher
- `civio-app` — Flutter mobile app for residents (iOS + Android)

A fourth surface, `civio-admin` (React web), is a sub-project of `civio-cloud`.

## Tech stack

| Layer | Tech | Version |
|---|---|---|
| Cloud API | Python 3.12, FastAPI | 0.115+ |
| Cloud ORM | SQLAlchemy async, Alembic | 2.0+, 1.14+ |
| Cloud DB | PostgreSQL | 16 |
| Cache | Redis | 7 |
| Message bus | RabbitMQ | 3.13+ |
| SIP proxy | OpenSIPS | 3.5 |
| Media server | Asterisk PJSIP | 22 LTS |
| Mobile | Flutter, Dart | 3.24+, 3.5+ |
| State | Riverpod | 2.x |
| SIP client | sip_ua + flutter_webrtc | latest |
| Admin web | React + TypeScript + Vite | 18+ |
| Containers | Docker Compose | v2 |
| CI | GitHub Actions | - |

## Implementation order (MUST be followed)

Claude Code MUST build in this order. Do not skip phases.

1. **Scaffold** — repo structure, Docker Compose skeleton, shared `.env.example`, pre-commit hooks, linting configs
2. **Database schema** — Alembic migrations for all tables in `docs/02-database-schema.sql`; verify with `alembic upgrade head` and `alembic check`
3. **Cloud core** — `civio-cloud` FastAPI app with auth, tenant, and SIP provisioning modules (see `civio-cloud/CLAUDE.md`)
4. **Infrastructure** — Docker Compose for PostgreSQL, Redis, RabbitMQ, Traefik with TLS
5. **Edge node** — `civio-edge` Asterisk Realtime configuration, local PostgreSQL, sync agent, event publisher
6. **OpenSIPS** — cloud SIP proxy with domain-based dispatcher and auth-callback to FastAPI
7. **Event workers** — CDR processor, billing worker, audit logger consuming RabbitMQ
8. **Flutter app** — auth, dialer, in-call UI, contacts, wallet, push notifications
9. **Admin web** — community management, CDR search, token ledger, health dashboard
10. **Testing** — unit + integration + SIPp E2E suite, CI pipeline

Each phase has its own CLAUDE.md in the corresponding directory. Read it before starting.

## Repository layout

```
civio/
├── CLAUDE.md                       this file
├── README.md                       human onboarding
├── docker-compose.yml              top-level orchestration for local dev
├── .env.example                    all required env vars
├── .pre-commit-config.yaml
├── .github/workflows/              CI pipelines
├── docs/
│   ├── 01-architecture.md          system architecture reference
│   ├── 02-database-schema.sql      authoritative DDL
│   ├── 03-api-contract.yaml        OpenAPI 3.1 specification
│   ├── 04-sync-protocol.md         cloud-to-edge sync protocol
│   ├── 05-test-strategy.md         testing pyramid and verification gates
│   └── 06-security-checklist.md    pre-launch security audit
├── civio-cloud/                    Python FastAPI control plane
│   ├── CLAUDE.md
│   └── ...
├── civio-edge/                     per-community edge bundle
│   ├── CLAUDE.md
│   └── ...
├── civio-app/                      Flutter mobile app
│   ├── CLAUDE.md
│   └── ...
└── .claude/commands/               reusable slash commands
    ├── scaffold-module.md
    ├── add-api-endpoint.md
    └── run-full-test-suite.md
```

## Global conventions

- **Language**: Python for backend, Dart for mobile, TypeScript for admin web. No other languages permitted.
- **Identifiers**: All entity primary keys are UUID v4. Never use auto-increment integers except for append-only logs (`token_ledger`, `sync_event`).
- **Timestamps**: Always store as `TIMESTAMPTZ` in UTC. Convert to local time only at the presentation layer.
- **Money / tokens**: Always `Decimal(18, 4)` on the wire and in DB. Never `float`.
- **Naming**:
  - Python modules and files: `snake_case`
  - Python classes: `PascalCase`
  - Dart files and classes: same as Python
  - Database tables: `snake_case`, plural (e.g. `users`, `call_logs`)
  - Database columns: `snake_case`, singular (`user_id`, not `users_id`)
  - API paths: kebab-case plural (`/api/v1/sip-endpoints`)
- **Logging**: structured JSON only (`structlog` for Python, `logger` for Dart). No `print()` or `console.log()` in committed code.
- **Secrets**: never hardcode. All secrets via env vars loaded by `pydantic-settings`. Keep an up-to-date `.env.example`.
- **Commits**: conventional commits format (`feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`).
- **Branches**: `main` (protected), `feat/<ticket>`, `fix/<ticket>`. Never push directly to main.

## Verification gates (MUST run after every significant change)

These commands define "done". If any fail, Claude Code MUST fix the code and re-run until all pass. Do not mark a task complete otherwise.

```bash
# Backend (run from civio-cloud/)
ruff check src/ tests/                  # no lint violations
ruff format --check src/ tests/         # formatting correct
mypy src/ --strict                      # zero type errors
pytest tests/unit -x -q                 # unit tests pass
pytest tests/integration -x -q          # integration tests pass
alembic check                           # migrations match models

# Mobile (run from civio-app/)
dart format --set-exit-if-changed lib/ test/
dart analyze --fatal-infos lib/ test/
flutter test

# Infrastructure
docker compose config -q                # compose file is valid
docker compose build                    # all images build

# E2E (run from repo root)
./scripts/e2e.sh                        # SIPp + API scenario
```

## Constraints (NEVER do these)

- NEVER use `Any` in Python type hints. Use `object`, generics, or define a protocol.
- NEVER write raw SQL in service layer. All DB access goes through repository classes.
- NEVER call SIP APIs directly from Flutter widgets. Go through the `UseCase` layer.
- NEVER hardcode community IDs, SIP domains, URLs, or credentials.
- NEVER commit `.env` files. Only `.env.example`.
- NEVER use `print`, `console.log`, `debugPrint` in committed code.
- NEVER leave `TODO` or `FIXME` comments in merged code — open a GitHub issue instead.
- NEVER store passwords in plaintext. Use `passlib[bcrypt]` with cost factor 12+.
- NEVER expose a SIP endpoint's password in any API response.
- NEVER log PII (mobile numbers, SIP URIs) at INFO level. DEBUG only, and only in development.
- NEVER allow a call to bypass the auth callback. Every INVITE gets authorized.
- NEVER allow `TokenLedger` rows to be updated or deleted. Append-only.
- NEVER block the SIP signalling path on event bus operations. Publish-and-forget.

## Environment variables

The root `.env.example` declares all vars. Subprojects may declare additional ones in their own `.env.example` but must not duplicate keys.

Key variables:

- `DATABASE_URL` — PostgreSQL async DSN (`postgresql+asyncpg://...`)
- `REDIS_URL` — Redis DSN
- `RABBITMQ_URL` — AMQP DSN
- `JWT_SECRET` — min 32 bytes, rotate quarterly
- `JWT_ACCESS_TTL_MIN` — default 15
- `JWT_REFRESH_TTL_DAYS` — default 7
- `OTP_TTL_SEC` — default 300
- `SIP_DOMAIN_SUFFIX` — e.g. `sip.civio.example.com`
- `OPENSIPS_AUTH_SHARED_SECRET` — shared between OpenSIPS and cloud
- `ASTERISK_AMI_USER` / `ASTERISK_AMI_SECRET` — for edge event publisher
- `PAYMENT_PROVIDER` — `ecpay` | `newebpay` | `stripe`
- `ENV` — `local` | `staging` | `production`

## Service layer pattern

Every feature MUST follow this layer separation:

```
HTTP request
    ↓
API router (api/v1/*.py)        handles HTTP, validation, auth dep injection
    ↓
Service (services/*.py)         business logic, orchestration, transactions
    ↓
Repository (repositories/*.py)  data access, query building
    ↓
Model (models/*.py)             SQLAlchemy ORM
    ↓
PostgreSQL
```

- Routers never call repositories directly.
- Services never import FastAPI types.
- Repositories never import service types.
- Schemas (`schemas/*.py`) are Pydantic models; they are the contract for HTTP requests and responses. Never return ORM models directly from an API route.

## Agent guidelines for Claude Code

1. **Read before write**. When touching a file, view it first. When adding a feature, read the relevant CLAUDE.md in the subdirectory.
2. **Tests are not optional**. Every new function, class, or endpoint ships with tests in the same PR.
3. **Migrations are generated, not hand-written**. Use `alembic revision --autogenerate -m "<message>"`. Review the generated SQL before committing.
4. **One task, one commit**. Keep commits focused. Never bundle unrelated changes.
5. **When stuck, ask**. If a requirement is ambiguous, write down your interpretation in the PR description and proceed — do not silently guess on architecture decisions.
6. **Use slash commands**. See `.claude/commands/` for reusable workflows.

## Quick start for Claude Code

When a user opens this project for the first time, do the following in order:

1. Run `/project:scaffold-module` with name `auth` to verify the scaffolding works end-to-end
2. Read `docs/01-architecture.md` to understand the system
3. Read `docs/02-database-schema.sql` for the authoritative data model
4. Read `docs/05-test-strategy.md` to understand the verification bar
5. Start building from phase 1 of the implementation order above
