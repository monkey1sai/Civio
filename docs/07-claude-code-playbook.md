# 07 — Claude Code execution playbook

This playbook is the authoritative sequence for building Civio from scratch. Claude Code MUST follow these phases in order. Each phase has inputs (what you read first), outputs (what must exist when you finish), and a verification gate (commands that must pass before moving on).

If a verification gate fails, DO NOT proceed. Fix the phase and re-verify.

---

## Phase 0 — Orientation

**Inputs:**
- Read `/CLAUDE.md`
- Read `/docs/01-architecture.md`
- Read `/docs/02-database-schema.sql`
- Read `/docs/03-api-contract.yaml`
- Read `/docs/04-sync-protocol.md`
- Read `/docs/05-test-strategy.md`
- Read `/docs/06-security-checklist.md`

**Outputs:**
- None (understanding only)

**Verification:**
- None. Proceed to Phase 1.

---

## Phase 1 — Repository scaffolding

**Goal:** Lay down the monorepo skeleton so Phase 2 can start adding real code.

**Tasks:**

1. Initialize git repository, configure `main` as default branch
2. Create top-level directories: `civio-cloud/`, `civio-edge/`, `civio-app/`, `docs/`, `.github/workflows/`, `.claude/commands/`, `scripts/`
3. Copy `.env.example` content as-is; verify `.env` is gitignored
4. Install pre-commit hooks: `pre-commit install && pre-commit install --hook-type commit-msg`
5. Create `scripts/` with:
   - `scripts/e2e.sh` — placeholder that exits 0 (real implementation in Phase 10)
   - `scripts/init-dev.sh` — creates `.env` from `.env.example`, generates secrets with `openssl rand`
   - `scripts/wait-for.sh` — helper to wait for services in docker-compose
6. Create `Makefile` with targets: `help`, `up`, `down`, `test`, `lint`, `migrate`, `clean`

**Outputs:**
```
civio/
├── CLAUDE.md
├── README.md
├── Makefile
├── docker-compose.yml
├── .env.example
├── .gitignore
├── .pre-commit-config.yaml
├── .secrets.baseline
├── .github/workflows/ci.yml
├── docs/…                       (all 7 docs)
├── .claude/commands/…           (3 slash commands)
├── civio-cloud/CLAUDE.md
├── civio-edge/CLAUDE.md
├── civio-app/CLAUDE.md
└── scripts/
    ├── e2e.sh
    ├── init-dev.sh
    └── wait-for.sh
```

**Verification:**
```bash
pre-commit run --all-files          # all hooks pass
docker compose config -q            # compose file is valid
git log --oneline | head -1         # at least one commit exists
```

> **CI 漸進式策略**:ci.yml 已配置成「子專案未初始化則跳過」,所以 Phase 1~8 期間會看到部分 CI job 被 skip,這是預期行為,不是 bug。每個 Phase 完成對應子專案初始化後,相關 CI 會自動啟用。

---

## Phase 2 — Cloud data layer (models + migrations)

**Goal:** Produce a working Alembic migration that creates the schema in `docs/02-database-schema.sql`.

**Tasks:**

1. Initialize `civio-cloud/` with Poetry:
   ```bash
   cd civio-cloud
   poetry init --no-interaction
   ```
   Add all dependencies from `civio-cloud/CLAUDE.md`.

2. Create `src/core/config.py` using `pydantic-settings`. Every env var listed in `.env.example` has a corresponding field.

3. Create `src/core/database.py` with async engine and `get_db` dependency.

4. Create `src/models/base.py` with `Base` (DeclarativeBase) and `TimestampMixin`.

5. Create one model file per entity in `docs/02-database-schema.sql`:
   - `community.py` → `Community`
   - `unit.py` → `Unit`
   - `user.py` → `User`
   - `user_unit_relation.py` → `UserUnitRelation`
   - `sip_endpoint.py` → `SipEndpoint`
   - `friend_mapping.py` → `FriendMapping`
   - `token_ledger.py` → `TokenLedger`
   - `call_log.py` → `CallLog`
   - `billing_record.py` → `BillingRecord`
   - `sync_event.py` → `SyncEvent`
   - `sync_state.py` → `SyncState`
   - `announcement.py` → `Announcement`
   - `task.py` → `Task`
   - `audit_log.py` → `AuditLog`
   - `consent_record.py` → `ConsentRecord`
   - `processed_event.py` → `ProcessedEvent`
   - `payment_order.py` → `PaymentOrder`

   Each model:
   - Uses `Mapped[T]` type annotations (SQLAlchemy 2.0 style)
   - Uses PostgreSQL enum types where the DDL says `ENUM(...)`
   - Has relationships defined where the DDL has foreign keys
   - Column names match the DDL exactly

6. Initialize Alembic:
   ```bash
   poetry run alembic init -t async src/migrations
   ```
   Configure `env.py` for async per `civio-cloud/CLAUDE.md`.

7. Generate first migration:
   ```bash
   poetry run alembic revision --autogenerate -m "initial_schema"
   ```

8. Add post-migration SQL for things autogen can't handle:
   - `token_ledger` append-only triggers
   - `tg_bump_community_version` trigger
   - `token_balances` materialized view
   - Indexes with `WHERE` clauses
   - `pg_trgm` extension on `communities.name`

9. Run migration and confirm schema matches the DDL (`pg_dump --schema-only`).

**Verification:**
```bash
cd civio-cloud
poetry run ruff check src/
poetry run mypy src/ --strict
docker compose up -d postgres
poetry run alembic upgrade head
poetry run alembic check
poetry run alembic downgrade base  # verify down migration works
poetry run alembic upgrade head
```

Additional check: compare `docs/02-database-schema.sql` structure with `pg_dump --schema-only civio`. Any drift must be resolved.

---

## Phase 3 — Cloud core: auth, config, security

**Goal:** Usable `POST /auth/otp/send` and `POST /auth/otp/verify` endpoints returning real JWTs.

**Tasks:**

1. Create `src/core/security.py`:
   - `hash_password`, `verify_password` using `passlib[bcrypt]`, cost 12
   - `create_access_token`, `create_refresh_token` using `python-jose`
   - `decode_token` raising specific exceptions for expired/invalid
   - `generate_otp` returning 6 digits

2. Create `src/core/redis_client.py` with async `Redis` client factory

3. Create `src/core/logging.py` with `structlog` JSON output

4. Create `src/core/exceptions.py`:
   - `CivioException` base
   - `AuthenticationError`, `AuthorizationError`, `NotFoundError`, `ConflictError`, `ValidationError`
   - FastAPI exception handlers that return `{code, message, details}` with correct HTTP codes

5. Create `src/core/dependencies.py`:
   - `get_current_user` — decodes JWT, loads user from DB
   - `require_role(*roles)` — dependency factory for role-gated endpoints
   - `get_current_community_id` — extracts from user

6. Create `src/repositories/base.py` with `BaseRepository[T]` (see `civio-cloud/CLAUDE.md`)

7. Create `src/repositories/user_repo.py`:
   ```python
   class UserRepository(BaseRepository[User]):
       async def get_by_mobile(self, community_id: UUID, mobile: str) -> User | None
       async def list_by_community(self, community_id: UUID) -> list[User]
   ```

8. Create `src/services/auth_service.py` per contract in `civio-cloud/CLAUDE.md`. Store OTP challenges in Redis with TTL.

9. Create `src/schemas/auth.py`:
   - `OtpSendRequest`, `OtpVerifyRequest`, `RefreshRequest`
   - `OtpChallenge`, `TokenPair`, `TokenPayload`

10. Create `src/api/v1/auth.py` with four endpoints:
    - `POST /auth/otp/send`
    - `POST /auth/otp/verify`
    - `POST /auth/refresh`
    - `POST /auth/logout`

11. Create `src/main.py` — FastAPI app factory:
    - Configures CORS from settings
    - Mounts v1 router at `/api/v1`
    - Adds exception handlers
    - Adds `/health` endpoint
    - Adds Prometheus metrics endpoint at `/metrics`

12. Write tests:
    - `tests/unit/services/test_auth_service.py` — OTP send, verify, wrong code, expired, rate limit
    - `tests/integration/api/test_auth_flow.py` — full round-trip: send OTP → read Redis → verify → call protected endpoint

**Verification:**
```bash
cd civio-cloud
poetry run pytest tests/unit/services/test_auth_service.py -x -q
poetry run pytest tests/integration/api/test_auth_flow.py -x -q
poetry run ruff check src/ tests/
poetry run mypy src/ --strict

# Manual smoke
poetry run uvicorn src.main:app --reload &
curl -X POST http://localhost:8000/api/v1/auth/otp/send \
  -H "Content-Type: application/json" \
  -d '{"mobile":"+886912345678"}'
# Should return 200 with {challenge_id, mobile, expires_at}
kill %1
```

---

## Phase 4 — Cloud: tenant & SIP provisioning

**Goal:** Admins can create communities, units, users; creating a user auto-creates a SIP endpoint.

**Tasks:**

1. Create remaining repositories in `src/repositories/`:
   - `community_repo`, `unit_repo`, `sip_endpoint_repo`, `friend_repo`, `user_unit_relation_repo`

2. Create services:
   - `src/services/tenant_service.py` — community and unit CRUD
   - `src/services/sip_provisioning_service.py` — generates SIP username (use `<unit_code>@<sip_domain>` format), generates strong password, hashes with bcrypt, creates endpoint row
   - `src/services/user_service.py` — user CRUD with auto SIP provisioning on `auth_status = verified`

3. Create schemas in `src/schemas/` (community, unit, user, sip)

4. Create routers:
   - `src/api/v1/communities.py`
   - `src/api/v1/units.py`
   - `src/api/v1/users.py`
   - `src/api/v1/sip.py` (but not the `/authorize` endpoint yet — that's Phase 6)

5. Add role-based access control: only `admin` role can POST/PATCH/DELETE on communities, units, users

6. Tests:
   - Unit: test each service method, especially SIP provisioning with collision handling
   - Integration: create community → unit → user → verify SIP endpoint auto-created

**Verification:**
```bash
poetry run pytest tests/unit/services -x -q
poetry run pytest tests/integration/api -x -q
poetry run mypy src/ --strict
```

---

## Phase 5 — Edge node infrastructure

**Goal:** A single-community Asterisk + PostgreSQL stack that can register a SIP client and place a same-community call without any cloud connection.

**Tasks:**

1. Create `civio-edge/docker-compose.yml` with services: asterisk, postgres, redis (all on `network_mode: host` for asterisk, bridge for others)

2. Build Asterisk 22 Dockerfile (multi-stage from `debian:bookworm-slim`)

3. Create Asterisk configuration files per `civio-edge/CLAUDE.md`:
   - `asterisk.conf`, `modules.conf`, `pjsip.conf`, `sorcery.conf`, `extconfig.conf`, `res_pgsql.conf`, `extensions.conf`, `rtp.conf`, `manager.conf`

4. Create PostgreSQL init script `postgres/init.sql` that creates Asterisk Realtime tables: `ps_endpoints`, `ps_auths`, `ps_aors`, `ps_contacts`

5. Seed test data: one endpoint with username `1001`, password bcrypt of `test_pass`

6. Verify registration:
   ```bash
   cd civio-edge
   docker compose up -d
   # Use a softphone (Linphone, Ooh) to register 1001@<host>
   # Check Asterisk CLI:
   docker compose exec asterisk asterisk -rx "pjsip show endpoints"
   ```

7. Write `tests/test_asterisk_config.py` — validates config files parse correctly by running `asterisk -c "core show channels"` in a clean container

**Verification:**
```bash
cd civio-edge
docker compose config -q
docker compose build
docker compose up -d
docker compose exec asterisk asterisk -rx "module show" | grep res_pjsip
docker compose exec asterisk asterisk -rx "pjsip show transports"
# Manual: register a softphone, verify with `pjsip show endpoints`
docker compose down -v
```

---

## Phase 6 — OpenSIPS cloud proxy + auth callback

**Goal:** Flutter client registers via OpenSIPS (wss://sip.civio.local:5061), OpenSIPS dispatches to the correct Asterisk edge, INVITEs trigger the auth callback.

**Tasks:**

1. Create `civio-cloud/opensips/` with:
   - `Dockerfile` based on `opensips/opensips:3.5`
   - `opensips.cfg` per `docs/01-architecture.md` example
   - `dispatcher.list` seeding one Asterisk backend

2. Configure dispatcher to select backend based on `sip_domain` of the request URI:
   - Parse domain from R-URI
   - Map to `setid` by looking up `communities.sip_domain` → `dispatcher` table
   - Set routing key accordingly

3. Add the `/api/v1/sip/authorize` endpoint to `src/api/v1/sip.py`:
   - Accepts `CallAuthRequest`
   - Authenticates via shared secret (NOT JWT)
   - Calls `CallPolicyService.authorize`
   - Returns `CallAuthDecision`

4. Implement `src/services/call_policy_service.py` with the full decision matrix from `civio-cloud/CLAUDE.md`

5. Configure OpenSIPS `exec` module to call the FastAPI auth endpoint on every INVITE; use `httpclient` module with 5-second timeout

6. Tests:
   - Unit: `tests/unit/services/test_call_policy_service.py` — MUST cover every row in the decision matrix
   - Integration: `tests/integration/api/test_sip_authorize.py` — uses real DB with seeded users and asserts each decision

**Verification:**
```bash
cd civio-cloud
poetry run pytest tests/unit/services/test_call_policy_service.py -x -v
# Every scenario in the decision matrix appears in the test output

docker compose up -d opensips civio-cloud-api postgres redis
# Simulated INVITE with sipp
cd ../tests/e2e
sipp -sf register_tls.xml -sf place_call.xml <opensips_host>
```

---

## Phase 7 — Sync service (cloud + edge)

**Goal:** A freshly provisioned edge pulls a full snapshot from cloud, then applies deltas as cloud writes happen. Merkle root matches on both sides.

**Tasks:**

1. Cloud side:
   - Implement `src/services/sync_service.py`:
     - `generate_full_snapshot` — queries all synced tables, paginates 1000 rows, attaches per-page SHA-256 checksum
     - `get_delta_since` — queries `sync_events`
     - `acknowledge` — compares Merkle root, updates `sync_state`
     - `emit_event` — writes to `sync_events` and publishes AMQP
   - Add endpoints to `src/api/v1/sync.py`:
     - `GET /sync/full/begin`, `GET /sync/full/{snapshot_id}`, `POST /sync/full/commit`
     - `GET /sync/delta`, `POST /sync/ack`
   - Add shared-secret auth dependency

2. Cloud side: `src/core/merkle.py` — reference implementation from `docs/04-sync-protocol.md`

3. Cloud side: wire up triggers — whenever a model in synced-entity list changes via service layer, insert into `sync_events` (use SQLAlchemy event listeners or explicit calls in each service)

4. Edge side: build `civio-edge/sync_agent/`:
   - `cloud_client.py` — `httpx.AsyncClient` with shared-secret + HMAC signature
   - `merkle.py` — identical to cloud
   - `state_store.py` — reads/writes local `sync_state` table
   - `applier.py` — applies DeltaBatch rows; maps `sip_endpoints` changes to `ps_endpoints` + `ps_auths` + `ps_aors`
   - `__main__.py` — runs the 30-second loop

5. Tests:
   - Cloud unit: test Merkle implementation with known fixtures
   - Edge unit: test applier with mock cloud responses, verify ps_* tables populated correctly
   - Integration (in `docker-compose.test.yml`):
     - Happy full sync
     - Happy delta sync
     - Merkle mismatch recovery
     - Stale version (force full resync)
     - Tombstone handling

**Verification:**
```bash
# Cloud unit + integration
cd civio-cloud
poetry run pytest tests/unit/services/test_sync_service.py -x -q
poetry run pytest tests/integration/sync -x -q

# Edge unit
cd ../civio-edge/sync_agent
poetry run pytest tests -x -q

# End-to-end (scripted)
cd ../..
./scripts/test-sync-e2e.sh
# Script: starts cloud + one edge, creates 10 users via cloud API,
# waits 60s, asserts ps_endpoints on edge has 10 rows with matching data
```

---

## Phase 8 — Event bus (CDR, billing, audit)

**Goal:** A completed call results in a `call_logs` row, a `token_ledger` entry, and an `audit_log` entry — all within 10 seconds.

**Tasks:**

1. Cloud side: `src/core/event_bus.py` — `EventPublisher` per `civio-cloud/CLAUDE.md` contract

2. Cloud side: `src/events/schemas.py` — Pydantic models for CloudEvents

3. Cloud side: three consumers in `src/events/consumers/`:
   - `cdr_consumer.py` — binds to `call.ended`, inserts `call_logs`
   - `billing_consumer.py` — binds to `billing.charge`, appends to `token_ledger`
   - `audit_consumer.py` — binds to `#`, inserts `audit_log`

4. Cloud side: `src/worker.py` — consumer entry point that starts all consumers

5. Each consumer MUST:
   - Use `processed_events` table for idempotency (check on receive, insert on success)
   - Declare its queue with DLX and 5-minute TTL
   - Manual ack on success, nack (requeue=False) on exception
   - Log start/success/failure with `structlog`

6. Edge side: build `civio-edge/event_publisher/`:
   - `ami_listener.py` using `panoramisk`
   - `event_mapper.py` — AMI event → CloudEvent
   - `mq_publisher.py` with local SQLite outbox for durability
   - `outbox.py` — drain loop with exponential backoff
   - `__main__.py`

7. Wire `cdr_consumer` to publish a follow-up `billing.charge` event

8. Tests:
   - Unit: mock RabbitMQ, verify each consumer handles success, failure, duplicate
   - Integration: publish event → assert DB row created
   - Edge unit: test AMI event mapping, outbox write/drain

**Verification:**
```bash
cd civio-cloud
poetry run pytest tests/integration/events -x -q

# End-to-end
cd ..
./scripts/test-event-bus-e2e.sh
# Script publishes a synthetic "call.ended" → verifies call_log + billing + audit rows
```

---

## Phase 9 — Flutter mobile app

**Goal:** Resident can log in via OTP, view contacts, place a call, receive a call.

**Tasks:**

1. Initialize Flutter project in `civio-app/`:
   ```bash
   flutter create civio-app --org com.civio --project-name civio_app
   ```

2. Set pubspec dependencies per `civio-app/CLAUDE.md`

3. Scaffold Clean Architecture folders per `civio-app/CLAUDE.md`

4. Generate boilerplate:
   ```bash
   dart run build_runner build --delete-conflicting-outputs
   ```

5. Build features in this order:
   - `auth` — login screen, OTP screen, token storage, interceptor
   - `contacts` — fetch user list from API, display in dialer
   - `call` — SIP registration, outgoing call, in-call UI
   - Native integration: CallKit (iOS), ConnectionService (Android)
   - Incoming call — PushKit/FCM handlers
   - `wallet` — balance + ledger screen
   - `messaging` — announcements + tasks

6. Tests:
   - Unit tests for every use case and repository
   - Widget tests for every screen
   - Integration tests for the three critical flows

7. iOS setup:
   - PushKit registration in `AppDelegate.swift`
   - CallKit entitlements
   - Background modes: `voip`, `audio`, `background-fetch`

8. Android setup:
   - FCM integration
   - Foreground service for incoming calls
   - `RECORD_AUDIO`, `FOREGROUND_SERVICE_PHONE_CALL` permissions

**Verification:**
```bash
cd civio-app
flutter pub get
dart format --set-exit-if-changed lib/ test/
dart analyze --fatal-infos lib/ test/
flutter test --coverage
# Manual: run on iOS simulator and Android emulator, place a call to the Asterisk seed user
flutter run
```

---

## Phase 10 — Testing harness & CI

**Goal:** Every PR runs the full CI matrix and must pass before merge.

**Tasks:**

1. Create `docker-compose.test.yml` — postgres/redis/rabbitmq on test ports (5433/6380/5673)

2. Create `docker-compose.e2e.yml` — full stack: cloud + edge + opensips + asterisk + sipp

3. Create `scripts/e2e.sh` — runs the 5 scenarios from `docs/05-test-strategy.md`

4. Create SIPp scenarios in `tests/e2e/sipp/`:
   - `register_tls.xml`
   - `place_call.xml`
   - `ddos_protection.xml`

5. Configure branch protection on `main` requiring CI green + 1 review

6. Write operational runbooks in `docs/runbooks/`:
   - `incident-compromised-credentials.md`
   - `incident-data-breach.md`
   - `incident-ddos.md`
   - `incident-ransomware.md`
   - `disaster-recovery.md`

7. Add monitoring: Prometheus scrape configs, Grafana dashboards (JSON in `ops/grafana/`)

**Verification:**
```bash
# Run full suite
/project:run-full-test-suite

# Verify CI config
gh workflow list
gh workflow run ci.yml
```

---

## Phase 11 — Admin web (optional MVP)

**Goal:** Web console for Civio staff to manage communities, view CDRs, and diagnose sync issues.

This phase is scoped to an MVP — just enough to replace direct database access for ops.

**Tasks:**

1. Initialize Vite + React + TypeScript in `civio-cloud/admin-web/`
2. Install shadcn/ui, React Router, TanStack Query, Zod, React Hook Form
3. Generate API client from `docs/03-api-contract.yaml` with `openapi-typescript-codegen`
4. Build pages: login, communities list, community detail, users table, CDR search, sync health, token ledger
5. Tests: Playwright for critical flows

**Verification:**
```bash
cd civio-cloud/admin-web
npm run lint
npm run type-check
npm run test
npm run build
```

---

## Cross-phase notes for Claude Code

### When you finish a phase

1. Run its verification commands
2. If green, commit with message: `feat(phase-N): <short summary>`
3. Push and open a PR
4. Wait for CI green
5. Self-review: read the diff and verify it aligns with the phase's contract
6. Only then proceed to the next phase

### If a verification command fails

1. Read the full error output
2. Identify the specific failure (type error? test assertion? compile error?)
3. Fix the code
4. Re-run the specific failing command (don't re-run the whole suite yet)
5. Once that command passes, re-run the whole phase's verification
6. If a test assertion is wrong (not the code), fix the test and document why in the commit message

### If you encounter ambiguity

The CLAUDE.md files in each subdirectory are authoritative. If a CLAUDE.md conflicts with this playbook, the CLAUDE.md wins — this playbook describes the order, not the details.

If the requirement is genuinely undefined (not covered in any CLAUDE.md or docs/), stop and ask the human engineer. Do not guess on architecture-level decisions.

### Speed vs quality

- Never skip tests to move faster
- Never disable linters or type checkers to move faster
- Never merge code that fails CI
- If you're stuck on a single problem for >30 minutes, document what you've tried and ask for help

---

## Ready-to-run starter command

When Claude Code first opens this project, the user will typically say:

> "Please start implementing Civio from Phase 1."

Claude Code's response should:
1. Acknowledge the 11-phase plan
2. Ask the user to confirm their target environment (local/staging/production)
3. Begin Phase 1 without further prompting if confirmed
4. Report progress at the end of each phase with verification output
