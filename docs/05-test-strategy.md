# 05 — Test strategy

This document defines the testing bar. No feature is "done" until it passes all applicable gates.

## Testing pyramid

```
        ┌───────────────┐
        │   E2E (5%)    │   SIPp + real Asterisk + real API
        ├───────────────┤
        │ Integration   │   docker-compose.test.yml
        │    (20%)      │   API + PostgreSQL + RabbitMQ + Redis
        ├───────────────┤
        │ Contract (5%) │   Schemathesis against OpenAPI
        ├───────────────┤
        │   Unit (70%)  │   pure functions, mocked dependencies
        └───────────────┘
```

## Coverage targets

| Layer | Target | Tool |
|---|---|---|
| Cloud services | 90% | pytest-cov |
| Cloud repositories | 85% | pytest-cov |
| Cloud API | 80% | pytest-cov |
| Cloud overall | 80% | pytest-cov |
| Edge agents | 80% | pytest-cov |
| Flutter app | 70% | flutter test --coverage |
| Contract tests | 100% endpoints | schemathesis |

## Unit tests

### Cloud — what must be tested

Every service method, every repository method, every use case:

```python
# Example: tests/unit/services/test_call_policy_service.py
class TestCallPolicyService:
    async def test_same_unit_family_allow(self, service, db):
        # Arrange: two users in the same unit
        ...
        # Act
        decision = await service.authorize(caller_uri, callee_uri)
        # Assert
        assert decision.decision == "allow"
        assert decision.reason == "family"

    async def test_different_community_deny(self, service): ...
    async def test_zero_tokens_no_coverage_deny(self, service): ...
    async def test_revoked_user_deny(self, service): ...
    # ... full matrix from civio-cloud/CLAUDE.md
```

Rule: one assertion per behavioural aspect. Do not combine unrelated assertions.

### Flutter — what must be tested

- Every use case
- Every repository implementation (with mocked data source)
- Every reducer / StateNotifier (Riverpod)
- Every widget's golden image (via `flutter_test`)

```dart
// Example: test/features/call/domain/use_cases/make_call_use_case_test.dart
void main() {
  late MockCallRepository repo;
  late MakeCallUseCase useCase;

  setUp(() {
    repo = MockCallRepository();
    useCase = MakeCallUseCase(repo);
  });

  test('returns failure when target uri is empty', () async {
    final result = await useCase('');
    expect(result.isFailure, true);
    verifyNever(() => repo.makeCall(any()));
  });

  test('delegates to repository on valid uri', () async {
    when(() => repo.makeCall('sip:1001@c.example.com'))
        .thenAnswer((_) async => Call(id: 'c1'));
    final result = await useCase('sip:1001@c.example.com');
    expect(result.isSuccess, true);
  });
}
```

## Integration tests

### Cloud

`tests/integration/` spins up real dependencies via `docker-compose.test.yml`:

- PostgreSQL 16 on port 5433
- Redis 7 on port 6380
- RabbitMQ 3.13 on port 5673

Each test class uses a transactional fixture that rolls back after the test:

```python
@pytest_asyncio.fixture
async def db_session(engine):
    connection = await engine.connect()
    trans = await connection.begin()
    session = AsyncSession(bind=connection)
    yield session
    await trans.rollback()
    await connection.close()
```

Key integration tests (MUST exist):

| File | What it verifies |
|---|---|
| `test_auth_flow.py` | full OTP → token → protected endpoint |
| `test_sip_authorize.py` | call policy endpoint with real DB |
| `test_sync_full.py` | full sync end-to-end with Merkle |
| `test_sync_delta.py` | delta sync with ACK |
| `test_cdr_consumer.py` | publish event → consumer writes call_log |
| `test_billing_worker.py` | call_log → token ledger entry |
| `test_migrations.py` | alembic upgrade head + downgrade base |

### Flutter

`integration_test/`:

- `login_flow_test.dart` — enter mobile → OTP → home
- `place_call_test.dart` — dial number → INVITE sent to mock SIP server → answered
- `receive_call_test.dart` — inject INVITE → CallKit UI appears → answer → media flows

## Contract tests

Use `schemathesis` to verify the FastAPI implementation matches `docs/03-api-contract.yaml`:

```bash
schemathesis run docs/03-api-contract.yaml \
  --base-url http://localhost:8000 \
  --checks all \
  --hypothesis-max-examples 100
```

Runs on every PR in CI.

## E2E tests

Located in `tests/e2e/`. Orchestrated by `docker-compose.e2e.yml` which brings up:

- Cloud API + worker
- PostgreSQL + Redis + RabbitMQ
- One Asterisk edge with local PostgreSQL
- OpenSIPS proxy
- Optional: mock Flutter via SIPp

### Must-have E2E scenarios

1. **New community onboarding**
   - Admin creates community via API
   - Admin creates 2 users
   - Sync completes within 60s
   - Both users REGISTER successfully via SIPp
   - User A calls User B, call connects for 5s
   - CDR appears in `call_logs`
   - Token ledger debited

2. **Cross-community deny**
   - User in community X calls user in community Y
   - OpenSIPS receives INVITE
   - Auth callback denies
   - SIP response 403
   - Audit log records denial

3. **Ownership transfer**
   - Admin sets `ownership_status = sold` on a unit
   - Within 60s, old owner's `auth_status = revoked` in edge
   - Old owner's REGISTER fails

4. **Token depletion**
   - User with balance = 1 token
   - Places long call (exceeds 1 token of duration)
   - Call is forcibly terminated when `max_duration_sec` reached
   - Ledger entries correct, balance = 0

5. **Edge recovery**
   - Stop edge Asterisk mid-call
   - Verify cloud marks community as unhealthy within 60s
   - Restart edge
   - Health returns, next registrations succeed

### SIPp scenarios

`tests/e2e/sipp/`:
- `register_tls.xml` — TLS registration with digest auth
- `place_call.xml` — INVITE, answer, BYE
- `ddos_protection.xml` — flood REGISTER, verify pike blocks

## Load tests

Target capacity per edge:
- 500 concurrent registrations
- 100 concurrent active calls
- 50 call setups per second peak

`tests/load/` contains SIPp + Locust scripts. Runs weekly in staging, not per PR.

## Test data

- Unit tests: use factory_boy factories (`tests/factories/`)
- Integration tests: use factories + DB fixtures
- E2E tests: seed via cloud API calls (don't touch DB directly)

## CI pipeline

`.github/workflows/ci.yml`:

```yaml
jobs:
  lint:
    - ruff check
    - ruff format --check
    - mypy --strict
    - dart format --set-exit-if-changed
    - dart analyze

  unit:
    - pytest tests/unit --cov
    - flutter test --coverage

  integration:
    services: [postgres, redis, rabbitmq]
    - pytest tests/integration
    - schemathesis run

  build:
    - docker compose build

  e2e:
    needs: [unit, integration, build]
    - docker compose -f docker-compose.e2e.yml up -d
    - pytest tests/e2e
    - docker compose -f docker-compose.e2e.yml down
```

A PR cannot merge unless **all** of the above pass.

## Definition of done (task-level)

A task is complete when:

- [ ] Code is written and follows the conventions in the relevant CLAUDE.md
- [ ] Unit tests exist and pass
- [ ] If the task involves API changes: integration test exists
- [ ] If the task involves schema changes: Alembic migration exists + `alembic check` passes
- [ ] Coverage has not regressed
- [ ] `ruff`, `mypy`, `dart analyze` all pass
- [ ] Documentation in relevant CLAUDE.md or docs/ is updated if behaviour changed
- [ ] Conventional commit message written
