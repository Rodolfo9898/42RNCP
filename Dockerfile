FROM python:3.14-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git openssh-client socat ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Same uid as the sandbox so both containers can read/write the shared workspace volume.
RUN useradd --create-home --uid 1000 verdict \
    && mkdir /workspace /projects && chown verdict:verdict /workspace /projects

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY --chmod=755 entrypoint.sh /entrypoint.sh

# No USER here: the entrypoint starts as root, relays the ssh-agent, then drops to uid 1000.
ENTRYPOINT ["/entrypoint.sh"]
ENV WORKSPACE=/workspace \
    SANDBOX_URL=http://sandbox:8001 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000
CMD ["uvicorn", "verdict.main:app", "--host", "0.0.0.0", "--port", "8000"]
