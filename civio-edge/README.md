# civio-edge

Per-community edge bundle. Deployed once at each community site (NUC, small server, or cloud VM).

## Before touching this directory

**Read `CLAUDE.md` in this folder first.**

## Quick reference

```bash
# Bring up the edge stack
docker compose up -d

# Check Asterisk
docker compose exec asterisk asterisk -rx "pjsip show endpoints"
docker compose exec asterisk asterisk -rx "pjsip show transports"

# Check sync status
docker compose logs -f sync-agent

# Check event publisher
docker compose logs -f event-publisher
```

## Services in this bundle

- `asterisk` — SIP server with PJSIP + Realtime, host network mode
- `rtpengine` — NAT traversal
- `coturn` — STUN/TURN for WebRTC clients
- `postgres` — local cache, Asterisk Realtime tables
- `redis` — hot-path caches
- `sync-agent` — pulls delta from cloud every 30s
- `event-publisher` — subscribes to Asterisk AMI, publishes CDR to cloud
- `auth-callback` — local fallback SIP authorization service

## Further reading

- `/docs/01-architecture.md`
- `/docs/04-sync-protocol.md`
- `/docs/06-security-checklist.md`
