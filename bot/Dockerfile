# syntax=docker/dockerfile:1.7

FROM python:3.12-slim
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin app
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app ./app
USER app
EXPOSE 8081
CMD ["python", "-m", "app.main"]
