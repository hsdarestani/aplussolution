# Sicherheit

- Keine Zugangsdaten oder `.env`-Dateien committen.
- Produktionsgeheimnisse ausschließlich in GitHub Secrets bzw. `/opt/aplussolution/.env` speichern.
- Root-Passwort nach dem ersten Deployment rotieren und mittelfristig durch einen eingeschränkten Deploy-User mit SSH-Key ersetzen.
- OAuth Redirect URLs exakt auf `solution.smarbiz.sbs` begrenzen.
- Vor Produktivstart Backups, Restore-Test, Monitoring, Rate Limits, Malware-Scan für Uploads und AV-Vertrag/Datenschutz-Folgenprüfung prüfen.
- Sicherheitsmeldungen vertraulich an A+ Solution GmbH senden.
