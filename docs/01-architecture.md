# 01 — Architecture

## Three tiers

Civio is a three-tier platform:

```
┌──────────────────────────────────────────────────────────┐
│   Client tier                                            │
│   ┌─────────────┐  ┌───────────┐  ┌─────────────────┐   │
│   │ Resident    │  │ Admin     │  │ Ops console     │   │
│   │ Flutter app │  │ React web │  │ Internal staff  │   │
│   └─────────────┘  └───────────┘  └─────────────────┘   │
└──────────┬──────────────┬──────────────┬─────────────────┘
           │ HTTPS/WSS    │ HTTPS        │
           ▼              ▼              ▼
┌──────────────────────────────────────────────────────────┐
│   Cloud control plane (single cluster, multi-AZ)         │
│                                                          │
│   ┌────────────┐   ┌───────────────┐   ┌─────────────┐  │
│   │ OpenSIPS   │   │ FastAPI core  │   │ RabbitMQ    │  │
│   │ (5060/5061)│   │ (443)         │   │ (5672)      │  │
│   └────────────┘   └───────────────┘   └─────────────┘  │
│        │                  │                    │         │
│        └──────┬───────────┴────────┬───────────┘         │
│               ▼                    ▼                     │
│         ┌───────────┐        ┌─────────┐                 │
│         │ PostgreSQL│        │ Redis   │                 │
│         │ primary + │        │ cache   │                 │
│         │ replica   │        │         │                 │
│         └───────────┘        └─────────┘                 │
└──────────┬────────────────────────────────────────┬──────┘
           │ AMQP/TLS + HTTPS sync                  │ SIP/TLS
           ▼                                        ▼
┌──────────────────────────────────────────────────────────┐
│   Community edge tier (one per community)                │
│                                                          │
│   ┌────────────┐  ┌──────────┐  ┌──────────┐            │
│   │ Asterisk   │  │ Sync     │  │ Event    │            │
│   │ 22 PJSIP   │  │ agent    │  │ publisher│            │
│   └────────────┘  └──────────┘  └──────────┘            │
│        ▲                 │              │                │
│        │                 ▼              │                │
│   ┌────────────┐  ┌──────────┐          │                │
│   │ rtpengine  │  │ Local    │          │                │
│   │ coturn     │  │ Postgres │          │                │
│   └────────────┘  └──────────┘          │                │
└──────────────────────────────────────────┴───────────────┘
```

## Communication contracts

| From | To | Protocol | Notes |
|---|---|---|---|
| Resident app | Cloud API | HTTPS REST | JWT-auth, HTTP/2 |
| Resident app | OpenSIPS | WSS (SIP over WebSocket) | TLS mandatory |
| Resident app | Community Asterisk (media) | SRTP/DTLS via ICE | coturn relay fallback |
| Admin web | Cloud API | HTTPS REST | JWT with admin role |
| OpenSIPS | FastAPI | HTTP POST | shared-secret callback |
| OpenSIPS | Asterisk | SIP over TLS | dispatcher module |
| Sync agent | Cloud API | HTTPS REST | signed with edge cert |
| Event publisher | RabbitMQ | AMQP over TLS | SASL PLAIN |
| Cloud workers | RabbitMQ | AMQP | local network |
| Cloud API | PostgreSQL | TCP | asyncpg |
| Cloud API | Redis | TCP | redis-py |

## Data flow lanes

Three primary lanes:

### 1. Write lane (e.g. admin creates a user)

```
Admin web → POST /api/v1/users → FastAPI
  → UserRepository.create()
  → PostgreSQL master.users INSERT
  → SipProvisioningService.create_endpoint()
  → PostgreSQL master.sip_endpoints INSERT
  → SyncService.emit_event("user.provisioned", {...})
  → PostgreSQL master.sync_events INSERT (version++)
  → RabbitMQ publish civio.events "user.provisioned"

Every 30s: community edge sync_agent
  → GET /api/v1/sync/delta?since=<v>
  → Receives {rows: [...user, ...sip_endpoint]}
  → Applies to local ps_endpoints, ps_auths, ps_aors
  → Asterisk reloads endpoint from realtime on next REGISTER
  → POST /api/v1/sync/ack with merkle_root
```

Delivery SLA: < 60 seconds from admin action to edge readiness.

### 2. Call lane (resident dials another resident)

```
Resident A (Flutter)
  → SIP INVITE over WSS → OpenSIPS (cloud)
  → dispatcher selects community-A Asterisk
  → INVITE forwarded to Asterisk via TLS
  → Asterisk dialplan:
      CURL http://auth-callback/authorize
      → auth-callback asks cloud /api/v1/sip/authorize
        → CallPolicyService.authorize(A, B)
        → returns {decision: "allow", billing_scope: "user", max_duration: 3600}
      → returns "allow"
  → Dial(PJSIP/B) → B's registered device
  → Resident B rings, answers
  → SDP negotiated, SRTP media flows direct (or via rtpengine)
```

Signalling SLA: INVITE → ringing < 800ms.

### 3. Event lane (call ends, billing happens)

```
Asterisk Hangup event
  → AMI → event_publisher (edge)
  → Maps to CloudEvent "call.ended"
  → Writes to local SQLite outbox (durability)
  → Publishes to cloud RabbitMQ civio.events

Cloud CDR consumer
  → Inserts call_logs row
  → Publishes "billing.charge"

Cloud billing worker
  → TokenLedgerRepository.append_entry(delta=-cost, reason="call")
  → Updates TokenBalance view

Cloud audit consumer
  → Appends immutable audit record
```

Billing SLA: < 10 seconds from hangup to token deduction visible.

## Tenant isolation model

**Row-level isolation** via `community_id` on every table. No schema-per-tenant — schemas don't scale for Alembic migrations.

- Every query in service/repository layer scopes by the caller's `community_id` (from JWT)
- Super-admins (Civio staff) can scope by explicit `?community_id=` query param
- A session-level SQLAlchemy event listener injects `community_id` filter automatically into all SELECTs

## Failure modes and behaviour

| Failure | Behaviour |
|---|---|
| Cloud API down | Edge: existing registrations keep working; new registrations fail. App retries with backoff. |
| Cloud DB primary down | Replicas continue read traffic; writes queue at API layer up to 60s. |
| RabbitMQ down | Event publishers buffer to local outbox. No data loss. |
| Edge node down | Residents see "community offline" in app. Cannot place or receive calls until replaced. |
| Network partition edge ↔ cloud | Edge serves same-community calls from local cache. Cross-community calls denied. Outbox fills. |
| Asterisk crash | Edge systemd restarts. Registrations re-establish within 60s. |

## Deployment topology

- **Local dev:** single `docker-compose up` runs cloud + one edge + one community DB
- **Staging:** cloud on one VPC, one edge on a separate VPC simulating a real community
- **Production cloud:** Kubernetes-ready, but initial deployment is Docker Compose on a dedicated VM per tier
- **Production edge:** NUC or small server at each community, managed via the ops console

## Observability

Every tier exports Prometheus metrics:

- `civio_api_request_duration_seconds` (labels: method, path, status)
- `civio_call_auth_decisions_total` (labels: decision, reason)
- `civio_sync_delta_rows` (labels: community_id)
- `civio_event_bus_publish_total` (labels: event_type, status)
- `civio_token_ledger_balance` (labels: scope, community_id)
- `asterisk_active_channels` (labels: community_id)

Alerts fire on:

- Call auth deny rate > 20% for 5 minutes
- Sync lag > 5 minutes for any community
- Event bus consumer lag > 1000 messages
- SIP Register failure rate > 5%
- Token balance negative for any account
