#!/usr/bin/env bash
set -euo pipefail
work_dir=$(mktemp -d)
trap 'rm -rf "$work_dir"' EXIT
cd "$work_dir"
curl -fsSL --retry 3 -o infisical.tar.gz https://github.com/Infisical/cli/releases/download/v0.45.6/cli_0.45.6_linux_amd64.tar.gz
printf '%s  %s\n' b427391e76113e351fa0509d6493cb400577dec26b28afb462c2c2f9c5a37d4d infisical.tar.gz | sha256sum -c -
tar -xzf infisical.tar.gz infisical
sudo install -m 755 infisical /usr/local/bin/infisical
curl -fsSL --retry 3 -o mihomo.gz https://github.com/MetaCubeX/mihomo/releases/download/v1.19.34/mihomo-linux-amd64-v1-v1.19.34.gz
printf '%s  %s\n' 0c07340a01408d033dda4088ea2a4c1e4d82aeed7b2f84f7c046e93b6ff3290c mihomo.gz | sha256sum -c -
gzip -d mihomo.gz
sudo install -m 755 mihomo /usr/local/bin/mihomo
