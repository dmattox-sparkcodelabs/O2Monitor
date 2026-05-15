#!/bin/bash
# Backup config.yaml with timestamp

cd "$(dirname "$0")"

mkdir -p backups

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="backups/config-${TIMESTAMP}.yaml"

cp config.yaml "$BACKUP_FILE"
echo "Backed up to: $BACKUP_FILE"

# Keep only last 10 backups
ls -t backups/config-*.yaml 2>/dev/null | tail -n +11 | xargs -r rm
echo "Kept last 10 backups"
