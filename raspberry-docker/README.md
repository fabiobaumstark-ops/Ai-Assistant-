# Docker auf dem Raspberry Pi

## Voraussetzungen
- Raspberry Pi 3, 4 oder 5 (empfohlen: 64-Bit-Raspberry-Pi-OS)
- Internetverbindung und SSH-Zugang oder Tastatur/Monitor
- Architektur prüfen: `dpkg --print-architecture` → `arm64` ist ideal, `armhf` = 32 Bit

## Installation
Auf dem Pi im Terminal:

```bash
curl -fsSLO https://raw.githubusercontent.com/fabiobaumstark-ops/Ai-Assistant-/claude/raspberry-docker-setup-5pj3u3/raspberry-docker/install-docker.sh
less install-docker.sh      # Skript vorher anschauen (mit q beenden)
bash install-docker.sh
sudo reboot
```

Das Skript:
1. aktualisiert das System,
2. installiert Docker Engine + Docker Compose (offizielles Skript `get.docker.com`),
3. startet Docker automatisch beim Booten,
4. fügt deinen Benutzer zur Gruppe `docker` hinzu (kein `sudo` mehr nötig),
5. begrenzt die Log-Größe (schont die SD-Karte),
6. testet mit `hello-world`.

## Testen nach dem Neustart
```bash
docker run --rm hello-world
docker compose version
docker compose -f docker-compose.example.yml up -d   # Webserver auf Port 8080
```

## Wichtige Befehle
| Befehl | Bedeutung |
|---|---|
| `docker ps` | laufende Container |
| `docker ps -a` | alle Container |
| `docker images` | heruntergeladene Images |
| `docker logs <name>` | Ausgabe eines Containers |
| `docker stop <name>` | Container stoppen |
| `docker system prune` | Unbenutztes aufräumen |

## Hinweise
- **Sicherheit:** Mitglieder der Gruppe `docker` haben praktisch Root-Rechte.
- Images müssen für ARM gebaut sein (`arm64`/`arm/v7`) – die meisten offiziellen Images sind das.
- Optional grafische Oberfläche: [Portainer](https://docs.portainer.io/).

## Home Assistant installieren
```bash
mkdir -p ~/homeassistant && cd ~/homeassistant
# docker-compose.yml aus raspberry-docker/homeassistant/ hierher kopieren
docker compose up -d
docker logs -f homeassistant     # Start beobachten (Strg+C beendet nur die Anzeige)
```
Danach im Browser `http://<IP-des-Pi>:8123` öffnen und ein Konto anlegen.
Der erste Start kann einige Minuten dauern.

Update:
```bash
cd ~/homeassistant && docker compose pull && docker compose up -d
```
