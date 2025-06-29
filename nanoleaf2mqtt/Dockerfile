
ARG BUILD_FROM
FROM $BUILD_FROM as builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project

FROM $BUILD_FROM
COPY --from=builder /app/.venv /app/.venv
COPY nanoleaf2mqtt /app/nanoleaf2mqtt
# Copy data for add-on
COPY run.sh /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]