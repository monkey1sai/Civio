# CLAUDE.md — civio-edge

## Scope
This subproject is the **per-community edge node**: a Docker Compose bundle deployed at each community site (on a NUC, small server, or cloud VM). It runs:

- Asterisk 22 PJSIP with Realtime Architecture, registered against local PostgreSQL
- Local PostgreSQL 15 holding Asterisk Realtime tables + cached community data
- Redis 7 for hot-path caches (friend map, token snapshot)
- `sync_agent` — Python daemon pulling delta from cloud every 30s
- `event_publisher` — Python daemon subscribing to Asterisk AMI and publishing to cloud RabbitMQ
- `auth_callback` — tiny FastAPI service called by OpenSIPS (runs in cloud) to make allow/deny decisions; edge runs a local fallback copy
- `rtpengine` + `coturn` for NAT traversal

Every community gets one instance. Instances are **stateless beyond cache** — if a node is lost, replace the hardware and trigger a full sync.

## Key design principles

1. **Cloud is the source of truth.** Never write business data directly to the edge DB. All changes go through cloud API and arrive via sync.
2. **Fail open for availability, closed for security.** If the edge cannot reach the cloud:
   - SIP REGISTER continues to work (using last synced credentials)
   - INVITE for same-community calls continues (using local snapshot)
   - Cross-community INVITE → DENY (never bypass policy)
   - Token deduction queued locally, reconciled when cloud returns
3. **Host networking for Asterisk.** Docker bridge mode breaks SIP/RTP. Always `network_mode: host`.
4. **Idempotent sync.** Applying the same delta batch twice must produce the same state.

## Directory layout

```
civio-edge/
├── CLAUDE.md                       this file
├── docker-compose.yml              full bundle (Asterisk + agents + db + cache)
├── .env.example
├── asterisk/
│   ├── Dockerfile                  multi-stage from debian:bookworm-slim
│   └── config/
│       ├── asterisk.conf
│       ├── modules.conf
│       ├── pjsip.conf              transports only, endpoints via realtime
│       ├── sorcery.conf            maps pjsip types to realtime
│       ├── extconfig.conf          maps realtime to pgsql
│       ├── res_pgsql.conf          pgsql connection
│       ├── extensions.conf         dialplan: context per community
│       ├── rtp.conf                rtp range 10000-20000
│       └── manager.conf            AMI user for event_publisher
├── postgres/
│   └── init.sql                    creates ps_* tables + snapshot tables
├── sync_agent/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── src/
│       ├── __main__.py             entry point, schedules pull loop
│       ├── config.py
│       ├── cloud_client.py         httpx async client, signed requests
│       ├── applier.py              applies DeltaBatch to local DB
│       ├── merkle.py               MerkleCalculator
│       ├── state_store.py          reads/writes local sync_state
│       └── models.py               pydantic: DeltaBatch, SyncRow
├── event_publisher/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── src/
│       ├── __main__.py
│       ├── config.py
│       ├── ami_listener.py         uses panoramisk
│       ├── event_mapper.py         AMI event → CloudEvent
│       ├── mq_publisher.py         aio-pika to cloud RabbitMQ
│       └── outbox.py               local SQLite outbox for offline resilience
├── auth_callback/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── src/
│       ├── __main__.py             FastAPI app
│       ├── routes.py               POST /authorize
│       ├── cloud_bridge.py         httpx call to cloud, 5s timeout
│       └── local_policy.py         fallback using local snapshot
├── rtpengine/
│   └── rtpengine.conf
├── coturn/
│   └── turnserver.conf
└── tests/
    ├── test_sync_agent.py
    ├── test_event_mapper.py
    └── test_local_policy.py
```

## Asterisk configuration — critical bits

### `pjsip.conf` (transports only; endpoints via realtime)

```ini
[transport-udp]
type=transport
protocol=udp
bind=0.0.0.0:5060
local_net=172.16.0.0/12
local_net=10.0.0.0/8
local_net=192.168.0.0/16
external_media_address=${EDGE_PUBLIC_IP}
external_signaling_address=${EDGE_PUBLIC_IP}

[transport-tls]
type=transport
protocol=tls
bind=0.0.0.0:5061
cert_file=/etc/asterisk/keys/fullchain.pem
priv_key_file=/etc/asterisk/keys/privkey.pem
method=tlsv1_2
external_media_address=${EDGE_PUBLIC_IP}
external_signaling_address=${EDGE_PUBLIC_IP}

[transport-wss]
type=transport
protocol=wss
bind=0.0.0.0:8089
cert_file=/etc/asterisk/keys/fullchain.pem
priv_key_file=/etc/asterisk/keys/privkey.pem
method=tlsv1_2
```

### `sorcery.conf`

```ini
[res_pjsip]
endpoint=realtime,ps_endpoints
auth=realtime,ps_auths
aor=realtime,ps_aors
contact=realtime,ps_contacts
transport=config,pjsip.conf,1
global=config,pjsip.conf,1
```

### `extconfig.conf`

```ini
[settings]
ps_endpoints => pgsql,asterisk,ps_endpoints
ps_auths => pgsql,asterisk,ps_auths
ps_aors => pgsql,asterisk,ps_aors
ps_contacts => pgsql,asterisk,ps_contacts
```

### Every endpoint row in `ps_endpoints` MUST set

```
direct_media=no
force_rport=yes
rewrite_contact=yes
rtp_symmetric=yes
media_encryption=sdes
media_encryption_optimistic=no
webrtc=yes            -- for Flutter clients using WSS
```

### `extensions.conf` — dialplan per community

Each community has its own context `tenant-<community_id>-internal`. The dialplan MUST call out to `auth_callback` before bridging:

```
[tenant-COMMUNITYID-internal]
exten => _X.,1,NoOp(Call ${CALLERID(num)} -> ${EXTEN})
 same => n,Set(AUTH=${CURL(http://auth-callback:8000/authorize,{"caller":"${CALLERID(num)}","callee":"${EXTEN}"})})
 same => n,GotoIf($["${AUTH}" = "allow"]?bridge:deny)
 same => n(deny),Hangup(21)
 same => n(bridge),Dial(PJSIP/${EXTEN},30)
 same => n,Hangup()
```

## Sync agent contract

```python
class SyncAgent:
    def __init__(
        self,
        cloud_client: CloudClient,
        applier: DeltaApplier,
        state_store: StateStore,
        interval_sec: int = 30,
    ) -> None: ...

    async def run_forever(self) -> None:
        """Main loop. Never raises — logs and continues."""

    async def pull_once(self) -> SyncResult:
        """One cycle: check state, pull delta, apply, ack."""

    async def full_resync(self, reason: str) -> None:
        """Called when Merkle mismatch detected or state lost."""
```

Pull cycle:
1. Read local `sync_state.last_delta_version` → `v`
2. `GET /api/v1/sync/delta?since=v` → `DeltaBatch`
3. Apply each row in a single transaction
4. Compute local Merkle root
5. `POST /api/v1/sync/ack` with `version` + `merkle_root`
6. If ack returns `merkle_mismatch` → `full_resync("merkle_mismatch")`

## Event publisher contract

Listens to these Asterisk AMI events:

| AMI event | Maps to CloudEvent type |
|---|---|
| `Newchannel` | `call.started` |
| `DialBegin` | `call.ringing` |
| `DialEnd` | `call.answered` or `call.rejected` |
| `Hangup` | `call.ended` (includes duration, hangup cause) |
| `PeerStatus` | `sip.endpoint.status_changed` |

```python
class EventPublisher:
    async def start(self) -> None: ...
    async def stop(self) -> None: ...

class EventMapper:
    @staticmethod
    def map_ami_event(ami: dict) -> CloudEvent | None: ...

class MqPublisher:
    async def publish(self, event: CloudEvent) -> None:
        """Writes to local outbox first, then publishes to cloud.
        On connection failure, events stay in outbox until drained."""
```

The **local outbox pattern** is non-negotiable. If the cloud RabbitMQ is unreachable, events go into SQLite. A background task drains the outbox with exponential backoff. Without this, CDRs are lost during network outages.

## Auth callback contract

```python
# POST /authorize
# Request:
{
  "caller_sip_uri": "1001",
  "callee_sip_uri": "1002",
  "call_id": "<sip call-id>"
}

# Response: 200 OK (always), decision in body
{
  "decision": "allow" | "deny",
  "reason": "family" | "friend" | "admin_always" | "not_friend" | "no_token" | "cross_community" | "unknown_user" | "user_revoked",
  "billing_scope": "user" | "community" | "free" | null,
  "max_duration_sec": 3600
}
```

Behaviour:
1. Try cloud first: `POST <cloud>/api/v1/sip/authorize` with 5s timeout
2. On timeout or 5xx, fall back to local policy evaluation using cached data
3. On cross-community fallback → always DENY (never trust stale data for cross-tenant)
4. Every decision logged to local SQLite and also queued for publish

## Verification commands

```bash
# Lint + type
poetry run ruff check src/
poetry run mypy src/ --strict

# Unit tests
poetry run pytest tests -x -q

# Compose
docker compose config -q
docker compose build

# Smoke test (requires running cloud)
./scripts/smoke.sh
```

## Constraints specific to edge

- NEVER issue SQL write statements directly to `ps_endpoints`, `ps_auths`, `ps_aors` from anywhere except `sync_agent.applier`. These are populated purely by sync.
- NEVER expose `postgres` or `redis` ports outside the Docker network. Only Asterisk ports (5060/5061/8089) are on the host.
- NEVER allow `auth_callback` to fall back on local policy for cross-community calls.
- NEVER delete rows from the local `snapshot_*` tables. Upsert only. Deletion arrives as a tombstone row with `deleted_at` set.
- NEVER embed the cloud RabbitMQ credentials in the Asterisk container. Only `event_publisher` has them.
