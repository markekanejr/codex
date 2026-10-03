FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
RUN pip install --no-cache-dir uv==0.12.19
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev
COPY . .
RUN useradd --uid 10001 --create-home app && chown -R app:app /app /opt/venv
USER app
ENV PATH="/opt/venv/bin:$PATH" DJANGO_SETTINGS_MODULE=config.production
CMD ["sh", "scripts/hosted_web.sh"]
