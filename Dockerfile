# K2b-5b: qmgc, the Qmage (.qmg) encoder behind Content > Boot/shutdown
# animations. GPLv3, vendored with its complete source in third_party/qmgc (see
# ATLAS.md there), built here as a separate program and only copied into the
# image below; ATLAS runs it as a subprocess and never links it.
#
# ⚠️ Same base as the image, so the libc it is built against is the one it runs
# on. libpng is copied beside it rather than installed with apt in the final
# stage, because Debian renamed the package between releases (libpng16-16 vs
# libpng16-16t64) and the base image moves.
FROM python:3.13-slim AS qmgc
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential cmake libpng-dev \
    && rm -rf /var/lib/apt/lists/*
COPY third_party/qmgc /src/qmgc
RUN cmake -S /src/qmgc -B /build -DCMAKE_BUILD_TYPE=Release \
    && cmake --build /build -j"$(nproc)" \
    && mkdir -p /out \
    && cp /build/qmgc /out/qmgc \
    && cp -L "$(ldd /build/qmgc | awk '/libpng/ {print $3}')" /out/

FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first, so a source change does not invalidate the install layer.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# EFF's apkeep, for the APKPure source (W98). Fetched here rather than vendored:
# a 16 MB binary does not belong in git.
#
# ⚠️ The digest is pinned and checked. This is a third-party executable that will
# fetch other executables onto a managed fleet, so "download and run" without
# verifying what arrived would be the weakest link in a chain this project has
# otherwise built carefully. A mismatch fails the build rather than shipping.
#
# Python does the fetching because the base image already has it; adding curl
# would mean an apt layer for one download.
ARG APKEEP_VERSION=1.0.0
ARG APKEEP_SHA256=a23579a3ba366d25a6d69848189b983d65662f4ecf4b9e11e16510811659de4e
RUN python - <<'PY' \
    && chmod +x /usr/local/bin/apkeep
import hashlib, os, urllib.request
version = os.environ.get("APKEEP_VERSION", "1.0.0")
expected = os.environ.get("APKEEP_SHA256", "")
url = (f"https://github.com/EFForg/apkeep/releases/download/{version}"
       f"/apkeep-x86_64-unknown-linux-gnu")
data = urllib.request.urlopen(url, timeout=180).read()
digest = hashlib.sha256(data).hexdigest()
if expected and digest != expected:
    raise SystemExit(f"apkeep digest mismatch: expected {expected}, got {digest}")
with open("/usr/local/bin/apkeep", "wb") as handle:
    handle.write(data)
print(f"apkeep {version} verified: {digest}")
PY

# K2b-5b: the encoder and its libpng, from the stage above. A missing library
# fails the build here rather than the first animation an operator makes.
COPY --from=qmgc /out/qmgc /usr/local/bin/qmgc
COPY --from=qmgc /out/libpng*.so* /usr/local/lib/
RUN ldconfig && ! ldd /usr/local/bin/qmgc | grep -q "not found"

COPY . .

# Run unprivileged. /pki is created here with the right ownership so that a named
# volume mounted over it inherits those permissions — Docker copies them from the
# image when initializing an empty volume.
RUN useradd --create-home --uid 1000 takmdm \
    && mkdir -p /pki \
    && chown -R takmdm:takmdm /pki /app \
    && chmod +x /app/docker/entrypoint.sh

USER takmdm

ENV TAKMDM_PKI_DIR=/pki

EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
# ⚠️ `--no-proxy-headers` is load-bearing, not tidiness. uvicorn otherwise
# rewrites the ASGI `client` from `X-Forwarded-For`, which would let a forged
# header choose the address that `TAKMDM_TRUSTED_PROXIES` is checked against —
# defeating the control with exactly the class of header it exists to defend
# against. Nothing in this application reads a forwarded address.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
