#!/bin/bash
# Установка systemd-сервиса PhotoMaker
set -e
cd "$(dirname "$0")/.."
sudo cp systemd/photomaker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable photomaker
sudo systemctl restart photomaker
echo "PhotoMaker service installed and started. Check: systemctl status photomaker"
