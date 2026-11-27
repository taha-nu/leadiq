#!/bin/bash
# Runs every 2 minutes on the EC2 server (cron). Pulling instead of pushing
# means GitHub needs no AWS credentials: CD publishes new images, and the
# server picks them up here.
set -e
cd /opt/leadiq
git pull --quiet                                        # compose + monitoring config
docker compose -f docker-compose.prod.yml pull --quiet  # newest images from GHCR
docker compose -f docker-compose.prod.yml up -d --remove-orphans  # restarts only what changed
docker image prune -f > /dev/null                       # free disk from old images
