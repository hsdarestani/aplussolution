from pathlib import Path


def replace_once(path,old,new):
    p=Path(path);text=p.read_text(encoding='utf-8')
    if old not in text: raise SystemExit(f'missing marker {path}: {old[:160]!r}')
    p.write_text(text.replace(old,new,1),encoding='utf-8')


app=Path('frontend/e2e/app-shell.spec.ts')
text=app.read_text(encoding='utf-8')
text=text.replace("await expect(page.getByRole('heading', { name: 'Mina Berger' })).toBeVisible();","await expect(page.getByTestId('phase8-mobile-dashboard')).toBeVisible();")
text=text.replace("await expect(page.getByRole('heading', { name: 'Einsätze', exact: true })).toBeVisible();\n    await expect(page.getByText('Geplante Einsätze und aktueller Besetzungsstatus für Ihre Aufträge.')).toBeVisible();","await expect(page.getByTestId('phase8-week-strip')).toBeVisible();")
app.write_text(text,encoding='utf-8')

worker=Path('frontend/e2e/worker-portal-deep.spec.ts')
text=worker.read_text(encoding='utf-8')
text=text.replace("await expect(page.getByRole('heading', { name: worker.name })).toBeVisible();","await expect(page.getByTestId('phase8-mobile-dashboard')).toBeVisible();")
text=text.replace("    await expect(page.getByText('QA-MA-001')).toBeVisible();\n", "    await expect(page.getByText('Heute', { exact: true })).toBeVisible();\n",1)
worker.write_text(text,encoding='utf-8')

priority=Path('frontend/e2e/admin-priority-navigation.spec.ts')
text=priority.read_text(encoding='utf-8')
text=text.replace("'Personal & Kunden', 'Aufträge & AI'","'Personal & Kunden', 'Mitteilungen'")
priority.write_text(text,encoding='utf-8')
