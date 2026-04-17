# 06 — Security checklist

Pre-launch and ongoing security requirements. Every item is **mandatory** unless explicitly marked optional.

## Transport

- [ ] All SIP signalling is TLS 1.2+ (no UDP/TCP on public ports)
- [ ] All media is SRTP (SDES for native clients, DTLS-SRTP for WebRTC)
- [ ] All HTTPS uses TLS 1.3 where possible, 1.2 minimum
- [ ] Let's Encrypt certs auto-renewed via Traefik
- [ ] HTTP strict transport security (HSTS) with 1-year max-age
- [ ] Valid cipher suites only: `ECDHE-*GCM*` and `TLS_AES_*_GCM_*`
- [ ] No SSL 3.0, TLS 1.0, TLS 1.1 anywhere

## Authentication & authorization

- [ ] Passwords hashed with bcrypt, cost factor >= 12
- [ ] OTPs are 6 digits, TTL 5 minutes, one-time use
- [ ] JWT access tokens: 15-minute expiry
- [ ] JWT refresh tokens: 7-day expiry, rotated on every use
- [ ] JWT secret is >= 32 bytes, rotated quarterly
- [ ] `JWT_SECRET` never appears in logs, errors, or client-facing responses
- [ ] Role-based access enforced at router level via dependency
- [ ] Super-admin actions require re-authentication (step-up auth)
- [ ] Sessions can be revoked; check Redis denylist on every request
- [ ] OpenSIPS auth callback uses shared secret (rotated annually)
- [ ] Sync API uses shared secret + HMAC body signature

## API hardening

- [ ] Rate limiting on all public endpoints (Traefik + Redis)
  - Anonymous: 60 req/min per IP
  - Authenticated: 600 req/min per user
  - OTP send: 5 attempts per 10 minutes per mobile
- [ ] CORS allowlist only (no `*`)
- [ ] Request size limit: 1 MB
- [ ] OpenAPI endpoint disabled in production
- [ ] Error responses never leak stack traces in production
- [ ] SQL injection prevented: all queries via SQLAlchemy parameterized
- [ ] SSRF prevented: no user-provided URLs fetched server-side without allowlist
- [ ] IDOR prevented: every query scoped by `community_id` from JWT

## SIP threats

- [ ] **Registration hijack**: TLS mandatory for REGISTER, digest auth enforced, short expiry (300s)
- [ ] **Toll fraud**: `max_duration_sec` enforced by Asterisk, alerts on abnormal call volume
- [ ] **SIP injection**: all user input sanitized before constructing SIP URIs
- [ ] **DDoS/flood**: OpenSIPS `pike` module enabled (30 req / 2s threshold)
- [ ] **fail2ban** watches Asterisk and OpenSIPS logs, bans after 3 failures, 24-hour ban
- [ ] **CallerID spoofing**: edge rejects INVITEs where From header doesn't match registered AOR

## Edge node security

- [ ] Edge exposes only: 5060/5061 (SIP), 8089 (WSS), 3478/5349 (TURN), 30000-40000 UDP (RTP)
- [ ] Edge does NOT expose: PostgreSQL, Redis, Docker socket, AMI
- [ ] Asterisk runs as non-root user
- [ ] AMI credentials kept only in `event_publisher` container
- [ ] Shared secrets injected via env, never baked into images
- [ ] Sync agent auth: shared secret + HMAC
- [ ] Operating system hardened: automatic security updates, minimal packages

## Data protection

- [ ] PII (mobile numbers, SIP URIs) never logged at INFO level
- [ ] Database backups encrypted at rest
- [ ] Database connection uses TLS
- [ ] `pgcrypto` used for any column-level encryption where needed
- [ ] Call recordings (if enabled) encrypted at rest
- [ ] Data retention policy enforced: call_logs 90 days, audit_log 3 years, token_ledger forever
- [ ] User deletion cascades: follow GDPR/台灣個資法 right-to-be-forgotten

## Secrets management

- [ ] No secrets in git history (use `trufflehog` in pre-commit)
- [ ] All secrets via env vars or mounted files
- [ ] `.env` in `.gitignore`
- [ ] Local dev uses `.env.local` (not committed)
- [ ] Production secrets in HashiCorp Vault or AWS Secrets Manager
- [ ] Secret rotation runbook documented and tested

## Dependency hygiene

- [ ] Python dependencies pinned in `poetry.lock`
- [ ] Dart dependencies pinned in `pubspec.lock`
- [ ] Weekly `poetry run safety check` in CI
- [ ] Weekly `dart pub outdated --mode=security`
- [ ] Renovate or Dependabot configured for auto-PRs
- [ ] Docker base images pinned by digest, not tag

## Compliance (台灣個資法 & GDPR-adjacent)

- [ ] `consent_records` table populated on first login
- [ ] Privacy policy versioned; consent re-solicited on version bump
- [ ] `GET /api/v1/privacy/export` returns user's full data dump
- [ ] `POST /api/v1/privacy/delete` anonymizes user (keeps ledger integrity)
- [ ] Call recording requires explicit opt-in per call, consent logged
- [ ] Data processing agreements (DPAs) signed with upstream processors (SMS gateway, payment providers)

## Audit & monitoring

- [ ] Every privileged action written to `audit_log`
- [ ] Every call decision (allow/deny) logged
- [ ] Every token ledger entry includes `idempotency_key` and `external_ref`
- [ ] Alerts on:
  - > 5% auth failure rate over 10 minutes
  - Any negative token balance
  - Sync lag > 5 minutes
  - > 100 fail2ban bans in an hour
  - Any privileged action outside business hours (warning, not block)
- [ ] Logs retained 1 year in a separate cold-storage bucket

## Incident response

- [ ] Runbook: compromised credentials — rotate secrets, invalidate sessions
- [ ] Runbook: data breach — legal notification flow (72 hours for GDPR)
- [ ] Runbook: DDoS — Cloudflare upstream, OpenSIPS pike tuning
- [ ] Runbook: ransomware — backup restore procedure, tested quarterly
- [ ] On-call rotation documented, PagerDuty or equivalent

## Pre-launch audit

- [ ] Penetration test by third party
- [ ] OWASP Top 10 checklist walked
- [ ] SIPVicious scan on OpenSIPS endpoints
- [ ] Load test at 2x expected peak
- [ ] Disaster recovery drill: restore from backup in < 1 hour

## Claude Code enforcement

These checks run in CI and block merges:

```bash
# Python
poetry run bandit -r src/                # security linter
poetry run safety check                  # known CVEs in deps
poetry run detect-secrets scan           # hardcoded secrets

# Dart
dart pub outdated --mode=security

# Secrets scan
trufflehog git file://. --since-commit HEAD~10

# Docker
docker scout cves civio-cloud:latest
docker scout cves civio-edge:latest
```
