# Self-hosted CI on sin

This repository uses a dedicated GitHub Actions runner on the existing sin server.
The repository Actions **variable** `CI_RUNS_ON` is:

```json
["self-hosted", "linux", "x64", "customer-churn"]
```

Set it under Settings → Secrets and variables → Actions → Variables → Repository
variables. The workflow uses the same labels as its fallback. It is not an
environment variable or Actions secret.

The runner is named `sin`, is installed in `/opt/actions-runner-customer-churn`, and
runs as the dedicated `churn-runner` account. Its systemd service is
`actions.runner.ali-aljufairi-Customer-Churn-MLOPS-Pipeline.sin.service` and starts at
boot. The initial runner version is `2.338.0`; GitHub manages runner updates.

The workflow uses Python 3.12 with a new virtual environment in the runner's
temporary directory. Development requirements include the pinned runtime
requirements so model training and API tests use the application's dependencies.
Fork pull requests do not execute on this persistent runner.

## Container builds

Docker runs rootless as `churn-runner`, with its own storage in
`/home/churn-runner/.local/share/docker` and socket at
`unix:///run/user/1003/docker.sock`. The runner service supplies `DOCKER_HOST` and
adds `/opt/customer-churn-ci/bin` to its path. It does not use Kubernetes's
containerd or a system-wide privileged Docker daemon.

The user-level `docker.service` is enabled at boot through systemd lingering.
Docker `29.9.1` uses Ubuntu's packaged RootlessKit, slirp4netns, uidmap, and
AppArmor profile. Its documented compatibility setting is:

```ini
Environment=DOCKERD_ROOTLESS_ROOTLESSKIT_DETACH_NETNS=false
```

It is stored in
`/home/churn-runner/.config/systemd/user/docker.service.d/ci.conf`. No custom
AppArmor profile or global user-namespace policy change is required. Both the
runner and rootless Docker service have a 2 GiB memory limit and a two-CPU quota.
The runner service also sets `NoNewPrivileges=yes`.

Docker's static binaries live in `/opt/customer-churn-ci/bin`; update them
explicitly from Docker's official releases. The initial official Buildx plugin
is `v0.38.0` in `/usr/local/lib/docker/cli-plugins/docker-buildx`. Release archives
are retained in `/opt/customer-churn-ci/downloads`. Runner and Buildx downloads
were checked against GitHub's release-asset SHA-256 digests.

## Maintenance on sin

```sh
systemctl status actions.runner.ali-aljufairi-Customer-Churn-MLOPS-Pipeline.sin.service
runuser -u churn-runner -- env XDG_RUNTIME_DIR=/run/user/1003 \
  DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1003/bus \
  systemctl --user status docker.service
runuser -u churn-runner -- env DOCKER_HOST=unix:///run/user/1003/docker.sock \
  /opt/customer-churn-ci/bin/docker info
```

The workflow trains the model, runs pytest and Ruff, and builds the production
image. Build images and cache are private to this runner account. Retain useful
cache between jobs, and remove unused images/cache during maintenance if disk
usage grows. Do not remove another project's runner, Kubernetes images, or data.
