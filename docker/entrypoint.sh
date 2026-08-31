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
fi

exec "$@"
