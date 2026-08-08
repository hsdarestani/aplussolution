# Veröffentlichung iOS und Android

- App-Name: `A+ Solution`
- Bundle-/Package-ID: `de.aplussolution.workforce`
- Produktions-URL: `https://solution.smarbiz.sbs`
- API: `https://solution.smarbiz.sbs/api`
- Datenschutz: `https://solution.smarbiz.sbs/datenschutz`
- Kontolöschung/Datenlöschung: `https://solution.smarbiz.sbs/konto-loeschen`
- Support: `https://solution.smarbiz.sbs/support`
- Impressum: `https://solution.smarbiz.sbs/impressum`

## Produkt- und Zugangsmodell

A+ Solution ist eine **interne Unternehmens-App** für Mitarbeiter, Disposition und Management der A+ Solution GmbH.

- Keine öffentliche Selbstregistrierung.
- Konten werden von der Administration angelegt oder per persönlicher Einladung aktiviert.
- Google/Apple Login, wenn aktiviert, authentifiziert ausschließlich bereits freigeschaltete Konten und erzeugt keine neuen A+ Solution Konten.
- Keine Werbung und kein Advertising Tracking.
- Keine Hintergrundortung.
- Präziser Standort nur beim aktiven Ein-/Ausstempeln zur Prüfung eines vorgesehenen Einsatzortes.

## Empfohlene Distribution

- **Android:** Managed Google Play Private App, beschränkt auf die A+ Solution Organisation.
- **iOS:** Private Custom App über Apple Business Manager.
- Falls Apple Business Manager nicht für alle Geräte geeignet ist, kann nach App Review alternativ eine Unlisted-App-Verteilung beantragt werden.

## Vor der Einreichung

1. Die rechtlichen URLs oben müssen öffentlich und ohne Login erreichbar sein.
2. Einen dedizierten Store-Review-Account mit ausschließlich synthetischen Beispieldaten anlegen.
3. Store-Icon 1024×1024 und Screenshots ohne echte Mitarbeiter-, Lohn-, Bank-, Steuer-, Gesundheits- oder vertrauliche Kundendaten bereitstellen.
4. Android AAB mit dem dauerhaften Upload-Key und iOS IPA mit Distribution Certificate/Provisioning Profile signieren.
5. Wenn Google Login im Build sichtbar bleibt, Google OAuth produktiv konfigurieren. Wenn Apple Login sichtbar bleibt, App ID/Service ID und „Mit Apple anmelden“ produktiv konfigurieren.
6. Nach `cap sync` immer `node scripts/prepare-native.mjs android` bzw. `node scripts/prepare-native.mjs ios` ausführen. Der Store-Workflow macht dies automatisch.
7. Keine Background-Location-, Camera-, Broad-Storage- oder Tracking-Permissions ergänzen, solange die App diese Funktionen nicht tatsächlich nutzt.
8. Die Store-Antworten und Privacy Labels aus `docs/STORE_SUBMISSION_2026.md` übernehmen und vor jedem Release gegen den echten Build prüfen.

## Review-Hinweis

Der Reviewer muss ausdrücklich erfahren, dass es keine Registrierung gibt. Zugangsdaten gehören nur in App Store Connect / Play Console bzw. in den Publisher-Release-Datensatz – niemals in GitHub.

## Kurzbeschreibung

`Interne Dienstplanung, Zeiterfassung und Dokumente für A+ Solution.`

Die vollständige Store-Beschreibung, Privacy/Data-Safety-Zuordnung und Review-Notes stehen in `docs/STORE_SUBMISSION_2026.md`.
