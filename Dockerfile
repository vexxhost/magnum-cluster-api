# syntax=docker/dockerfile:1.23

FROM alpine:3.22@sha256:55ae5d250caebc548793f321534bc6a8ef1d116f334f18f4ada1b2daad3251b2 AS registry-base
RUN apk add --no-cache docker-registry
ADD registry/config.yml /etc/docker-registry/config.yml

FROM registry-base AS registry-loader
COPY --from=ghcr.io/astral-sh/uv:0.11.3 /uv /uvx /bin/
RUN apk add --no-cache cargo crane gcc linux-headers musl-dev netcat-openbsd py3-pip python3-dev
COPY . /src
WORKDIR /src
RUN <<EOF
  docker-registry serve /etc/docker-registry/config.yml &

  while ! nc -z localhost 5000; do
    sleep 0.1
  done

  uv run magnum-cluster-api-image-loader --insecure --repository localhost:5000
EOF

FROM registry-base AS registry
COPY --from=registry-loader --link /var/lib/registry /var/lib/registry
EXPOSE 5000
ENTRYPOINT ["docker-registry", "serve", "/etc/docker-registry/config.yml"]
