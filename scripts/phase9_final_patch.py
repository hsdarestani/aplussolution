from pathlib import Path


def replace_once(path: str, old: str, new: str):
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    if old not in text:
        raise SystemExit(f'missing marker in {path}: {old[:120]!r}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')

# Full history endpoint: workers see their own; admin/manager see the imported workforce archive.
replace_once(
    'backend/core/attendance_views.py',
    "\n\n@api_view(['POST'])\ndef request_time_correction(request, entry_id):\n",
    "\n\n@api_view(['GET'])\ndef attendance_history(request):\n    if request.user.role == User.Role.WORKER:\n        queryset = TimeEntry.objects.filter(worker=request.user.worker_profile)\n    elif _manager_only(request):\n        queryset = TimeEntry.objects.exclude(worker__user__email__iendswith=SYNTHETIC_MIGRATION_EMAIL_SUFFIX)\n    else:\n        return Response({'detail': 'Keine Berechtigung.'}, status=403)\n\n    queryset = queryset.select_related('shift__position', 'worker__user').filter(\n        clock_out__isnull=False,\n    ).order_by('-clock_in')\n    return Response({\n        'count': queryset.count(),\n        'history': TimeEntrySerializer(queryset, many=True, context={'request': request}).data,\n    })\n\n\n@api_view(['POST'])\ndef request_time_correction(request, entry_id):\n",
)
replace_once(
    'backend/core/urls.py',
    "    path('attendance/home/', attendance_views.employee_attendance_home),\n",
    "    path('attendance/home/', attendance_views.employee_attendance_home),\n    path('attendance/history/', attendance_views.attendance_history),\n",
)

# Mobile attendance consumes the full archive for both worker and manager mobile views.
replace_once(
    'frontend/src/AttendanceV3.tsx',
    "  const load = async () => {\n    const [main, timeOff] = await Promise.all([\n      api(isManager(user) ? 'attendance/exceptions/' : 'attendance/home/'),\n      api('time-off/'),\n    ]);\n    setData(main);\n    setAbsences(unpack(timeOff));\n  };\n",
    "  const load = async () => {\n    const mobile = typeof window !== 'undefined' && window.matchMedia('(max-width: 900px)').matches;\n    const requests: Promise<any>[] = [\n      api(isManager(user) ? 'attendance/exceptions/' : 'attendance/home/'),\n      api('time-off/'),\n    ];\n    if (mobile && (isManager(user) || user.role === 'worker')) requests.push(api('attendance/history/'));\n    const [main, timeOff, archive] = await Promise.all(requests);\n    setData(archive ? { ...main, history: archive.history || [], history_count: archive.count || 0 } : main);\n    setAbsences(unpack(timeOff));\n  };\n",
)
replace_once(
    'frontend/src/AttendanceV3.tsx',
    "  if (user.role === 'worker' && !mobileClockMode && typeof window !== 'undefined' && window.matchMedia('(max-width: 900px)').matches) {\n    return <Phase8MobileAttendance data={data} />;\n  }\n",
    "  if ((user.role === 'worker' || isManager(user)) && !mobileClockMode && typeof window !== 'undefined' && window.matchMedia('(max-width: 900px)').matches) {\n    return <Phase8MobileAttendance data={data} showWorker={isManager(user)} />;\n  }\n",
)

# More becomes a true app page so the WIW bottom navigation remains visible.
replace_once(
    'frontend/src/App.tsx',
    '<IonApp className="mobile-first-app-shell-v1" data-view={view}>',
    '<IonApp className="mobile-first-app-shell-v1" data-view={mobileMenuOpen ? \'more\' : view}>',
)
replace_once(
    'frontend/src/App.tsx',
    "  else if (view === 'akte') content = <AktePage user={user} />;\n\n  return (\n",
    "  else if (view === 'akte') content = <AktePage user={user} />;\n\n  if (mobileMenuOpen) {\n    content = <MobileMoreMenu user={user} items={mobileMoreItems as [string,string][]} view={view} navigate={navigateTo} onLogout={logout} />;\n  }\n\n  return (\n",
)
replace_once(
    'frontend/src/App.tsx',
    "            className={!primaryViews.includes(view) ? 'active' : ''}\n",
    "            className={mobileMenuOpen || !primaryViews.includes(view) ? 'active' : ''}\n",
)
replace_once(
    'frontend/src/App.tsx',
    "          isOpen={mobileMenuOpen}\n",
    "          isOpen={false}\n",
)

# Admin/manager gets the same WIW-style mobile information hierarchy instead of desktop cards squeezed onto mobile.
replace_once(
    'frontend/src/AdminHomeV4.tsx',
    '    <div className="admin-home-v4" data-testid="admin-exception-center">\n',
    '''    <div className="admin-home-v4" data-testid="admin-exception-center">\n      <div className="wiw-mobile-admin-dashboard" data-testid="wiw-mobile-admin-dashboard">\n        <div className="wiw-section-label">Heute</div>\n        <button type="button" className="wiw-mobile-row" onClick={() => navigate('time')}><span className="wiw-count">{byCategory.attendance || 0}</span><strong>Arbeitszeit-Hinweise</strong></button>\n        <button type="button" className="wiw-mobile-row" onClick={() => navigate('people')}><span className="wiw-row-icon"><IonIcon icon={peopleOutline}/></span><strong>Mitarbeiteraktivität</strong></button>\n\n        <div className="wiw-section-label">Anfragen</div>\n        <button type="button" className="wiw-mobile-row" onClick={() => navigate('operations')}><span className="wiw-count">{byCategory.requests || 0}</span><strong>Abwesenheitsanträge</strong></button>\n        <button type="button" className="wiw-mobile-row" onClick={() => navigate('operations')}><span className="wiw-count">{byCategory.staffing || 0}</span><strong>Schichtanfragen</strong></button>\n        <button type="button" className="wiw-mobile-row" onClick={() => navigate('schedule')}><span className="wiw-count">{byCategory.staffing || 0}</span><strong>OpenShift-Anfragen</strong></button>\n\n        <div className="wiw-section-label">Dienstplan</div>\n        <button type="button" className="wiw-next-shift" onClick={() => navigate('schedule')}><small>Nächster Einsatz:</small><strong>Dienstplan öffnen</strong></button>\n        <button type="button" className="wiw-mobile-row" onClick={() => navigate('schedule')}><span className="wiw-row-icon"><IonIcon icon={calendarOutline}/></span><strong>Schichten</strong></button>\n        <button type="button" className="wiw-mobile-row" onClick={() => navigate('schedule')}><span className="wiw-count">{byCategory.staffing || 0}</span><strong>OpenShifts verfügbar</strong></button>\n\n        <div className="wiw-section-label">Wichtige anstehende Termine</div>\n        <div className="wiw-upcoming"><div>{(criticalFirst[0] || results[0]) ? <><strong>{(criticalFirst[0] || results[0]).title}</strong><span>{(criticalFirst[0] || results[0]).message}</span></> : <span>Keine offenen Vorgänge</span>}</div>{(criticalFirst[0] || results[0]) && <button type="button" onClick={() => open(criticalFirst[0] || results[0])}>Öffnen</button>}</div>\n      </div>\n''',
)

# Make role visible in pay-period detail when an admin views the archive.
replace_once(
    'frontend/src/Phase8MobileAttendance.tsx',
    "export default function Phase8MobileAttendance({data}:{data:any}){",
    "export default function Phase8MobileAttendance({data,showWorker=false}:{data:any;showWorker?:boolean}){",
)
replace_once(
    'frontend/src/Phase8MobileAttendance.tsx',
    "<div><strong>{fmtDate(entry.clock_in)}</strong><span>{fmtTime(entry.clock_in)} – {entry.clock_out?fmtTime(entry.clock_out):'läuft'}</span><small>{entry.shift_title||'Arbeitszeit'}</small></div>",
    "<div><strong>{showWorker && entry.worker_name ? `${entry.worker_name} · ` : ''}{fmtDate(entry.clock_in)}</strong><span>{fmtTime(entry.clock_in)} – {entry.clock_out?fmtTime(entry.clock_out):'läuft'}</span><small>{entry.shift_title||'Arbeitszeit'}</small></div>",
)

# More/dashboard appbar behavior and admin mobile switch.
p = Path('frontend/src/wiw-mobile-light.css')
css = p.read_text(encoding='utf-8')
css += '''\n@media(max-width:900px){\n  .wiw-mobile-admin-dashboard{display:block;background:var(--wiw-bg);color:var(--wiw-copy);min-height:calc(100dvh - 126px)}\n  .admin-home-v4>.wiw-mobile-admin-dashboard~*{display:none!important}\n  .mobile-first-app-shell-v1[data-view='more'] .mobile-appbar{display:none!important}\n  .mobile-first-app-shell-v1[data-view='more'] .app{padding-top:0!important}\n  .mobile-first-app-shell-v1[data-view='more'] .global-search{display:none!important}\n}\n@media(min-width:901px){.wiw-mobile-admin-dashboard{display:none!important}}\n'''
p.write_text(css, encoding='utf-8')

# Robust browser guard for appearance helper.
p = Path('frontend/src/mobileAppearance.ts')
text = p.read_text(encoding='utf-8')
text = text.replace("  if (typeof window !== 'undefined') window.localStorage.setItem(STORAGE_KEY, next);\n  window.dispatchEvent(new CustomEvent('aplus-appearance-change', { detail: next }));", "  if (typeof window !== 'undefined') {\n    window.localStorage.setItem(STORAGE_KEY, next);\n    window.dispatchEvent(new CustomEvent('aplus-appearance-change', { detail: next }));\n  }")
p.write_text(text, encoding='utf-8')
''