# MNCS Commons Experimental Public Node deployment

This profile targets Debian/Ubuntu, Python 3.11+, systemd, and Caddy. The
Python service binds to loopback; Caddy owns Internet-facing HTTPS.

```text
/opt/mncs-commons/                 code and virtual environment
/var/lib/mncs-commons/public/      replaceable public store
/etc/mncs-commons/public-node.env configuration
/etc/mncs-commons/visibility.json  operator-only serving overlay
```

The service must not have access to MNCS repositories, GitHub tokens, Forge or
Fabric credentials, SSH agent sockets, cloud credentials, or model-provider keys.

Review `install-or-update.sh` and run it as an operator. Then initialize and
seed exactly once when desired:

```bash
sudo -u mncs-commons /opt/mncs-commons/venv/bin/mncs-commons store init /var/lib/mncs-commons/public
sudo -u mncs-commons /opt/mncs-commons/venv/bin/mncs-commons store seed-public /var/lib/mncs-commons/public
```

Set `MNCS_COMMONS_BASE_URL=https://<hostname>` and
`MNCS_COMMONS_WRITE_MODE=anonymous-public`. To stop ingestion, change only
`MNCS_COMMONS_WRITE_MODE=read-only` and restart the unit; reads remain available.
Run Caddy with `Caddyfile.example`, then run:

```bash
deploy/public-node/verify-deployment.sh https://<hostname>
```

Expose TCP 80/443 for Caddy and keep the application port closed to the network.
This profile reduces accidental access and resource exposure; it is not a formal
sandbox or protected custody claim. Rate and capacity policies are single-node
controls, not federation-wide guarantees.
