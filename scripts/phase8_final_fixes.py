from pathlib import Path


def replace_once(path, old, new):
    file = Path(path)
    text = file.read_text(encoding='utf-8')
    if old not in text:
        raise SystemExit(f'Expected block not found in {path}: {old[:120]!r}')
    file.write_text(text.replace(old, new, 1), encoding='utf-8')


# 1) Keep signer identity searchable/auditable regardless of smart signature placement source.
replace_once(
    'backend/core/signature_pdf.py',
    """            if placement.get('source') == 'legacy-fallback':\n                role_label = _ROLE_LABELS.get(signature.role, role)\n                label_y = max(7.0, rect.y0 - 8.0)\n                name_y = min(page.rect.height - 5.0, rect.y1 + 9.0)\n                page.insert_text((rect.x0, label_y), role_label, fontsize=7, color=(0.35, 0.39, 0.45), overlay=True)\n                page.insert_text((rect.x0, name_y), signature.signer_name[:70], fontsize=7, color=(0.15, 0.18, 0.22), overlay=True)\n""",
    """            if placement.get('source') == 'legacy-fallback':\n                role_label = _ROLE_LABELS.get(signature.role, role)\n                label_y = max(7.0, rect.y0 - 8.0)\n                page.insert_text((rect.x0, label_y), role_label, fontsize=7, color=(0.35, 0.39, 0.45), overlay=True)\n\n            # Keep signer identity as searchable/auditable text for every placement.\n            name_y = min(page.rect.height - 5.0, rect.y1 + 9.0)\n            page.insert_text((rect.x0, name_y), signature.signer_name[:70], fontsize=7, color=(0.15, 0.18, 0.22), overlay=True)\n""",
)

# 2) Day/week/month mobile cards must retain worker claim/release actions.
replace_once(
    'frontend/src/ScheduleV2.tsx',
    """  const renderMini=(item:any,compact=false)=>{const status=statusInfo(item);const canOpen=isManager(user);return <article style={clientStyle(item)} className={`sv2-event ${compact?'compact':''}`} key={item.id} role={canOpen?'button':undefined} tabIndex={canOpen?0:undefined} onClick={()=>openItem(item)} onKeyDown={event=>{if(canOpen&&(event.key==='Enter'||event.key===' ')){event.preventDefault();openItem(item);}}}><div className=\"sv2-event-head\"><strong>{item.position_name||'Einsatz'}</strong><span>{status.label}</span></div>{renderShiftDetails(item,compact)}</article>;};\n""",
    """  const renderMini=(item:any,compact=false)=>{const status=statusInfo(item);const canOpen=isManager(user);const mine=workerView&&tab==='mine';return <article style={clientStyle(item)} className={`sv2-event ${compact?'compact':''}`} key={item.id} role={canOpen?'button':undefined} tabIndex={canOpen?0:undefined} onClick={()=>openItem(item)} onKeyDown={event=>{if(canOpen&&(event.key==='Enter'||event.key===' ')){event.preventDefault();openItem(item);}}}><div className=\"sv2-event-head\"><strong>{item.position_name||'Einsatz'}</strong><span>{status.label}</span></div>{renderShiftDetails(item,compact)}{workerView&&<div className=\"sv2-mini-actions\">{!mine&&status.open&&<IonButton size=\"small\" disabled={busy} onClick={event=>{event.stopPropagation();void act(`shifts/${item.id}/claim/`,'Schicht übernommen.');}}><IonIcon slot=\"start\" icon={checkmarkCircleOutline}/>Übernehmen</IonButton>}{mine&&<IonButton size=\"small\" fill=\"outline\" color=\"medium\" disabled={busy} onClick={event=>{event.stopPropagation();setReleaseTarget(item);}}>Freigeben</IonButton>}</div>}</article>;};\n""",
)

replace_once(
    'frontend/src/phase8-wiw-mobile.css',
    """  .sv2-event-details { gap:3px !important; }\n""",
    """  .sv2-event-details { gap:3px !important; }\n  .sv2-mini-actions {\n    display:flex;\n    justify-content:flex-end;\n    gap:6px;\n    margin-top:5px;\n  }\n  .sv2-mini-actions ion-button {\n    margin:0;\n    min-height:28px;\n    font-size:9px;\n  }\n""",
)

# 3) Scope worker mobile assertions to the visible Phase 8 day view, not hidden duplicate markup.
replace_once(
    'frontend/e2e/app-shell.spec.ts',
    """    await expect(page.getByText('Servicekraft', { exact: true }).first()).toBeVisible();\n    await expect(page.getByText('Main Suites Frankfurt', { exact: true }).first()).toBeVisible();\n""",
    """    const dayView = page.getByTestId('schedule-day-view');\n    await expect(dayView.getByText('Servicekraft', { exact: true }).first()).toBeVisible();\n    await expect(dayView.getByText('Main Suites Frankfurt', { exact: true }).first()).toBeVisible();\n""",
)

# Client has Dashboard / Dienstplan / Mehr; Zeiterfassung is intentionally not a client feature.
replace_once(
    'frontend/e2e/app-shell.spec.ts',
    """    await expect(page.getByText('Zu unterzeichnen')).toBeVisible();\n    await expect(page.locator('.mobile-tabbar button')).toHaveCount(4);\n""",
    """    await expect(page.getByText('Zu unterzeichnen')).toBeVisible();\n    await expect(page.locator('.mobile-tabbar button')).toHaveCount(3);\n""",
)

# 4) Mobile Phase 8 intentionally exposes one day view plus week strip; desktop retains all planning views.
replace_once(
    'frontend/e2e/berlin-schedule.spec.ts',
    """test('planning views keep overflow inside the workspace on mobile', async ({ page }) => {\n  await page.setViewportSize({ width: 390, height: 844 }); await page.clock.setFixedTime(fixedNow); await mockAdmin(page); await page.goto('/?view=schedule');\n  const views: Array<[string, string]> = [\n    ['day', 'schedule-day-view'],\n    ['week', 'schedule-week-view'],\n    ['month', 'schedule-month-view'],\n    ['timeline', 'schedule-timeline-view'],\n  ];\n  for (const [key, testId] of views) {\n    await page.getByTestId(`schedule-view-${key}`).click();\n    await expect(page.getByTestId(testId)).toBeVisible();\n    const noPageOverflow = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);\n    expect(noPageOverflow).toBeTruthy();\n  }\n});\n""",
    """test('Phase 8 mobile planning keeps the day workspace and week strip inside the viewport', async ({ page }) => {\n  await page.setViewportSize({ width: 390, height: 844 }); await page.clock.setFixedTime(fixedNow); await mockAdmin(page); await page.goto('/?view=schedule');\n  await expect(page.getByTestId('phase8-week-strip')).toBeVisible();\n  await expect(page.getByTestId('schedule-day-view')).toBeVisible();\n  await expect(page.getByTestId('schedule-view-toolbar')).toBeHidden();\n  const noPageOverflow = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);\n  expect(noPageOverflow).toBeTruthy();\n});\n""",
)

# 5) Manager creation moved to the visible Phase 8 floating + control on mobile.
replace_once(
    'frontend/e2e/friendly-datetime.spec.ts',
    "await page.getByTestId('schedule-create-manual').click();",
    "await page.getByRole('button', { name: 'Schicht anlegen' }).click();",
)

# 6) Aufträge still exists; only the obsolete admin quick-action label was removed in Phase 8.
replace_once(
    'frontend/e2e/orders-timezone.spec.ts',
    """  await page.goto('/');\n  await page.getByText('Aufträge & AI', { exact: true }).first().click();\n""",
    """  await page.goto('/?view=orders');\n""",
)

print('Phase 8 final fixes applied.')
