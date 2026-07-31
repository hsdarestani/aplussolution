from pathlib import Path

app = Path('frontend/src/App.tsx')
text = app.read_text(encoding='utf-8')

import_marker = "import ListToolbar from './ListToolbar';\n"
import_line = "import DocumentCenterV5 from './DocumentCenterV5';\n"
if import_line not in text:
    if import_marker not in text:
        raise SystemExit('ListToolbar import marker not found')
    text = text.replace(import_marker, import_marker + import_line, 1)

start = text.index('function Contracts(')
end = text.index('function Documents(', start)
chunk = text[start:end]

cancel_function_marker = '''  async function remove(id: string) {
    if (!window.confirm('Diesen Vertragsentwurf löschen?')) return;
    try {
      await api(`contracts/${id}/`, { method: 'DELETE' });
      await load();
      setToast('Vertrag wurde gelöscht.');
    } catch (reason: any) {
      setToast(reason.message);
    }
  }

'''
cancel_function = '''  async function remove(id: string) {
    if (!window.confirm('Diesen Vertragsentwurf löschen?')) return;
    try {
      await api(`contracts/${id}/`, { method: 'DELETE' });
      await load();
      setToast('Vertrag wurde gelöscht.');
    } catch (reason: any) {
      setToast(reason.message);
    }
  }

  async function cancelContract(id: string) {
    const reason = window.prompt('Warum wird dieser Vertrag storniert?');
    if (!reason) return;
    try {
      await api(`contracts/${id}/cancel/`, { method: 'POST', body: JSON.stringify({ reason }) });
      await load();
      setToast('Vertrag wurde storniert und bleibt in der Akte erhalten.');
    } catch (reason: any) {
      setToast(reason.message);
    }
  }

'''
if 'async function cancelContract' not in chunk:
    if cancel_function_marker not in chunk:
        raise SystemExit('Contract remove marker not found')
    chunk = chunk.replace(cancel_function_marker, cancel_function, 1)

center_marker = '''      <ListToolbar
        query={listQuery}'''
center_block = '''      {isManager(user) && <DocumentCenterV5 onChanged={load} />}
      <ListToolbar
        query={listQuery}'''
if '<DocumentCenterV5' not in chunk:
    if center_marker not in chunk:
        raise SystemExit('Contract ListToolbar marker not found')
    chunk = chunk.replace(center_marker, center_block, 1)

row_marker = '<div className="row contract-row" key={contract.id}>'
row_replacement = '<div className="row contract-row" id={`contract-${contract.id}`} key={contract.id}>'
if row_replacement not in chunk:
    if row_marker not in chunk:
        raise SystemExit('Contract row marker not found')
    chunk = chunk.replace(row_marker, row_replacement, 1)

send_button_marker = '''                {contract.status === 'draft' && (
                  <IonButton fill="clear" color="danger" onClick={() => remove(contract.id)}>
                    <IonIcon icon={trashOutline} />
                  </IonButton>
                )}
'''
send_button_replacement = '''                {contract.status === 'draft' && (
                  <IonButton fill="clear" color="danger" onClick={() => remove(contract.id)}>
                    <IonIcon icon={trashOutline} />
                  </IonButton>
                )}
                {['ready', 'sent'].includes(contract.status) && !contract.signatures?.length && (
                  <IonButton size="small" fill="clear" color="danger" onClick={() => cancelContract(contract.id)}>
                    Stornieren
                  </IonButton>
                )}
'''
if "cancelContract(contract.id)" not in chunk:
    if send_button_marker not in chunk:
        raise SystemExit('Contract action marker not found')
    chunk = chunk.replace(send_button_marker, send_button_replacement, 1)

old_sign_condition = "{(['client', 'worker'].includes(user.role) || isManager(user)) && ['ready', 'sent', 'signed'].includes(contract.status) && !contract.signatures?.some((item: any) => item.role === (isManager(user) ? 'employer' : user.role === 'worker' ? 'employee' : 'client')) && ("
new_sign_condition = "{(['client', 'worker'].includes(user.role) || isManager(user)) && ['ready', 'sent'].includes(contract.status) && !contract.signatures?.some((item: any) => item.role === (isManager(user) ? 'employer' : user.role === 'worker' ? 'employee' : 'client')) && ("
if new_sign_condition not in chunk:
    if old_sign_condition not in chunk:
        raise SystemExit('Contract sign condition marker not found')
    chunk = chunk.replace(old_sign_condition, new_sign_condition, 1)

text = text[:start] + chunk + text[end:]
app.write_text(text, encoding='utf-8')

center = Path('frontend/src/DocumentCenterV5.tsx')
source = center.read_text(encoding='utf-8')
old = '''      } else {
        sessionStorage.setItem('aplus:focus', JSON.stringify({ view: 'contracts', id: item.id, source: 'document-center' }));
        setToast('Der Vorgang ist unten in der Vertragsliste markiert.');
      }
      await load();
'''
new = '''      } else {
        sessionStorage.setItem('aplus:focus', JSON.stringify({ view: 'contracts', id: item.id, source: 'document-center' }));
        window.setTimeout(() => document.getElementById(`contract-${item.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 40);
        setToast('Der Vorgang wurde in der Vertragsliste geöffnet.');
      }
      await load();
'''
if new not in source:
    if old not in source:
        raise SystemExit('Document center focus marker not found')
    source = source.replace(old, new, 1)
center.write_text(source, encoding='utf-8')
