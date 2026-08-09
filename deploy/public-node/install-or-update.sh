#!/bin/sh
set -eu

ROOT=${1:-/opt/mncs-commons}
REPO=${2:-"$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"}

if [ "$(id -u)" -ne 0 ]; then
    echo "run as root for installation; review this script first" >&2
    exit 2
fi
if ! id mncs-commons >/dev/null 2>&1; then
    useradd --system --home-dir /nonexistent --shell /usr/sbin/nologin mncs-commons
fi
install -d -o mncs-commons -g mncs-commons -m 0750 /var/lib/mncs-commons/public
install -d -o root -g mncs-commons -m 0750 /etc/mncs-commons
install -d -o root -g root -m 0755 "$ROOT"
python3 -m venv "$ROOT/venv"
"$ROOT/venv/bin/python" -m pip install --upgrade "$REPO[server]"
install -o root -g root -m 0644 "$REPO/deploy/public-node/mncs-commons.service" /etc/systemd/system/mncs-commons.service
if [ ! -f /etc/mncs-commons/public-node.env ]; then
    install -o root -g mncs-commons -m 0640 "$REPO/deploy/public-node/mncs-commons.env.example" /etc/mncs-commons/public-node.env
fi
if [ ! -f /etc/mncs-commons/visibility.json ]; then
    printf '%s\n' '{"version":1,"withheld":{}}' > /etc/mncs-commons/visibility.json
    chown root:mncs-commons /etc/mncs-commons/visibility.json
    chmod 0640 /etc/mncs-commons/visibility.json
fi
systemctl daemon-reload
echo "installed; review the environment file, initialize the store, then enable the unit"
