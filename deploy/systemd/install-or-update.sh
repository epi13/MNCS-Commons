#!/usr/bin/env bash
set -euo pipefail

repository=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
config_dir=${XDG_CONFIG_HOME:-"$HOME/.config"}/mncs-commons
state_dir=${XDG_STATE_HOME:-"$HOME/.local/state"}/mncs-commons
share_dir=${XDG_DATA_HOME:-"$HOME/.local/share"}/mncs-commons
unit_dir=${XDG_CONFIG_HOME:-"$HOME/.config"}/systemd/user

install -d -m 0700 "$config_dir" "$state_dir" "$share_dir" "$unit_dir"
python3 -m venv "$share_dir/venv"
"$share_dir/venv/bin/python" -m pip install --upgrade --force-reinstall "$repository"
install -m 0644 "$repository/deploy/systemd/mncs-commons.service" \
  "$unit_dir/mncs-commons.service"
if [[ ! -e "$config_dir/service.env" ]]; then
  install -m 0600 "$repository/deploy/systemd/mncs-commons.env.example" \
    "$config_dir/service.env"
else
  chmod 0600 "$config_dir/service.env"
fi

systemctl --user daemon-reload
systemctl --user enable --now mncs-commons.service
systemctl --user restart mncs-commons.service
systemctl --user --no-pager status mncs-commons.service
