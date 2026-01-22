FROM python:3.12-slim-bookworm

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
ENV UV_SYSTEM_PYTHON=false
ENV UV_PROJECT_ENVIRONMENT=/app/.venv
# ^^^https://docs.astral.sh/uv/guides/integration/docker/#optimizations
# ^^^https://docs.astral.sh/uv/guides/integration/docker/#compiling-bytecode
# ^^^https://docs.astral.sh/uv/guides/integration/docker/#caching

# ENV UV_NO_CACHE=1
# If you're not mounting the cache, image size can be reduced by using the --no-cache flag or setting UV_NO_CACHE.

# Install dependencies without installing the project itself
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --group docker

# Copy project files
COPY pyproject.toml README.md uv.lock /app/
COPY ./src/ /app/src/
COPY ./tests/mocks /app/tests/mocks

# Sync the project
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --group docker

ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# create the s3 bucket if desired(if false then using real S3 bucket), then start the fastapi app
CMD (\
    if [ "$CREATE_BUCKET_ON_STARTUP" = "true" ]; then \
        uv run -- python -c "import boto3; boto3.client('s3').create_bucket(Bucket='${S3_BUCKET_NAME}')"; \
    fi \
    ) \
    && uv run -- uvicorn files_api.main:create_app --factory --host 0.0.0.0 --port 8000 --reload

# """
# Ref:
# - https://github.com/astral-sh/uv-docker-example/tree/main
# - https://docs.astral.sh/uv/guides/integration/docker/#getting-started
# - https://docs.astral.sh/uv/guides/integration/fastapi/#migrating-an-existing-fastapi-project
# - https://docs.astral.sh/uv/guides/integration/aws-lambda/#using-uv-with-aws-lambda
# - https://docs.astral.sh/uv/concepts/projects/config/#project-environment-path
# """