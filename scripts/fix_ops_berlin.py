from pathlib import Path
p=Path('frontend/src/Operations.tsx')
s=p.read_text()
helper="const berlinDateKey = (date = new Date()) => { const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Berlin',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(date); const get=(type:string)=>parts.find(item=>item.type===type)?.value||''; return `${get('year')}-${get('month')}-${get('day')}`; };"
if 'const berlinDateKey =' not in s:
    marker="const API = String(import.meta.env.VITE_API_URL || '/api').replace(/\\/$/, '');"
    if marker not in s: raise SystemExit('Operations API marker missing')
    s=s.replace(marker, marker+'\n'+helper, 1)
s=s.replace("{ month: new Date().toISOString().slice(0, 7) }", "{ month: berlinDateKey().slice(0, 7) }")
p.write_text(s)
