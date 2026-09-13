#!/bin/sh
# Wait for Postgres, apply migrations, then hand off to the given command.
set -e

if [ -n "${TAKMDM_DATABASE_URL}" ] && [ "${TAKMDM_SKIP_DB_WAIT}" != "1" ]; then
  echo "waiting for database..."
  python - <<'PY'
import os, sys, time
import sqlalchemy

url = os.environ["TAKMDM_DATABASE_URL"]
deadline = time.monotonic() + 60
engine = sqlalchemy.create_engine(url, pool_pre_ping=True)

while True:
    try:
        with engine.connect() as connection:
            connection.execute(sqlalchemy.text("SELECT 1"))
        break
    except Exception as exc:
        if time.monotonic() > deadline:
            print(f"database unreachable after 60s: {exc}", file=sys.stderr)
            sys.exit(1)
        time.sleep(1)
print("database ready")
PY

  if [ "${TAKMDM_SKIP_MIGRATIONS}" != "1" ]; then
    echo "applying migrations..."
    alembic upgrade head
  fi

  # Load the applications shipped in dist/ — the agent above all, because the
  # provisioning QR carries its signing checksum and a deployment with an empty
  # library cannot enrol anything at all.
  #
  # After migrations, because it writes rows. Idempotent: every build after the
  # first reports "already uploaded" and nothing changes.
  #
  # `|| true` on purpose. This is the startup path, and refusing to boot over a
  # bundled APK that could not be read would be far worse than starting with an
  # empty library and saying so in the log.
  if [ "${TAKMDM_SKIP_SEED}" != "1" ]; then
    python -m app.cli seed-packages "${TAKMDM_SEED_DIR:-/seed}" || true
  fi
fi

exec "$@"
