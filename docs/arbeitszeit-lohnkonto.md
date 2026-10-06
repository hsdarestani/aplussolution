# Arbeitszeit und Lohnkonto: Abgleich und Betrieb

## Drei miteinander verbundene Datenquellen

1. **Dienstplan (Plan):** Zuordnung von Mitarbeiter, Kunde, Einsatzort und geplanter Schicht. Die Planzeiten sind eine Vergleichsgröße, kein Nachweis der tatsächlich geleisteten Stunden.
2. **Zeiterfassung (Ist):** Geschlossene, freigegebene A+ Zeiteinträge sowie historische WIW Zeiteinträge mit WIW Identität. Maßgeblich sind tatsächlicher Beginn, tatsächliches Ende und unbezahlte Pause. Nicht freigegebene native Einträge bleiben bis zur Freigabe außerhalb der abrechnungsrelevanten Iststunden.
3. **Lexware beziehungsweise Bankexport (Zahlung):** Einmalig hochgeladene CSV oder ZIP Dateien mit Bankumsätzen. Die tatsächlich überwiesenen Beträge und Zahlungsdaten werden dem Mitarbeiter und dem zuvor ausgewählten Abrechnungsmonat zugeordnet.

Aus dem Dienstplan wird **niemals** die tatsächlich gearbeitete Stundenzahl abgeleitet. Aus einem überwiesenen Eurobetrag wird **niemals automatisch** auf die bezahlte Stundenzahl geschlossen.

## Verwendung im Adminbereich

1. Im Modul Arbeitszeitkonto die arbeitsvertraglichen Sollstunden, den Stundenlohn und gegebenenfalls die Zuschlagssätze für Nacht, Samstag und Sonntag kontrollieren.
2. **Gesamthistorie neu berechnen** für die vorhandenen Arbeitszeiten ausführen. Die Monatskonten werden je Mitarbeiter ab dem ersten erfassten Arbeitsmonat aufgebaut. Historische, abgeschlossene Stammdatenwerte bestehender Monatskonten werden beim erneuten Berechnen beibehalten.
3. Die Monatsübersicht und die Tagesdetails kontrollieren: Kunde, Einsatzort, Planbeginn und Planende, tatsächlicher Beginn und tatsächliches Ende, Pause, Nettostunden und Zuschlagsstunden.
4. Bei Bedarf **Lexware Import** wählen, einen Abrechnungsmonat ausdrücklich angeben und den CSV oder ZIP Bankexport hochladen. Nicht zugeordnete Umsätze werden nur zur Prüfung angezeigt. Bei gleichen Namen wird eine mehrdeutige Zuordnung nicht geraten. Bereits importierte gleiche Transaktionen werden anhand ihrer gespeicherten Identität nicht doppelt übernommen.
5. Die tatsächlich **bezahlten Stunden gesamt** pro Mitarbeiter und Monat anhand der Abrechnung bestätigen beziehungsweise korrigieren. Dies ist eine von der Banküberweisung getrennte Angabe. Anschließend den kumulierten Saldo prüfen.
6. Monatsübersichten als Excel oder CSV sowie den individuellen Tagesnachweis im PDF exportieren.

## Rechenregeln

- **Iststunden:** Summe der tatsächlich freigegebenen Arbeitsminuten abzüglich der dokumentierten unbezahlten Pausen.
- **Sollstunden:** Gesonderte vertragliche Vergleichsgröße.
- **Monatssaldo:** Iststunden plus manuelle Stundenkorrektur minus tatsächlich bezahlte Gesamtstunden.
- **Kumulativer Saldo:** Voriger Saldo plus Monatssaldo. Ein positiver Saldo ist ein Stundenguthaben, ein negativer Saldo ein Minus.
- **Beispiel:** 50 Iststunden und 38 bezahlte Stunden ergeben bei einem Startsaldo von 0 genau +12 Stunden.
- **Zuschläge:** Nachtstunden im Zeitraum 23:00 bis 06:00, Samstag und Sonntag werden aus den tatsächlichen Uhrzeiten ermittelt. Die Satzhöhe ist je Mitarbeiter konfigurierbar. Wenn nur die gesamte Pausendauer bekannt ist, wird sie proportional auf die Zuschlagskategorien verteilt. Überschneidende Kategorien werden separat ausgewiesen.
- **Bruttovorschau:** Iststunden mal historisch gespeichertem Stundensatz plus gegebenenfalls Zuschläge. Der tatsächliche Bankabfluss aus Lexware bleibt eine separat ausgewiesene Zahl.

## Prüfpflichtige Ausgangsdaten und Grenzen

Bei bereits bestehenden älteren Zeitkonten und bei frisch aus Sollstunden initialisierten Monatskonten kann das Feld bezahlte Gesamtstunden zunächst aus dem bisherigen Sollwert stammen. **Dieser Ausgangswert ist kein Zahlungsnachweis.** Er muss anhand von Lohnabrechnung oder Zahlungsnachweis überprüft und gegebenenfalls korrigiert werden, bevor der Stundensaldo als tatsächlich abgerechnet betrachtet werden kann.

Die Lexware Bankdatei bestätigt den Bankabfluss, aber nicht selbst die vergüteten Arbeitsstunden oder die lohnsteuerliche Behandlung von Zuschlägen. Die automatische Erkennung von Zahlungsempfängern benötigt einen erkennbaren Namen; unklare und mehrdeutige Zeilen müssen manuell abgeglichen werden.

Für Minijobs wird 2026 bei einem Grundbrutto über 603 EUR gewarnt. Die Warnung ist ein Hinweis, keine automatische rechtliche Neubewertung. Zusätzliche Sonderfälle und die Behandlung von Zuschlägen sind lohnabrechnerisch zu prüfen.

Die Bedienoberfläche und das Datenmodell ergänzen das bestehende Adminsystem; eine Änderung des Mitarbeiter App Designs ist nicht Teil dieses Moduls.
