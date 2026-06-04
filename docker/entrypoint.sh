#!/bin/sh
set -e

# Named Docker volumes are created as root:root on first mount, making them
# unwritable by appuser (UID=10001). This entrypoint runs as root and corrects
# ownership before dropping privileges — covers both first-deploy and any
# docker-compose restart / docker restart scenario where the compose-level
# backend-volume-init init-container does not re-run.
mkdir -p /var/run/ultra /var/log/ultra-autotrade
chown -R 10001:10001 /var/run/ultra /var/log/ultra-autotrade

exec gosu appuser "$@"
