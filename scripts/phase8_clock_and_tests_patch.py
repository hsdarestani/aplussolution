from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target=Path(path)
    text=target.read_text(encoding='utf-8')
    if old not in text:
        raise SystemExit(f'missing marker in {path}: {old[:180]!r}')
    target.write_text(text.replace(old,new,1),encoding='utf-8')


replace_once(
    'frontend/src/EmployeeHome.tsx',
    "<button type=\"button\" onClick={()=>navigate('time')}>Einstempeln</button>",
    "<button type=\"button\" onClick={()=>{sessionStorage.setItem('phase8:attendance-clock','1');navigate('time');}}>Einstempeln</button>",
)

replace_once(
    'frontend/src/AttendanceV3.tsx',
    """  const [closeTarget, setCloseTarget] = useState<any>();

  const load = async () => {""",
    """  const [closeTarget, setCloseTarget] = useState<any>();
  const [mobileClockMode] = useState(() => {
    if (typeof window === 'undefined') return false;
    try {
      const requested = sessionStorage.getItem('phase8:attendance-clock') === '1';
      if (requested) sessionStorage.removeItem('phase8:attendance-clock');
      return requested;
    } catch {
      return false;
    }
  });

  const load = async () => {""",
)
replace_once(
    'frontend/src/AttendanceV3.tsx',
    "if (user.role === 'worker' && typeof window !== 'undefined' && window.matchMedia('(max-width: 900px)').matches) {",
    "if (user.role === 'worker' && !mobileClockMode && typeof window !== 'undefined' && window.matchMedia('(max-width: 900px)').matches) {",
)

# Mobile shell tests: bottom-tab Attendance is Pay Periods, dashboard Clock-In opens full clock mode.
app=Path('frontend/e2e/app-shell.spec.ts')
text=app.read_text(encoding='utf-8')
text=text.replace(
    "await expect(page.getByRole('heading', { name: 'Bereit für deinen Einsatz?' })).toBeVisible();\n    await expect(page.getByRole('button', { name: 'Einstempeln' })).toBeEnabled();",
    "await expect(page.getByTestId('phase8-pay-periods')).toBeVisible();\n    await expect(page.getByText('Abrechnungszeiträume', { exact: true })).toBeVisible();",
    1,
)
text=text.replace(
    "await expect(page.getByRole('heading', { name: 'Bereit für deinen Einsatz?' })).toBeVisible();\n    await expect.poll(() => new URL(page.url()).searchParams.get('view')).toBe('time');",
    "await expect(page.getByTestId('phase8-pay-periods')).toBeVisible();\n    await expect.poll(() => new URL(page.url()).searchParams.get('view')).toBe('time');",
    1,
)
text=text.replace(
    "await expect(page.getByRole('heading', { name: 'Bereit für deinen Einsatz?' })).toBeVisible();\n    await expect.poll(() => new URL(page.url()).searchParams.get('view')).toBe('time');",
    "await expect(page.getByTestId('phase8-pay-periods')).toBeVisible();\n    await expect.poll(() => new URL(page.url()).searchParams.get('view')).toBe('time');",
    1,
)
text=text.replace(
    "await expect(page.getByRole('heading', { name: 'Schichten' })).toBeVisible();",
    "await expect(page.getByTestId('phase8-week-strip')).toBeVisible();",
)
text=text.replace(
    "await expect(moreMenu.getByRole('button', { name: 'Ranking', exact: true })).toBeVisible();",
    "await expect(moreMenu.getByRole('button', { name: 'Ranking', exact: true })).toBeVisible();\n    await expect(moreMenu.getByRole('button', { name: 'Mitteilungen', exact: true })).toBeVisible();",
    1,
)
app.write_text(text,encoding='utf-8')

worker=Path('frontend/e2e/worker-portal-deep.spec.ts')
text=worker.read_text(encoding='utf-8')
text=text.replace(
    """    await page.goto('/?view=time');
    await page.getByRole('button', { name: 'Einstempeln' }).click();""",
    """    await page.goto('/');
    await page.getByTestId('phase8-mobile-dashboard').getByRole('button', { name: 'Einstempeln' }).click();
    await expect(page.getByRole('heading', { name: 'Bereit für deinen Einsatz?' })).toBeVisible();
    await page.getByRole('button', { name: 'Einstempeln' }).click();""",
    1,
)
worker.write_text(text,encoding='utf-8')
