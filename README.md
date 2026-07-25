# A+ Solution Workforce Platform

Deutschsprachige Workforce-, Vertrags- und Portal-Plattform für **A+ Solution GmbH** als Web-App, PWA sowie gemeinsame iOS-/Android-Codebasis.

## Rollen

- **Administration / Disposition:** Schichtplanung, OpenShifts, Zeiterfassung, Urlaub, Personal, Kunden, Verträge, Dokumente, Erinnerungen, Aufträge, Nachrichten, Bewertungen, Berichte und Audit-Log.
- **Mitarbeiter:** Dienstplan, Schichtübernahme, Verfügbarkeit, Schichttausch, GPS-Arbeitszeitkonto, Abwesenheiten, Vertragsunterschrift, Dokumente, Lohnabrechnungen, Nachrichten und Ranking.
- **Kunden:** Personalaufträge, Einsatzabdeckung, Dokumentenupload, Mitarbeiterbewertungen sowie Prüfung, Download und digitale Signatur von Vertragsunterlagen.

## Architektur

- `backend/`: Django 5, Django REST Framework, PostgreSQL, Redis und Celery
- `frontend/`: Ionic React, Vite PWA und Capacitor
- `Caddyfile`: HTTPS-Reverse-Proxy für `solution.smarbiz.sbs`
- `.github/workflows/deploy.yml`: Validierung und VPS-Deployment über `HOST` und `PASS`
- `.github/workflows/mobile.yml`: unsigniertes Android-AAB bzw. iOS-Xcode-Projekt
- `.github/workflows/mobile-store-release.yml`: credential-geschütztes signiertes Android-AAB bzw. iOS-IPA

## Enthaltene Funktionsbereiche

Dienstplanung über mehrere Kunden und Einsatzorte, OpenShifts, Verfügbarkeiten, Schichttausch mit Freigabe, Wochenkopie, Sammelveröffentlichung, Überschneidungsprüfung, Personalabdeckung, Monatsstundenwarnung, GPS-Geofence-Zeiterfassung, Freigaben, Abwesenheiten, Kundenaufträge, digitale Personal- und Kundenakten, Vertragsgenerator, PDF, Signatur-Hash/IP/Audit, 30-/7-Tage-Erinnerungen an Administration, Mitarbeiter und Kundenkontakte, Lohnabrechnungen, Nachrichten, Benachrichtigungen, Rollenrechte, Bewertungen, Ranking und CSV-Berichte.

## Steuerzentrale

Die rollenabhängige Steuerzentrale zeigt Planungsrisiken, Schichtkonflikte, Zuweisungen trotz Nichtverfügbarkeit, offene Personalbedarfe, Stundenrisiken, geschätzte Lohnkosten, ungeprüfte Zeiten, Vertragsfristen, digitale Akten sowie die Produktionsbereitschaft externer Dienste. Mitarbeiter pflegen dort ihre Verfügbarkeit und Schichttauschanfragen; Kunden sehen die Abdeckung ihrer eigenen Aufträge.

## Dateneingabe und Ersteinrichtung

Die operative Oberfläche enthält Formulare für Mitarbeiter, Kunden, Einsatzorte, Positionen, Aufträge, Schichten, Zeiten, Abwesenheiten, Verträge, Dokumente und Lohnabrechnungen. Mitarbeiter können per Drag & Drop auf Schichten verteilt werden. Für größere Erstimporte stehen CSV-Importe zur Verfügung. Optional kann die Administration über die Startseite einen isolierten Demodatensatz erzeugen.

## Berichte

Die Administration kann CSV-Dateien für Dienstpläne, freigegebene Arbeitszeiten und eine unverbindliche Lohnvorbereitung exportieren. Die Lohnschätzung ersetzt keine steuerliche Lohnabrechnung.

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
4. OAuth-, SMTP-, Firmendaten und AÜG-Angaben in `/opt/aplussolution/.env` ergänzen und `docker compose up -d --build` ausführen.

## Social Login

Google- und Apple-Login sind invitation-only: Die E-Mail-Adresse muss zuerst durch die Administration als Mitarbeiter- oder Kundenkonto angelegt werden. Benötigt werden Google OAuth Web Client ID/Secret sowie Apple Services ID, Team ID, Key ID und Private Key. Apple-ID-Tokens werden gegen Apples öffentliche Schlüssel, Issuer und Audience validiert.

## Mobile Release

Bundle-ID: `de.aplussolution.workforce`.

Für einen signierten Android Store Build werden folgende GitHub-Secrets benötigt:

- `ANDROID_KEYSTORE_BASE64`
- `ANDROID_KEYSTORE_PASSWORD`
- `ANDROID_KEY_ALIAS`
- `ANDROID_KEY_PASSWORD`

Für einen signierten iOS App Store Build werden benötigt:

- `IOS_CERTIFICATE_BASE64`
- `IOS_CERTIFICATE_PASSWORD`
- `IOS_PROVISIONING_PROFILE_BASE64`
- `IOS_TEAM_ID`
- optional `IOS_KEYCHAIN_PASSWORD`

Der Workflow `Signed mobile store release` bricht ohne diese vertraulichen externen Zugangsdaten bewusst ab und veröffentlicht nach erfolgreicher Signierung ein AAB bzw. IPA als geschütztes Workflow-Artefakt.

## Vertragstemplates

Der Generator ist schema- und templatebasiert. Felder für `Arbeitsvertrag`, `1b Einsatzbereich`, Vertragsbeginn/-ende, `Neuanstellung`, `Tätigkeit`, Beschäftigungsart, Monatsstunden, Tariflohn und übertarifliche Zulage sind enthalten. Aufhebungsvertrag, Wiederaufnahme und Einzelarbeitnehmerüberlassungsvertrag sind als Typen vorbereitet. Vorlagen werden versioniert per JSON importiert; ein Formatbeispiel liegt unter `docs/contract-template-import.example.json`.

Die acht finalen, rechtlich freigegebenen Muster können erst importiert werden, sobald die Dateien geliefert wurden. Die Steuerzentrale zeigt bis dahin sichtbar an, dass der finale Vertragssatz unvollständig ist.

## Externe Aktivierungspunkte

Code und Bedienoberfläche sind vorbereitet; folgende Inhalte können nicht aus dem Quellcode erfunden werden und müssen als echte Unternehmensdaten geliefert werden:

- Google- und Apple-OAuth-Credentials
- Android-Keystore sowie Apple Distribution Certificate und Provisioning Profile
- die acht finalen Vertragsmuster
- rechtlich freigegebene Firmendaten, AÜG-Angaben, Datenschutztexte, Signaturstufe und Aufbewahrungsfristen
- SMTP-Zugang für den produktiven E-Mail-Versand

## Rechtlicher Hinweis

Die Software ersetzt keine Rechts- oder Steuerberatung. Vertragsmuster, Tarifdaten, AÜG-Angaben, elektronische Signaturstufe, Datenschutztexte und Aufbewahrungsfristen müssen vor Produktivnutzung fachlich freigegeben werden.
