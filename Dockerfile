# syntax=docker/dockerfile:1.4

FROM alpine:3.17 AS registry-base
RUN apk add --no-cache docker-registry
ADD registry/config.yml /etc/docker-registry/config.yml

FROM registry-base AS registry-loader
COPY --from=gcr.io/go-containerregistry/crane /ko-app/crane /usr/local/bin/crane
RUN apk add --no-cache cargo gcc linux-headers musl-dev netcat-openbsd py3-pip python3-dev
RUN \
  --mount=type=bind,source=.,target=/src \
  --mount=type=cache,target=/root/.cache \
    pip install /src
RUN <<EOF
  docker-registry serve /etc/docker-registry/config.yml &

  while ! nc -z localhost 5000; do
    sleep 0.1
  done

  magnum-cluster-api-image-loader --insecure --repository localhost:5000
EOF

FROM registry-base AS registry
COPY --from=registry-loader --link /var/lib/registry /var/lib/registry
EXPOSE 5000
ENTRYPOINT ["docker-registry", "serve", "/etc/docker-registry/config.yml"]
