#!/usr/bin/env bash
set -euo pipefail

action=${1:-status}
case "$action" in
  start|stop|restart|status)
    systemctl --user "$action" mncs-commons.service
    ;;
  logs)
    journalctl --user -u mncs-commons.service --no-pager -n 100
    ;;
  doctor)
    "$HOME/.local/share/mncs-commons/venv/bin/mncs-commons-service" doctor
    ;;
  *)
    echo "usage: $0 {start|stop|restart|status|logs|doctor}" >&2
    exit 2
    ;;
esac
