FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VERSION=2.4.1 \
    POETRY_VIRTUALENVS_CREATE=false

RUN apt-get update \
    && apt-get install --no-install-recommends -y gcc libc6-dev libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Poetry gets its own venv so installing the lock never swaps out its packages
RUN python -m venv /opt/poetry \
    && /opt/poetry/bin/pip install --no-cache-dir "poetry==${POETRY_VERSION}"

WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN /opt/poetry/bin/poetry install --only main --no-root --no-interaction

COPY . .

# A broken import fails the build, so the old image stays live
RUN python -c "import refresh"

CMD ["python", "refresh.py"]
