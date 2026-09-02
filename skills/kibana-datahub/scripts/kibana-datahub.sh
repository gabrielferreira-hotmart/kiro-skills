#!/usr/bin/env bash
# Wrapper — delega para _internal/
exec "$(dirname "$0")/_internal/kibana-datahub.sh" "$@"
