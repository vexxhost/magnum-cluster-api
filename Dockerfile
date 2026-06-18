# syntax=docker/dockerfile:1.24

FROM alpine:3.24@sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b AS registry-base
RUN apk add --no-cache docker-registry
ADD registry/config.yml /etc/docker-registry/config.yml

FROM registry-base AS registry-loader
COPY --from=ghcr.io/astral-sh/uv:0.11.22 /uv /uvx /bin/
RUN apk add --no-cache cargo crane gcc linux-headers musl-dev netcat-openbsd py3-pip python3-dev
COPY . /src
WORKDIR /src
RUN <<EOF
  docker-registry serve /etc/docker-registry/config.yml &

  while ! nc -z localhost 5000; do
    sleep 0.1
  done

  uv run --no-project \
    --with click \
    --with diskcache \
    --with platformdirs \
    --with requests \
    --with pyyaml \
    -m magnum_cluster_api.cmd.image_loader \
    --insecure \
    --repository localhost:5000
EOF

FROM registry-base AS registry
COPY --from=registry-loader --link /var/lib/registry /var/lib/registry
EXPOSE 5000
ENTRYPOINT ["docker-registry", "serve", "/etc/docker-registry/config.yml"]
