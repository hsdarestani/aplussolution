from pathlib import Path

# Keep Operations business-date defaults in Europe/Berlin.
p=Path('frontend/src/Operations.tsx')
s=p.read_text()
helper="const berlinDateKey = (date = new Date()) => { const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Berlin',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(date); const get=(type:string)=>parts.find(item=>item.type===type)?.value||''; return `${get('year')}-${get('month')}-${get('day')}`; };"
if 'const berlinDateKey =' not in s:
    marker="const API = String(import.meta.env.VITE_API_URL || '/api').replace(/\\/$/, '');"
    if marker not in s: raise SystemExit('Operations API marker missing')
    s=s.replace(marker, marker+'\n'+helper, 1)
s=s.replace("{ month: new Date().toISOString().slice(0, 7) }", "{ month: berlinDateKey().slice(0, 7) }")
p.write_text(s)

# Preserve the successful save confirmation after reloading the Digital Akte.
p=Path('frontend/src/AktePage.tsx')
s=p.read_text()
old="setData(result); setEditing(false); setMessage('Akte wurde gespeichert.'); await load();"
new="setData(result); setEditing(false); await load(); setMessage('Akte wurde gespeichert.');"
if old in s:
    s=s.replace(old,new,1)
elif new not in s:
    raise SystemExit('AktePage save marker missing')
p.write_text(s)
