# syntax=docker/dockerfile:1.4

FROM alpine:3.21 AS registry-base
RUN apk add --no-cache docker-registry
ADD registry/config.yml /etc/docker-registry/config.yml

FROM registry-base AS registry-loader
RUN apk add --no-cache cargo uv crane gcc linux-headers musl-dev netcat-openbsd py3-pip python3-dev
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
