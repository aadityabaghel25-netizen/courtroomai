#!/bin/bash
# One-command deploy of the CourtroomAI API on a fresh Ubuntu 24.04 EC2 instance:
#   curl -fsSL https://raw.githubusercontent.com/aadityabaghel25-netizen/courtroomai/main/deploy/aws/setup.sh | sudo bash
# Installs Docker, builds the API image from this repo, downloads the data release, and serves it
# over HTTPS at https://<public-ip-with-dashes>.sslip.io (Caddy, free Let's Encrypt certificate).
# Asks for the two API keys once (input hidden) and stores them in /opt/courtroomai/app.env (root only).
# Re-run the same command to update to the latest code.
set -euo pipefail

REPO=https://github.com/aadityabaghel25-netizen/courtroomai.git
DATA_URL=https://github.com/aadityabaghel25-netizen/courtroomai/releases/download/data-v1/courtroomai-data.tgz
APP=/opt/courtroomai
ENV_FILE=$APP/app.env

say() { printf '\n==> %s\n' "$*"; }

say "Installing Docker and git"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq docker.io git curl > /dev/null
systemctl enable --now docker > /dev/null

# Swap gives headroom while building and if memory spikes during a brief.
if ! swapon --show | grep -q /swapfile; then
  say "Adding 4 GB swap"
  fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile > /dev/null && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

say "Fetching code"
mkdir -p $APP
if [ -d $APP/src/.git ]; then git -C $APP/src pull -q; else git clone -q $REPO $APP/src; fi

if [ ! -f $ENV_FILE ]; then
  say "API keys (typing is hidden; paste and press Enter)"
  umask 077
  ask() {
    printf '%s: ' "$1" > /dev/tty
    stty -echo < /dev/tty; IFS= read -r v < /dev/tty; stty echo < /dev/tty; printf '\n' > /dev/tty
    [ -n "$v" ] || { echo "$1 is required" >&2; exit 1; }
    printf '%s=%s\n' "$1" "$v" >> $ENV_FILE
  }
  ask TOKEN_FACTORY_API_KEY
  ask TAVILY_API_KEY
  cat >> $ENV_FILE <<'EOF'
TOKEN_FACTORY_BASE_URL=https://api.tokenfactory.nebius.com/v1
NEMOTRON_NANO_MODEL=nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B
NEMOTRON_SUPER_MODEL=nvidia/nemotron-3-super-120b-a12b
NEMOTRON_ULTRA_MODEL=nvidia/Nemotron-3-Ultra-550b-a55b
EOF
  chmod 600 $ENV_FILE
fi

say "Building the API image (first time: about 5-10 minutes)"
docker build -q -t courtroomai-api $APP/src > /dev/null

IMDS_TOKEN=$(curl -s -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
PUBLIC_IP=$(curl -s -H "X-aws-ec2-metadata-token: $IMDS_TOKEN" http://169.254.169.254/latest/meta-data/public-ipv4)
HOST="${PUBLIC_IP//./-}.sslip.io"

say "Starting the API and HTTPS proxy"
docker rm -f courtroomai-api caddy > /dev/null 2>&1 || true
docker run -d --name courtroomai-api --restart always \
  --env-file $ENV_FILE -e DATA_URL=$DATA_URL \
  -v courtroomai-data:/data -v courtroomai-logs:/app/logs \
  -p 127.0.0.1:8000:8000 courtroomai-api > /dev/null
docker run -d --name caddy --restart always --network host \
  -v caddy-data:/data caddy:2.10 \
  caddy reverse-proxy --from "$HOST" --to 127.0.0.1:8000 > /dev/null

say "Waiting for the API (first start downloads 215 MB of data)"
for i in $(seq 1 60); do
  if curl -fs "https://$HOST/api/health" 2>/dev/null | grep -q '"ok"'; then
    say "Live: https://$HOST   (set VITE_API_URL to this on Vercel)"
    exit 0
  fi
  sleep 10
done
echo "Not healthy after 10 minutes. Logs: sudo docker logs --tail 50 courtroomai-api" >&2
exit 1
