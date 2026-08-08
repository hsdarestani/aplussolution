import React from 'react';
import './store-compliance.css';

type LegalPage = 'privacy' | 'deletion' | 'imprint' | 'support';

const COMPANY = {
  name: 'A+ Solution GmbH',
  managingDirector: 'Ashkan Asadian G.',
  address: 'Carl-Sonnenschein Straße 57, 65936 Frankfurt am Main, Deutschland',
  phone: '+49 69 21000418',
  mobile: '+49 172 7779721',
  email: 'info@aplus-solution.de',
  website: 'https://aplus-solution.de',
  register: 'HRB 128570',
  vat: 'DE296290089',
};

function Shell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <main className="store-legal-shell">
      <header className="store-legal-header">
        <a className="store-legal-brand" href="/" aria-label="A+ Solution App öffnen">
          <span>A+</span>
          <strong>Solution</strong>
        </a>
        <nav aria-label="Rechtliche Informationen">
          <a href="/datenschutz">Datenschutz</a>
          <a href="/konto-loeschen">Kontolöschung</a>
          <a href="/impressum">Impressum</a>
          <a href="/support">Support</a>
        </nav>
      </header>
      <article className="store-legal-card">
        <p className="store-legal-kicker">A+ SOLUTION · INTERNE WORKFORCE-APP</p>
        <h1>{title}</h1>
        {children}
        <p className="store-legal-updated">Stand: 8. August 2026</p>
      </article>
    </main>
  );
}

function Privacy() {
  return (
    <Shell title="Datenschutzinformation für die A+ Solution App">
      <p>
        Diese Datenschutzinformation beschreibt die Verarbeitung personenbezogener Daten in der internen
        mobilen und webbasierten Anwendung „A+ Solution“ (Bundle-/Package-ID
        <code> de.aplussolution.workforce</code>). Die App dient ausschließlich betrieblichen Zwecken der
        A+ Solution GmbH, insbesondere für Mitarbeiter, Disposition und Management. Es gibt keine öffentliche
        Selbstregistrierung. Benutzerkonten werden ausschließlich durch die Administration angelegt oder per
        persönlicher Einladung aktiviert.
      </p>

      <h2>1. Verantwortlicher</h2>
      <p>
        <strong>{COMPANY.name}</strong><br />
        {COMPANY.address}<br />
        Geschäftsführer: {COMPANY.managingDirector}<br />
        E-Mail: <a href={`mailto:${COMPANY.email}`}>{COMPANY.email}</a><br />
        Telefon: <a href="tel:+496921000418">{COMPANY.phone}</a>
      </p>

      <h2>2. Welche Daten verarbeitet werden</h2>
      <p>Je nach Rolle, Arbeitsverhältnis und genutzter Funktion können insbesondere folgende Daten verarbeitet werden:</p>
      <ul>
        <li>Stamm- und Kontaktdaten wie Name, geschäftliche bzw. hinterlegte E-Mail-Adresse, Telefonnummer, Anschrift und Personalnummer.</li>
        <li>Beschäftigungs- und Abrechnungsdaten wie Beschäftigungsart, Arbeitszeit, Stundenkonten, Vergütungsangaben, Lohnunterlagen sowie – soweit für die Personalverwaltung erforderlich – Steuer-, Sozialversicherungs-, Krankenversicherungs- und Bankdaten.</li>
        <li>Einsatz- und Planungsdaten wie Schichten, Einsatzorte, Verfügbarkeiten, Abwesenheiten und organisatorische Hinweise.</li>
        <li>Zeiterfassungsdaten einschließlich Ein- und Ausstempelzeit sowie – nur beim aktiven Ein- oder Ausstempeln – des aktuellen präzisen Standorts zur Prüfung des vorgesehenen Einsatzortes.</li>
        <li>Vertrags- und Dokumentendaten, hochgeladene Dateien, Lohnabrechnungen, Signaturen und Nachweise zur elektronischen Unterzeichnung.</li>
        <li>Kommunikationsdaten aus internen Nachrichten und Benachrichtigungen.</li>
        <li>Authentifizierungs- und Sicherheitsdaten wie Benutzer-ID, Sitzungs-/Tokeninformationen, Zeitstempel sowie sicherheitsrelevante Protokolldaten. Bei elektronischen Signaturen kann die IP-Adresse als Nachweis gespeichert werden.</li>
      </ul>

      <h2>3. Standortdaten</h2>
      <p>
        Die App verwendet <strong>keine Hintergrundortung</strong>. Ein Standortzugriff wird nur ausgelöst, wenn ein
        Mitarbeiter aktiv ein- oder ausstempelt und für den zugeordneten Einsatzort eine Standortprüfung vorgesehen
        ist. Dabei werden Breiten- und Längengrad an das A+ Solution-System übertragen und zusammen mit dem
        Zeiteintrag gespeichert. Die Standortberechtigung des Betriebssystems kann jederzeit in den Geräteeinstellungen
        geändert werden. Ist eine Standortprüfung für den konkreten Einsatz erforderlich, kann ohne Standortfreigabe
        keine standortgebundene Zeiterfassung durchgeführt werden.
      </p>

      <h2>4. Abwesenheiten und besondere Kategorien personenbezogener Daten</h2>
      <p>
        Für Abwesenheitsanträge ist keine medizinische Diagnose erforderlich. Nutzer sollen in optionalen Freitextfeldern
        keine Diagnosen oder unnötigen Gesundheitsdetails eintragen. Soweit besondere Kategorien personenbezogener Daten
        im Beschäftigungskontext ausnahmsweise zur Erfüllung arbeits-, sozialversicherungs- oder sozialschutzrechtlicher
        Pflichten erforderlich sind, erfolgt die Verarbeitung nur im hierfür erforderlichen Umfang.
      </p>

      <h2>5. Zwecke und Rechtsgrundlagen</h2>
      <p>
        Die Verarbeitung erfolgt zur Durchführung und Organisation des Beschäftigungsverhältnisses, zur Einsatz- und
        Arbeitszeitplanung, Zeiterfassung, Vertrags- und Dokumentenverwaltung, Lohn- und Personaladministration,
        internen Kommunikation sowie zur Erfüllung gesetzlicher Arbeitgeberpflichten. Maßgeblich sind insbesondere
        § 26 BDSG sowie – je nach Verarbeitung – Art. 6 Abs. 1 lit. b und c DSGVO. Für notwendige Sicherheits-,
        Missbrauchs- und Nachweiszwecke können berechtigte Interessen nach Art. 6 Abs. 1 lit. f DSGVO einschlägig sein.
        Soweit im Beschäftigungskontext besondere Kategorien personenbezogener Daten erforderlich verarbeitet werden,
        erfolgt dies insbesondere nach Art. 9 Abs. 2 lit. b DSGVO in Verbindung mit § 26 Abs. 3 BDSG.
      </p>

      <h2>6. Anmeldung und externe Identitätsanbieter</h2>
      <p>
        Die reguläre Anmeldung erfolgt mit einem von A+ Solution bereitgestellten Konto. Optional kann ein bereits
        vorhandenes, von A+ Solution freigeschaltetes Konto über Google oder „Mit Apple anmelden“ authentifiziert werden.
        Die Nutzung dieser Anmeldewege erstellt kein neues A+ Solution-Konto. Bei Nutzung eines solchen Anbieters werden
        die für die Anmeldung erforderlichen Identitätsdaten (insbesondere E-Mail-Adresse bzw. Anbieter-ID und
        Authentifizierungsinformationen) mit dem jeweiligen Anbieter ausgetauscht.
      </p>

      <h2>7. Empfänger und Auftragsverarbeiter</h2>
      <p>
        Zugriff innerhalb der A+ Solution GmbH erhalten nur Personen, die ihn für ihre jeweilige Rolle und Aufgabe
        benötigen. Technische Dienstleister können Daten ausschließlich im erforderlichen Umfang als Auftragsverarbeiter
        oder sonstige datenschutzrechtlich zulässige Empfänger verarbeiten. Dazu können Hosting-/IT-Dienstleister,
        E-Mail-Dienstleister sowie – bei freiwilliger Nutzung – Google und Apple für die Authentifizierung gehören.
      </p>
      <p>
        Eine optionale, ausschließlich für Managementfunktionen vorgesehene Auftragsanalyse kann – sofern diese Funktion
        administrativ aktiviert ist – von autorisierten Nutzern ausgelöst werden. Dabei wird der von ihnen ausdrücklich
        übermittelte Auftragstext zur strukturierten Analyse an OpenAI übertragen. Lohn-, Personalakten-, Krankheits- oder
        sonstige unnötige Beschäftigtendaten dürfen dafür nicht eingegeben werden. Bestehende betriebliche Systeme können
        außerdem vorübergehend für Migration, Abgleich oder gesetzlich erforderliche Nachweise angebunden sein.
      </p>

      <h2>8. Drittlandübermittlungen</h2>
      <p>
        Soweit bei optionalen Diensten Anbieter außerhalb des Europäischen Wirtschaftsraums beteiligt sind, erfolgt eine
        Übermittlung nur auf Grundlage der jeweils anwendbaren datenschutzrechtlichen Voraussetzungen und geeigneter
        Garantien. Die Kern-Personal- und Workforce-Daten werden nicht zu Werbezwecken verkauft oder an Werbenetzwerke
        übermittelt.
      </p>

      <h2>9. Speicherdauer und Löschung</h2>
      <p>
        Daten werden nur so lange gespeichert, wie sie für den jeweiligen betrieblichen Zweck, das Beschäftigungsverhältnis,
        die Geltendmachung oder Abwehr von Ansprüchen oder gesetzliche Aufbewahrungs- und Nachweispflichten benötigt werden.
        Nach Wegfall des Zwecks werden Daten gelöscht oder anonymisiert, soweit keine gesetzlichen Pflichten oder
        berechtigten Aufbewahrungsgründe entgegenstehen. Insbesondere Personal-, Vertrags-, Arbeitszeit-, Steuer- und
        Abrechnungsunterlagen können gesetzlichen Aufbewahrungsfristen unterliegen.
      </p>

      <h2>10. Kontolöschung und Ende des Zugangs</h2>
      <p>
        Die App bietet keine öffentliche Kontoerstellung. Bei Ende der Berechtigung wird der Portalzugang durch die
        Administration deaktiviert. Zusätzlich kann jeder angemeldete Nutzer unter „Mein Profil“ eine Löschanfrage
        auslösen. Eine Anfrage ist auch ohne App über <a href="/konto-loeschen">/konto-loeschen</a> beziehungsweise per
        E-Mail an <a href={`mailto:${COMPANY.email}`}>{COMPANY.email}</a> möglich. Löschbare Kontodaten werden gelöscht
        oder anonymisiert; gesetzlich aufzubewahrende Beschäftigungs-, Vertrags- oder Abrechnungsunterlagen bleiben nur
        für die jeweilige Aufbewahrungsdauer erhalten.
      </p>

      <h2>11. Sicherheit</h2>
      <p>
        Die Kommunikation mit dem Produktivsystem erfolgt verschlüsselt über HTTPS. Die Anwendung verwendet
        rollenbasierte Zugriffsrechte und authentifizierte API-Zugriffe. Administrative und sensible Funktionen sind auf
        berechtigte Rollen beschränkt. Es werden keine Werbe-SDKs eingesetzt und keine Standortdaten für Werbung oder
        Profilbildung verwendet.
      </p>

      <h2>12. Rechte betroffener Personen</h2>
      <p>
        Betroffene Personen haben im Rahmen der gesetzlichen Voraussetzungen insbesondere Rechte auf Auskunft,
        Berichtigung, Löschung, Einschränkung der Verarbeitung, Datenübertragbarkeit und Widerspruch. Anfragen können an
        <a href={`mailto:${COMPANY.email}`}> {COMPANY.email}</a> gerichtet werden. Außerdem besteht das Recht, sich bei
        einer Datenschutzaufsichtsbehörde zu beschweren; für ein Unternehmen mit Sitz in Frankfurt am Main ist
        insbesondere der Hessische Beauftragte für Datenschutz und Informationsfreiheit zuständig.
      </p>

      <h2>13. Änderungen</h2>
      <p>
        Diese Information wird angepasst, wenn Funktionen, Empfänger oder Rechtsgrundlagen der A+ Solution App wesentlich
        geändert werden. Die jeweils aktuelle Fassung ist dauerhaft unter <a href="/datenschutz">/datenschutz</a>
        erreichbar.
      </p>
    </Shell>
  );
}

function Deletion() {
  return (
    <Shell title="Kontolöschung und Datenlöschung">
      <p>
        Die A+ Solution App ist eine interne Unternehmensanwendung. Nutzer können sich nicht selbst registrieren;
        Zugänge werden von der A+ Solution GmbH administrativ angelegt oder per persönlicher Einladung aktiviert.
      </p>
      <h2>Löschung in der App anfragen</h2>
      <p>
        Angemeldete Nutzer öffnen <strong>Mein Profil</strong> und wählen <strong>„Kontolöschung anfragen“</strong>.
        Die Anfrage wird im System dokumentiert und von der Administration bearbeitet.
      </p>
      <h2>Löschung ohne App anfragen</h2>
      <p>
        Sende eine E-Mail von oder unter Angabe deiner registrierten E-Mail-Adresse an
        <a href={`mailto:${COMPANY.email}`}> {COMPANY.email}</a> mit dem Betreff „A+ Solution App – Löschanfrage“.
        Zur Vermeidung unberechtigter Löschungen kann eine Identitätsprüfung erforderlich sein.
      </p>
      <h2>Was gelöscht wird</h2>
      <p>
        Der App-Zugang wird deaktiviert und personenbezogene Daten, die nicht mehr benötigt werden, werden gelöscht oder
        anonymisiert. Daten, die A+ Solution aufgrund arbeits-, handels-, steuer-, sozialversicherungs- oder sonstiger
        gesetzlicher Pflichten weiter aufbewahren muss, sowie Daten, die zur Geltendmachung oder Abwehr von Ansprüchen
        erforderlich sind, werden erst nach Wegfall des Aufbewahrungsgrundes gelöscht.
      </p>
      <p>
        Weitere Einzelheiten stehen in der <a href="/datenschutz">Datenschutzinformation</a>.
      </p>
    </Shell>
  );
}

function Imprint() {
  return (
    <Shell title="Impressum">
      <p><strong>{COMPANY.name}</strong></p>
      <p>{COMPANY.address}</p>
      <p>Geschäftsführer: {COMPANY.managingDirector}</p>
      <p>Handelsregister: {COMPANY.register}</p>
      <p>USt-IdNr.: {COMPANY.vat}</p>
      <p>
        Telefon: <a href="tel:+496921000418">{COMPANY.phone}</a><br />
        Mobil: <a href="tel:+491727779721">{COMPANY.mobile}</a><br />
        E-Mail: <a href={`mailto:${COMPANY.email}`}>{COMPANY.email}</a><br />
        Website: <a href={COMPANY.website} rel="noreferrer">aplus-solution.de</a>
      </p>
    </Shell>
  );
}

function Support() {
  return (
    <Shell title="Support für die A+ Solution App">
      <p>
        Die A+ Solution App ist ausschließlich für freigeschaltete Mitarbeiter, Disposition und Management vorgesehen.
        Es gibt keine öffentliche Registrierung.
      </p>
      <h2>Zugang</h2>
      <p>
        Wenn du noch keinen Zugang hast, wende dich an die interne Administration. Ein Konto wird zuerst im
        A+ Solution-System angelegt; anschließend erhältst du deine Zugangsdaten oder eine persönliche Aktivierungseinladung.
      </p>
      <h2>Technische Hilfe</h2>
      <p>
        E-Mail: <a href={`mailto:${COMPANY.email}`}>{COMPANY.email}</a><br />
        Telefon: <a href="tel:+496921000418">{COMPANY.phone}</a>
      </p>
      <h2>Datenschutz und Löschung</h2>
      <p>
        <a href="/datenschutz">Datenschutzinformation öffnen</a><br />
        <a href="/konto-loeschen">Kontolöschung oder Datenlöschung anfragen</a>
      </p>
    </Shell>
  );
}

export function legalPageFromPath(pathname: string): LegalPage | null {
  const path = pathname.replace(/\/+$/, '') || '/';
  if (path === '/datenschutz' || path === '/privacy') return 'privacy';
  if (path === '/konto-loeschen' || path === '/account-deletion') return 'deletion';
  if (path === '/impressum') return 'imprint';
  if (path === '/support') return 'support';
  return null;
}

export default function StoreLegalPage({ page }: { page: LegalPage }) {
  if (page === 'privacy') return <Privacy />;
  if (page === 'deletion') return <Deletion />;
  if (page === 'imprint') return <Imprint />;
  return <Support />;
}
