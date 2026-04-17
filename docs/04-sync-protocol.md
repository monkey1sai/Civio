# 04 — Cloud-to-edge sync protocol

This document specifies how community edge nodes synchronize with the cloud master database. It covers initial bootstrap (full sync), ongoing updates (delta sync), verification (Merkle tree), and recovery (resync).

## Principles

1. **Cloud is the single source of truth.** Edge data is always a view; it is never authoritative.
2. **Monotonic versioning.** Every write to synced tables bumps a per-community counter.
3. **Idempotent application.** Applying the same row twice produces the same state.
4. **Eventual consistency with ACK.** Target propagation SLA is 60 seconds end-to-end.
5. **Fail-safe verification.** Merkle root checks detect drift; mismatches trigger automatic full resync.

## Synced entities

These tables sync to edge (in this order):

1. `communities` — the edge's own community row
2. `units`
3. `users`
4. `user_unit_relations`
5. `sip_endpoints` — maps to edge `ps_endpoints` + `ps_auths` + `ps_aors`
6. `friend_mappings`
7. Token snapshots (current balances only, not full ledger)
8. `announcements`
9. `tasks` (only those assigned to this community)

NOT synced to edge (cloud only):
- `call_logs`, `billing_records`, `audit_log`, `payment_orders`, `consent_records`

## Version numbering

Each community has a `current_version` BIGINT in `communities`. Every INSERT/UPDATE/DELETE on synced tables that belong to that community increments it via the `tg_bump_community_version` trigger.

Each synced row carries a `sync_version` BIGINT equal to the community version at the time of the write. This allows the edge to request "all changes since version X".

## 1. Bootstrap — full sync

Used when:
- Edge node is first provisioned
- Edge detects Merkle mismatch
- Edge has been offline > 7 days (delta window lapses)
- Operator triggers via ops console

### Flow

```
Edge                                      Cloud
 │                                          │
 │── POST /sync/full/begin ─────────────▶  │  create snapshot, return snapshot_id + total_rows
 │                                          │
 │◀──── {snapshot_id, version, total} ────  │
 │                                          │
 │── GET /sync/full/{snapshot_id}          │
 │     ?cursor=0&limit=1000 ───────────▶   │
 │                                          │
 │◀─── {rows, next_cursor, checksum} ───── │
 │                                          │
 │ (repeat until next_cursor is null)       │
 │                                          │
 │ local: verify each page checksum         │
 │ local: apply to staging tables           │
 │                                          │
 │── POST /sync/full/commit ───────────▶   │  compute expected_merkle_root
 │     {snapshot_id, merkle_root} ─▶       │  compare with edge's
 │                                          │
 │◀───── {status: ok} ────────────────────  │
 │                                          │
 │ local: swap staging → live in txn        │
 │ local: update sync_state                 │
```

### Data format

```json
{
  "snapshot_id": "snap_<uuid>",
  "community_id": "<uuid>",
  "version": 12345,
  "rows": [
    {
      "entity_type": "users",
      "entity_id": "<uuid>",
      "data": { ...all columns... },
      "version": 12340
    },
    ...
  ],
  "next_cursor": "opaque-string",
  "page_checksum": "sha256-of-serialized-rows"
}
```

### Properties

- Page size: 1000 rows
- Each page carries its own SHA-256 checksum for transport verification
- Edge writes to `staging_*` tables, only swaps to live `ps_*` tables after commit
- Swap is a single transaction: `BEGIN; TRUNCATE ps_endpoints; INSERT INTO ps_endpoints SELECT * FROM staging_sip_endpoints; ...; COMMIT;`

## 2. Delta sync (steady state)

Runs every 30 seconds on every edge.

### Flow

```
Edge                                      Cloud
 │                                          │
 │── GET /sync/delta                       │
 │     ?community_id=X&since=V ────────▶   │
 │                                          │
 │                                          │  query sync_events
 │                                          │  WHERE community_id = X
 │                                          │    AND version > V
 │                                          │  ORDER BY version LIMIT 500
 │                                          │
 │◀──── DeltaBatch{from_v, to_v, rows} ──  │
 │                                          │
 │ local: for each row:                     │
 │   if operation = upsert:                 │
 │     UPSERT into ps_* / snapshot_*        │
 │   if operation = tombstone:              │
 │     mark deleted_at, keep row            │
 │                                          │
 │ local: compute merkle_root               │
 │                                          │
 │── POST /sync/ack                         │
 │     {community_id, version, ──────────▶ │
 │      merkle_root}                        │
 │                                          │
 │                                          │  verify merkle_root
 │◀──── {status: ok} ─── OR ────────────── │
 │◀──── {status: merkle_mismatch,          │
 │       expected_merkle_root: "..."}      │
 │                                          │
 │ if mismatch → trigger full resync        │
```

### Delta row format

```json
{
  "entity_type": "sip_endpoints",
  "entity_id": "<uuid>",
  "operation": "upsert",
  "data": {
    "id": "<uuid>",
    "user_id": "<uuid>",
    "username": "1001",
    "password_hash": "<bcrypt>",
    ...
  },
  "version": 12345
}
```

For deletions, `operation = "tombstone"` and `data` contains only the `id`.

## 3. Merkle tree verification

### Construction

For every synced table on both cloud and edge:

1. Compute `row_hash = sha256(sorted_kv_serialization(row))` for each row
2. Sort `row_hash` values lexicographically
3. Build binary Merkle tree; leaf = `row_hash`, internal node = `sha256(left || right)`
4. Root = top of tree

### Per-community Merkle root

Combine table roots:

```
merkle_root = sha256(
  sorted_concat(
    "communities:"    + merkle_root(communities_rows),
    "units:"          + merkle_root(units_rows),
    "users:"          + merkle_root(users_rows),
    "sip_endpoints:"  + merkle_root(sip_endpoints_rows),
    "friend_mappings:"+ merkle_root(friend_mappings_rows),
    ...
  )
)
```

### Reference implementation (Python)

```python
import hashlib
import json
from typing import Sequence

def row_hash(row: dict) -> bytes:
    canonical = json.dumps(row, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).digest()

def merkle_root(rows: Sequence[dict]) -> str:
    if not rows:
        return hashlib.sha256(b"").hexdigest()
    hashes = sorted(row_hash(r) for r in rows)
    while len(hashes) > 1:
        if len(hashes) % 2 == 1:
            hashes.append(hashes[-1])  # duplicate last
        hashes = [
            hashlib.sha256(hashes[i] + hashes[i + 1]).digest()
            for i in range(0, len(hashes), 2)
        ]
    return hashes[0].hex()
```

Both cloud and edge MUST implement this identically. Any discrepancy = mismatch.

## 4. Recovery

### Merkle mismatch

Cloud detects mismatch → responds to `/sync/ack` with `{status: "merkle_mismatch", expected_merkle_root: "..."}`.

Edge behaviour:
1. Log full diagnostic: local vs cloud root, last delta version
2. Mark `sync_state.health_status = "resyncing"`
3. Trigger full sync (section 1)
4. On commit success, mark `health_status = "healthy"`

### Stale version

If edge's `since` is older than cloud's oldest `sync_events` row (pruned after 7 days), cloud responds with `{status: "stale_version"}`. Edge must perform full resync.

### Network outage

Edge `sync_agent` retries with exponential backoff: 30s → 60s → 120s → 300s → 600s (capped). Never gives up.

## 5. Event pruning

Cloud retains `sync_events` rows for 7 days after creation. A daily cron job prunes older rows. Communities that lag more than 7 days MUST do a full sync.

## 6. Security

- Every sync request carries `X-Civio-Shared-Secret` (one secret per edge, rotated annually)
- Every sync request is signed: `X-Civio-Signature: hmac-sha256(body, secret)`
- Cloud validates signature; rejects with 401 otherwise
- Communication is always TLS 1.2+

## 7. Test harness

Claude Code MUST produce these integration tests:

1. **Happy path full sync:** cloud has 100 users → edge requests full → applies → Merkle matches
2. **Happy path delta:** cloud creates 5 new users → edge pulls delta → applies → Merkle matches
3. **Merkle mismatch recovery:** corrupt one row on edge → next delta ack fails → automatic full resync succeeds
4. **Network outage:** cut edge→cloud for 10 minutes during 50 writes → after reconnect, delta catches up
5. **Stale version:** set edge's `since` to cloud's pruned range → receives `stale_version` → triggers full sync
6. **Tombstone:** cloud deletes a user → delta carries tombstone → edge marks deleted → user can no longer register
