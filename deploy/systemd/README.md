# Persistent user service

Install or update the independently supervised controller-local Commons service:

```bash
deploy/systemd/install-or-update.sh
```

The helper creates private config/state/data directories, installs an isolated
virtual environment, preserves an existing mode-`0600` environment file, installs
the user unit, reloads systemd, and restarts the service. It is safe to rerun after
updating the checkout.

Routine operations:

```bash
deploy/systemd/service.sh status
deploy/systemd/service.sh doctor
deploy/systemd/service.sh logs
deploy/systemd/service.sh restart
```

The unit exposes no TCP listener. Its consumer socket is
`~/.local/state/mncs-commons/commons.sock`; its stronger operator socket is
`~/.local/state/mncs-commons/commons-operator.sock`. Both live below a private
directory and are mode `0600`. Harness and Control use the consumer socket. Only
explicit operator workflows should receive the operator socket.

The service initializes a missing store once. It does not automatically recover a
damaged or incomplete store. Inspect `status`/`doctor`, preserve the evidence, and
run `mncs-commons-service recover` only after an operator decides recovery is
appropriate.
