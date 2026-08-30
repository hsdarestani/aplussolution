from pathlib import Path

p = Path(__file__).with_name('final_schedule_ux_patch.py')
text = p.read_text(encoding='utf-8')
old = '"setClients(unpack(c).filter(item=>item.active!==false));"'
new = '"setClients(unpack(c).filter((item:any)=>item.active!==false));"'
if old not in text:
    raise SystemExit('bootstrap target not found')
p.write_text(text.replace(old, new, 1), encoding='utf-8')
print('bootstrap: OK')
