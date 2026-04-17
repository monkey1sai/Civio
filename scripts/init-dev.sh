#!/usr/bin/env bash
# init-dev.sh — set up a fresh local development environment.
# Generates real random secrets into .env so you never commit fake ones.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  read -p ".env already exists. Overwrite? (y/N) " -n 1 -r
  echo
  [[ ! $REPLY =~ ^[Yy]$ ]] && exit 0
fi

gen_pw() { openssl rand -base64 24 | tr -d '/+=' | cut -c1-24; }
gen_hex() { openssl rand -hex 32; }
gen_jwt() { openssl rand -base64 48 | tr -d '\n'; }

POSTGRES_PW="$(gen_pw)"
REDIS_PW="$(gen_pw)"
RABBIT_PW="$(gen_pw)"
JWT_SECRET="$(gen_jwt)"
OPENSIPS_SECRET="$(gen_hex)"
EDGE_SYNC_SECRET="$(gen_hex)"
AMI_PW="$(gen_pw)"

cp .env.example .env
sed -i.bak \
  -e "s|change_me_min_16_chars|PLACEHOLDER|g" \
  .env
rm .env.bak

python3 - "$POSTGRES_PW" "$REDIS_PW" "$RABBIT_PW" "$JWT_SECRET" \
         "$OPENSIPS_SECRET" "$EDGE_SYNC_SECRET" "$AMI_PW" <<'PY'
import sys, pathlib
pg, rd, rb, jwt, osip, edge, ami = sys.argv[1:8]
p = pathlib.Path(".env")
text = p.read_text()
replacements = {
    "PLACEHOLDER": pg,
    "replace_with_random_48_byte_base64": jwt,
}
for k, v in replacements.items():
    text = text.replace(k, v, 1)
lines = []
for line in text.splitlines():
    if line.startswith("POSTGRES_PASSWORD="):
        line = f"POSTGRES_PASSWORD={pg}"
    elif line.startswith("REDIS_PASSWORD="):
        line = f"REDIS_PASSWORD={rd}"
    elif line.startswith("RABBITMQ_PASSWORD="):
        line = f"RABBITMQ_PASSWORD={rb}"
    elif line.startswith("DATABASE_URL="):
        line = f"DATABASE_URL=postgresql+asyncpg://civio:{pg}@postgres:5432/civio"
    elif line.startswith("REDIS_URL="):
        line = f"REDIS_URL=redis://:{rd}@redis:6379/0"
    elif line.startswith("RABBITMQ_URL="):
        line = f"RABBITMQ_URL=amqp://civio:{rb}@rabbitmq:5672/civio"
    elif line.startswith("CLOUD_RABBITMQ_URL="):
        line = f"CLOUD_RABBITMQ_URL=amqp://civio:{rb}@rabbitmq:5672/civio"
    elif line.startswith("JWT_SECRET="):
        line = f"JWT_SECRET={jwt}"
    elif line.startswith("OPENSIPS_AUTH_SHARED_SECRET="):
        line = f"OPENSIPS_AUTH_SHARED_SECRET={osip}"
    elif line.startswith("EDGE_SYNC_SHARED_SECRET="):
        line = f"EDGE_SYNC_SHARED_SECRET={edge}"
    elif line.startswith("ASTERISK_AMI_SECRET="):
        line = f"ASTERISK_AMI_SECRET={ami}"
    lines.append(line)
p.write_text("\n".join(lines) + "\n")
PY

chmod 600 .env
echo "✓ .env written with random secrets (chmod 600)"

if ! command -v pre-commit >/dev/null 2>&1; then
  echo "→ installing pre-commit"
  pip install --user pre-commit
fi
pre-commit install
pre-commit install --hook-type commit-msg
echo "✓ pre-commit hooks installed"

if [[ ! -f .secrets.baseline ]]; then
  pip install --user detect-secrets >/dev/null 2>&1 || true
  detect-secrets scan > .secrets.baseline
  echo "✓ .secrets.baseline generated"
fi

echo ""
echo "Next steps:"
echo "  make up                  # start infrastructure"
echo "  make cloud-install       # install Python deps"
echo "  make migrate             # apply database migrations"
echo "  make cloud-run           # run the API"
