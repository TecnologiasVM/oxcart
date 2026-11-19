# The backend in hosted mode (the question path only). Build from the repository root:
#
#   docker build -f backend/Dockerfile -t oxcart-backend .
#   docker run --rm -p 8000:8000 --env-file <your settings> oxcart-backend
#
# The image holds code and pinned packages. It holds no key, no address and no data: every
# setting comes from the environment of the host that runs it (see backend/README.md).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OXCART_PUBLIC=1

WORKDIR /srv
COPY backend/requirements.txt /srv/requirements.txt
RUN pip install --no-cache-dir -r /srv/requirements.txt

# The shared modules (settings, the catalogue lookup), installed as the `oxcart` package.
# --no-deps: the pinned list above is the whole dependency list. -e: the package is used
# from /srv/oxcart, so the paths it derives from its own place are those of a checkout.
COPY pyproject.toml /srv/pyproject.toml
COPY oxcart /srv/oxcart
RUN pip install --no-cache-dir --no-deps -e /srv

# The API.
COPY backend/app /srv/backend/app

RUN useradd --system --uid 10001 --no-create-home oxcart
USER oxcart
WORKDIR /srv/backend

# The host says which port to listen on (PORT); 8000 otherwise. No access log: it would
# record the caller's address.
EXPOSE 8000
CMD ["sh", "-c", "exec python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --no-access-log"]
