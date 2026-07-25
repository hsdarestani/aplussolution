# A+ Solution Workforce Platform

Deutschsprachige Workforce-, Vertrags- und Portal-Plattform für **A+ Solution GmbH** als Web-App, PWA sowie gemeinsame iOS-/Android-Codebasis.

## Rollen

- **Administration / Disposition:** Schichtplanung, OpenShifts, Zeiterfassung, Urlaub, Personal, Kunden, Verträge, Dokumente, Erinnerungen, Aufträge, Nachrichten, Bewertungen und Audit-Log.
- **Mitarbeiter:** Dienstplan, Schichtübernahme, Schichttausch, Arbeitszeitkonto, Abwesenheiten, Dokumente, Lohnabrechnungen, Nachrichten und Ranking.
- **Kunden:** Personalaufträge, Einsätze, Dokumentenupload, Mitarbeiterbewertungen sowie Prüfung, Download und digitale Signatur von Vertragsunterlagen.

## Architektur

- `backend/`: Django 5, Django REST Framework, PostgreSQL, Redis und Celery
- `frontend/`: Ionic React, Vite PWA und Capacitor
- `Caddyfile`: HTTPS-Reverse-Proxy für `solution.smarbiz.sbs`
- `.github/workflows/deploy.yml`: Validierung und VPS-Deployment über `HOST` und `PASS`
- `.github/workflows/mobile.yml`: Android-AAB und iOS-Xcode-Projekt

## Enthaltene Funktionsbereiche

Dienstplanung über mehrere Kunden/Orte, offene Schichten, Verfügbarkeiten, Schichttausch, GPS-Zeiterfassung, Freigaben, Abwesenheiten, Kundenaufträge, digitale Personalakten, Vertragsgenerator, PDF, Signatur-Hash/IP/Audit, 30-/7-Tage-Erinnerungen, Lohnabrechnungen, Nachrichten, Benachrichtigungen, Rollenrechte, Bewertungen und Ranking.

## Lokaler Start

```bash
cp .env.example .env
docker compose up --build
```

App: `http://localhost:8080` · API: `http://localhost:8000/api/` · Admin: `http://localhost:8000/admin/`

## Produktion

1. DNS-A-Record `solution.smarbiz.sbs` auf `5.75.205.93` setzen.
2. Repository-Secrets `HOST=5.75.205.93` und `PASS=<Root-Passwort>` hinterlegen.
3. Nach dem ersten Deployment die generierten Admin-Daten aus `/root/aplussolution-initial-admin.txt` lesen.
4. OAuth-, Mail-, Firmendaten und AÜG-Angaben in `/opt/aplussolution/.env` ergänzen und `docker compose up -d --build` ausführen.

## Social Login

Benötigt werden Google OAuth Web Client ID/Secret sowie Apple Services ID, Team ID, Key ID und Private Key. Die Apple-ID-Tokens werden gegen Apples öffentliche Schlüssel, Issuer und Audience validiert.

## Mobile Release

Bundle-ID: `de.aplussolution.workforce`. Der Mobile-Workflow erzeugt ein unsigniertes Android AAB bzw. ein iOS-Xcode-Projekt. Store-Signierung, Provisioning Profiles, Distribution-Zertifikate und Store-Zugangsdaten müssen als externe Credentials ergänzt werden.

## Vertragstemplates

Der Generator ist schema- und templatebasiert. Ein Grundmuster mit den Feldern Einsatzbereich, Laufzeit, Neuanstellung, Tätigkeit, Beschäftigungsart, Monatsstunden, Tariflohn und Zulage ist enthalten. Aufhebungsvertrag, Wiederaufnahme und Einzelarbeitnehmerüberlassungsvertrag sind als Typen vorbereitet. Die acht finalen Muster werden nach Lieferung versioniert importiert.

## Rechtlicher Hinweis

Die Software ersetzt keine Rechtsberatung. Vertragsmuster, Tarifdaten, AÜG-Angaben, elektronische Signaturstufe und Aufbewahrungsfristen müssen vor Produktivnutzung fachlich freigegeben werden.
