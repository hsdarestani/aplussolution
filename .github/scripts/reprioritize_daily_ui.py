from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f'{label} anchor not found')
    return text.replace(old, new, 1)


app_path = Path('frontend/src/App.tsx')
app = app_path.read_text()

old_nav = """  admin: [
    ['dashboard', 'Übersicht'],
    ['schedule', 'Dienstplanung'],
    ['time', 'Zeiterfassung'],
    ['contracts', 'Verträge'],
    ['documents', 'Dokumente'],
    ['orders', 'Aufträge'],
    ['people', 'Personal & Kunden'],
    ['messages', 'Nachrichten'],
    ['operations', 'Steuerzentrale'],
  ],
  manager: [
    ['dashboard', 'Übersicht'],
    ['schedule', 'Dienstplanung'],
    ['time', 'Zeiterfassung'],
    ['contracts', 'Verträge'],
    ['documents', 'Dokumente'],
    ['orders', 'Aufträge'],
    ['people', 'Personal & Kunden'],
    ['messages', 'Nachrichten'],
    ['operations', 'Steuerzentrale'],
  ],"""
new_nav = """  admin: [
    ['dashboard', 'Übersicht'],
    ['orders', 'Auftragseingang & AI'],
    ['schedule', 'Dienstplanung'],
    ['time', 'Zeiterfassung'],
    ['people', 'Personal & Kunden'],
    ['contracts', 'Verträge & ANÜ'],
    ['documents', 'Dokumente & Lohn'],
    ['messages', 'Nachrichten'],
    ['operations', 'Mehr / Steuerzentrale'],
  ],
  manager: [
    ['dashboard', 'Übersicht'],
    ['orders', 'Auftragseingang & AI'],
    ['schedule', 'Dienstplanung'],
    ['time', 'Zeiterfassung'],
    ['people', 'Personal & Kunden'],
    ['contracts', 'Verträge & ANÜ'],
    ['documents', 'Dokumente & Lohn'],
    ['messages', 'Nachrichten'],
    ['operations', 'Mehr / Steuerzentrale'],
  ],"""
app = replace_once(app, old_nav, new_nav, 'admin/manager nav')

old_primary = """  const primaryViews: View[] = ['dashboard', 'schedule', 'time', 'messages'];
  const mobilePrimaryItems = items.filter(([key]) => primaryViews.includes(key));"""
new_primary = """  const primaryViews: View[] = isManager(user)
    ? ['orders', 'schedule', 'time', 'people']
    : ['dashboard', 'schedule', 'time', 'messages'];
  const mobilePrimaryItems = items.filter(([key]) => primaryViews.includes(key));"""
app = replace_once(app, old_primary, new_primary, 'primary mobile nav')

old_labels = """  const mobileLabels: Partial<Record<View, string>> = {
    dashboard: 'Start',
    schedule: 'Plan',
    time: 'Zeit',
    messages: 'Chat',
  };"""
new_labels = """  const mobileLabels: Partial<Record<View, string>> = {
    dashboard: 'Start',
    orders: 'Aufträge',
    schedule: 'Plan',
    time: 'Zeit',
    people: 'Personal',
    messages: 'Chat',
  };"""
app = replace_once(app, old_labels, new_labels, 'mobile labels')

hero_old = """        <span>● System aktiv</span>
      </div>
      <div className=\"stats\">"""
hero_new = """        <span>● System aktiv</span>
      </div>
      {isManager(user) && (
        <div className=\"button-group priority-actions\">
          <IonButton onClick={() => navigate('orders')}><IonIcon slot=\"start\" icon={briefcaseOutline} />Auftrag & AI</IonButton>
          <IonButton fill=\"outline\" onClick={() => navigate('schedule')}><IonIcon slot=\"start\" icon={calendarOutline} />Dienstplan</IonButton>
          <IonButton fill=\"outline\" onClick={() => navigate('time')}><IonIcon slot=\"start\" icon={stopwatchOutline} />Zeiterfassung</IonButton>
          <IonButton fill=\"outline\" onClick={() => navigate('people')}><IonIcon slot=\"start\" icon={peopleOutline} />Personal</IonButton>
          <IonButton fill=\"clear\" href=\"?view=operations#arbeitszeitkonto\">Arbeitszeit & Lohn</IonButton>
        </div>
      )}
      <div className=\"stats\">"""
app = replace_once(app, hero_old, hero_new, 'dashboard priority actions')

state_old = """  const [listSort, setListSort] = useState('-starts_at');

  const load = async () => {"""
state_new = """  const [listSort, setListSort] = useState('-starts_at');
  const [aiOpen, setAiOpen] = useState(false);
  const [orderText, setOrderText] = useState('');
  const [parsedOrder, setParsedOrder] = useState<any>();

  const load = async () => {"""
app = replace_once(app, state_old, state_new, 'orders AI state')

func_old = """  async function remove(id: string) {
    if (!window.confirm('Diesen Auftrag löschen?')) return;
    try {
      await api(`orders/${id}/`, { method: 'DELETE' });
      await load();
      setToast('Auftrag wurde gelöscht.');
    } catch (reason: any) {
      setToast(reason.message);
    }
  }

  return ("""
func_new = """  async function remove(id: string) {
    if (!window.confirm('Diesen Auftrag löschen?')) return;
    try {
      await api(`orders/${id}/`, { method: 'DELETE' });
      await load();
      setToast('Auftrag wurde gelöscht.');
    } catch (reason: any) {
      setToast(reason.message);
    }
  }

  async function parseAiOrder() {
    if (!orderText.trim()) {
      setToast('Bitte zuerst den Text der Kundenanfrage einfügen.');
      return;
    }
    setBusy(true);
    try {
      const result: any = await api('automation/orders/parse/', {
        method: 'POST',
        body: JSON.stringify({ text: orderText }),
      });
      setParsedOrder(result);
      setToast(`${result.shifts?.length || 0} Schicht(en) erkannt. Bitte kurz prüfen.`);
    } catch (reason: any) {
      setToast(reason.message);
    } finally {
      setBusy(false);
    }
  }

  async function approveAiOrder() {
    if (!parsedOrder) return void parseAiOrder();
    setBusy(true);
    try {
      const result: any = await api('automation/orders/approve/', {
        method: 'POST',
        body: JSON.stringify({ parsed: parsedOrder, raw_text: orderText }),
      });
      setAiOpen(false);
      setOrderText('');
      setParsedOrder(undefined);
      await load();
      setToast(`${result.created_count || 0} Personalplatz/-plätze als OpenShift in A+ Workforce erstellt.`);
    } catch (reason: any) {
      setToast(reason.message);
    } finally {
      setBusy(false);
    }
  }

  return ("""
app = replace_once(app, func_old, func_new, 'orders AI functions')

title_old = """      <Title
        title=\"Aufträge\"
        text=\"Veranstaltungen und Personalbedarf direkt übermitteln und disponieren.\"
        action={
          <IonButton onClick={() => setOpen(true)}>
            <IonIcon slot=\"start\" icon={addOutline} />
            Neuer Auftrag
          </IonButton>
        }
      />"""
title_new = """      <Title
        title={isManager(user) ? 'Auftragseingang & AI' : 'Aufträge'}
        text={isManager(user) ? 'Kundenanfragen einlesen, mit AI prüfen und direkt als OpenShifts disponieren.' : 'Veranstaltungen und Personalbedarf direkt übermitteln.'}
        action={
          <div className=\"button-group\">
            {isManager(user) && (
              <IonButton onClick={() => { setParsedOrder(undefined); setAiOpen(true); }}>
                <IonIcon slot=\"start\" icon={briefcaseOutline} />
                Anfrage mit AI einlesen
              </IonButton>
            )}
            <IonButton fill={isManager(user) ? 'outline' : 'solid'} onClick={() => setOpen(true)}>
              <IonIcon slot=\"start\" icon={addOutline} />
              Neuer Auftrag
            </IonButton>
          </div>
        }
      />
      {isManager(user) && (
        <div className=\"notice\">
          <b>Schnellster Ablauf:</b> Kundenmail kopieren → AI analysiert Datum, Zeiten, Anzahl, Position und Einsatzort → kurz prüfen → OpenShifts erstellen.
        </div>
      )}"""
app = replace_once(app, title_old, title_new, 'orders title/actions')

modal_old = """      <FormModal
        open={open}
        title=\"Neuer Personalauftrag\""""
modal_new = """      <FormModal
        open={aiOpen}
        title=\"Kundenanfrage mit AI einlesen\"
        onClose={() => { setAiOpen(false); setParsedOrder(undefined); }}
        onSave={parsedOrder ? approveAiOrder : parseAiOrder}
        busy={busy}
        saveLabel={parsedOrder ? 'Prüfen & OpenShifts erstellen' : 'Mit AI analysieren'}
      >
        <IonTextarea
          className=\"full\"
          autoGrow
          fill=\"outline\"
          label=\"Text aus Kunden-E-Mail / Anfrage\"
          labelPlacement=\"floating\"
          value={orderText}
          onIonInput={(event) => { setOrderText(String(value(event))); setParsedOrder(undefined); }}
        />
        {parsedOrder && (
          <div className=\"notice full\">
            <b>{parsedOrder.request_id || 'Auftrag erkannt'}</b>
            <p>Bitte diese erkannten Schichten vor dem Erstellen kurz prüfen:</p>
            {parsedOrder.shifts?.map((item: any, index: number) => (
              <div key={index}>
                {item.date} · {item.start_time}–{item.end_time} · {item.count}× {item.role} · {item.site_text || item.location_text}
              </div>
            ))}
          </div>
        )}
      </FormModal>

      <FormModal
        open={open}
        title=\"Neuer Personalauftrag\""""
app = replace_once(app, modal_old, modal_new, 'orders AI modal')
app_path.write_text(app)

ops_path = Path('frontend/src/Operations.tsx')
ops = ops_path.read_text()

import_old = """import { api, User } from './api';
import './operations.css';"""
import_new = """import { api, User } from './api';
import PremiumOperations from './PremiumOperations';
import './operations.css';"""
ops = replace_once(ops, import_old, import_new, 'PremiumOperations import')
ops = ops.replace("'OpenShifts wurden in When I Work erstellt.'", "'OpenShifts wurden in A+ Workforce erstellt.'")
ops = ops.replace("'Prüfen & in WIW erstellen'", "'Prüfen & OpenShifts erstellen'")
ops = ops.replace('>Aus WIW synchronisieren</IonButton>', '>Arbeitszeit aktualisieren</IonButton>')
ops = ops.replace('Manuelle Auszahlungen und Korrekturen bleiben bei jeder WIW-Synchronisierung erhalten.', 'Manuelle Auszahlungen und Korrekturen bleiben bei jeder Aktualisierung erhalten.')
if 'id="arbeitszeitkonto"' not in ops:
    ops = ops.replace('<section className="operations-panel" data-testid="working-time-panel">', '<section id="arbeitszeitkonto" className="operations-panel" data-testid="working-time-panel">', 1)
ops = ops.replace('<div className="operations-head"><div><h3>When I Work</h3><p>Personal, Orte, Positionen, Schichten, Zeiten und Abwesenheiten automatisch übernehmen.</p></div>', '<div className="operations-head"><div><h3>WIW Migration / Altbestand</h3><p>Nur noch für historischen Abgleich und Migration; A+ Workforce ist das operative Hauptsystem.</p></div>', 1)
notify_old = """      <Notifications rows={data.notifications || []} readAll={readAll} />"""
notify_new = """      {isManager(user) && <PremiumOperations user={user} />}

      <Notifications rows={data.notifications || []} readAll={readAll} />"""
ops = replace_once(ops, notify_old, notify_new, 'PremiumOperations render')
ops_path.write_text(ops)
