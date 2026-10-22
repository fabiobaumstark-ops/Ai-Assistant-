#!/usr/bin/env bash
# Installiert Docker Engine + Docker Compose auf einem Raspberry Pi
# (Raspberry Pi OS / Debian / Ubuntu) und richtet es fuer den aktuellen Benutzer ein.
#
# Aufruf auf dem Pi:   bash install-docker.sh
set -euo pipefail

if [[ $EUID -eq 0 ]]; then
  echo "Bitte als normaler Benutzer starten (nicht mit sudo). Das Skript fragt selbst nach sudo." >&2
  exit 1
fi

USER_NAME="$(id -un)"
ARCH="$(dpkg --print-architecture)"

echo "==> System: $(. /etc/os-release && echo "$PRETTY_NAME"), Architektur: $ARCH"
if [[ "$ARCH" == "armhf" ]]; then
  echo "WARNUNG: 32-Bit-System (armhf). Docker unterstuetzt das nur noch eingeschraenkt."
  echo "         Empfehlung: Raspberry Pi OS 64-Bit verwenden (Pi 3/4/5)."
fi

if command -v docker >/dev/null 2>&1; then
  echo "==> Docker ist bereits installiert: $(docker --version)"
else
  echo "==> System aktualisieren"
  sudo apt-get update
  sudo apt-get -y upgrade
  sudo apt-get install -y ca-certificates curl

  echo "==> Docker ueber das offizielle Installationsskript installieren"
  curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
  sudo sh /tmp/get-docker.sh
  rm -f /tmp/get-docker.sh
fi

echo "==> Docker beim Systemstart automatisch starten"
sudo systemctl enable --now docker.service containerd.service

echo "==> Benutzer '$USER_NAME' zur Gruppe 'docker' hinzufuegen (Docker ohne sudo)"
sudo groupadd -f docker
sudo usermod -aG docker "$USER_NAME"

echo "==> Log-Groesse begrenzen (schont die SD-Karte)"
if [[ ! -f /etc/docker/daemon.json ]]; then
  sudo mkdir -p /etc/docker
  sudo tee /etc/docker/daemon.json >/dev/null <<'JSON'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
JSON
  sudo systemctl restart docker
else
  echo "    /etc/docker/daemon.json existiert schon - wird nicht veraendert."
fi

echo "==> Test: hello-world"
sudo docker run --rm hello-world

echo
echo "Fertig!"
echo "  Docker:  $(docker --version)"
echo "  Compose: $(docker compose version 2>/dev/null || echo 'nicht gefunden')"
echo
echo "WICHTIG: Einmal ab- und wieder anmelden (oder 'sudo reboot'),"
echo "damit 'docker' ohne sudo funktioniert."
