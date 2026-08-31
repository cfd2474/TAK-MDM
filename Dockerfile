FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first, so a source change does not invalidate the install layer.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

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
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
