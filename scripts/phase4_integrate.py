from pathlib import Path
import re

backend = Path('backend/core/admin_center_views.py')
source = backend.read_text(encoding='utf-8')
staffing_block = '''    # Staffing demand: published/confirmed future shifts with open capacity.
    staffing = list(
        Shift.objects.filter(
            status__in=[Shift.Status.PUBLISHED, Shift.Status.CONFIRMED],
            ends_at__gte=now,
        ).select_related('client', 'location', 'position').annotate(
            slot_open_count=Count(
                'slots',
                filter=Q(slots__status=ShiftSlot.Status.OPEN, slots__worker__isnull=True),
                distinct=True,
            ),
            slot_filled_count=Count(
                'slots',
                filter=Q(slots__status=ShiftSlot.Status.CLAIMED, slots__worker__isnull=False),
                distinct=True,
            ),
        ).order_by('starts_at')[:120]
    )
    for shift in staffing:
        legacy_filled = 1 if shift.worker_id and shift.slot_filled_count == 0 else 0
        effective_filled = min(shift.required_count, shift.slot_filled_count + legacy_filled)
        effective_open = max(0, shift.required_count - effective_filled)
        if not effective_open:
            continue
        hours_until = (shift.starts_at - now).total_seconds() / 3600
        severity = 'critical' if hours_until <= 24 else 'warning'
        items.append(_exception(
            'staffing',
            severity,
            f'{effective_open} Platz/Plätze noch offen',
            f'{shift.position.name} · {shift.client.name} · {shift.location.name}',
            'schedule',
            shift.id,
            due_at=shift.starts_at,
            meta={
                'open_count': effective_open,
                'filled_count': effective_filled,
                'required_count': shift.required_count,
                'starts_at': shift.starts_at,
            },
        ))

    # Attendance:'''
source, count = re.subn(
    r"    # Staffing demand: published/confirmed future shifts with open capacity\..*?\n    # Attendance:",
    staffing_block,
    source,
    count=1,
    flags=re.S,
)
if count != 1:
    raise SystemExit('Staffing exception block marker not found')

late_marker = '''    for correction in TimeEntryCorrection.objects.filter(
'''
legacy_late = '''    # Legacy directly-assigned shifts remain visible during the transition even if a claimed slot is missing.
    late_legacy = Shift.objects.filter(
        worker__isnull=False,
        status__in=[Shift.Status.PUBLISHED, Shift.Status.CONFIRMED],
        starts_at__lte=now - timedelta(minutes=15),
        ends_at__gte=now - timedelta(hours=12),
    ).exclude(
        slots__status=ShiftSlot.Status.CLAIMED,
        slots__worker__isnull=False,
    ).select_related('worker__user', 'client', 'location', 'position').distinct().order_by('-starts_at')[:80]
    legacy_pairs = set(
        TimeEntry.objects.filter(shift_id__in=[shift.id for shift in late_legacy]).values_list('shift_id', 'worker_id')
    )
    for shift in late_legacy:
        if (shift.id, shift.worker_id) in legacy_pairs:
            continue
        minutes_late = max(15, int((now - shift.starts_at).total_seconds() // 60))
        items.append(_exception(
            'attendance',
            'critical' if minutes_late >= 60 else 'warning',
            'Kein Check-in erfasst',
            f'{shift.worker.user.get_full_name() or shift.worker.user.email} · {shift.position.name} · seit {minutes_late} Min.',
            'time',
            shift.id,
            due_at=shift.starts_at,
            meta={
                'worker_id': str(shift.worker_id),
                'worker_name': shift.worker.user.get_full_name() or shift.worker.user.email,
                'minutes_late': minutes_late,
                'location': shift.location.name,
                'legacy_assignment': True,
            },
        ))

'''
if legacy_late not in source:
    if late_marker not in source:
        raise SystemExit('Late legacy insertion marker not found')
    source = source.replace(late_marker, legacy_late + late_marker, 1)
source = source.replace("    seen_contract_actions = set()\n", '', 1)
source = source.replace("            seen_contract_actions.add(contract.id)\n", '', 1)
source = source.replace(
    "    workers = WorkerProfile.objects.filter(active=True).select_related('user').order_by('user__last_name')[:250]\n",
    "    workers = list(WorkerProfile.objects.filter(active=True).select_related('user').order_by('user__last_name')[:250])\n",
    1,
)
backend.write_text(source, encoding='utf-8')

app = Path('frontend/src/App.tsx')
text = app.read_text(encoding='utf-8')
import_marker = "import PortalAccessPanel from './PortalAccessPanel';\n"
imports = "import AdminHomeV4 from './AdminHomeV4';\nimport GlobalSearch from './GlobalSearch';\nimport ListToolbar from './ListToolbar';\n"
if "import AdminHomeV4" not in text:
    if import_marker not in text:
        raise SystemExit('App import marker not found')
    text = text.replace(import_marker, import_marker + imports, 1)

old_default = "  let content: React.ReactNode = user.role === 'worker' ? <EmployeeHome user={user} navigate={navigateTo} /> : <Dashboard user={user} navigate={navigateTo} />;"
new_default = "  let content: React.ReactNode = user.role === 'worker' ? <EmployeeHome user={user} navigate={navigateTo} /> : isManager(user) ? <AdminHomeV4 navigate={navigateTo} /> : <Dashboard user={user} navigate={navigateTo} />;"
if new_default not in text:
    if old_default not in text:
        raise SystemExit('Default dashboard routing marker not found')
    text = text.replace(old_default, new_default, 1)
old_main = '            <main className="app-main">{content}</main>'
new_main = '            <main className="app-main">{isManager(user) && <GlobalSearch onNavigate={navigateTo} />}{content}</main>'
if new_main not in text:
    if old_main not in text:
        raise SystemExit('App main marker not found')
    text = text.replace(old_main, new_main, 1)

def section(source_text, start, end):
    a = source_text.index(start)
    b = source_text.index(end, a)
    return a, b, source_text[a:b]

def replace_section(source_text, start, end, updater):
    a, b, chunk = section(source_text, start, end)
    return source_text[:a] + updater(chunk) + source_text[b:]

def must_replace(chunk, old, new, label):
    if new in chunk:
        return chunk
    if old not in chunk:
        raise SystemExit(f'{label} marker not found')
    return chunk.replace(old, new, 1)

def patch_people(chunk):
    chunk = must_replace(chunk, "  const [csvType, setCsvType] = useState('workers');\n", "  const [csvType, setCsvType] = useState('workers');\n  const [listQuery, setListQuery] = useState('');\n  const [listSort, setListSort] = useState('name');\n", 'People state')
    old = '''  const load = async () => {
    const [workerData, clientData, locationData, positionData] = await Promise.all([
      api('workers/'),
      api('clients/'),
      api('locations/'),
      api('positions/'),
    ]);
    setWorkers(unpack(workerData));
    setClients(unpack(clientData));
    setLocations(unpack(locationData));
    setPositions(unpack(positionData));
  };

  useEffect(() => {
    void load();
  }, []);
'''
    new = '''  const load = async () => {
    const search = listQuery.trim() ? `&search=${encodeURIComponent(listQuery.trim())}` : '';
    const workerOrdering = listSort === 'number' ? 'employee_number' : 'user__last_name';
    const clientOrdering = listSort === 'number' ? 'customer_number' : 'name';
    const [workerData, clientData, locationData, positionData] = await Promise.all([
      api(`workers/?ordering=${workerOrdering}${search}`),
      api(`clients/?ordering=${clientOrdering}${search}`),
      api('locations/'),
      api('positions/'),
    ]);
    setWorkers(unpack(workerData));
    setClients(unpack(clientData));
    setLocations(unpack(locationData));
    setPositions(unpack(positionData));
  };

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), listQuery ? 250 : 0);
    return () => window.clearTimeout(timer);
  }, [listQuery, listSort]);
'''
    chunk = must_replace(chunk, old, new, 'People load')
    marker = "      {isManager(user) && <PortalAccessPanel />}\n\n      <div className=\"columns\">"
    toolbar = '''      {isManager(user) && <PortalAccessPanel />}

      <ListToolbar
        query={listQuery}
        onQuery={setListQuery}
        placeholder="Mitarbeiter oder Kunden suchen …"
        sort={listSort}
        onSort={setListSort}
        sortOptions={[{ value: 'name', label: 'Nach Name' }, { value: 'number', label: 'Nach Nummer' }]}
        count={workers.length + clients.length}
      />

      <div className="columns">'''
    return must_replace(chunk, marker, toolbar, 'People toolbar')

text = replace_section(text, 'function People(', 'function Schedule(', patch_people)

def patch_contracts(chunk):
    chunk = must_replace(chunk, "  const [toast, setToast] = useState('');\n", "  const [toast, setToast] = useState('');\n  const [listQuery, setListQuery] = useState('');\n  const [listStatus, setListStatus] = useState('');\n  const [listSort, setListSort] = useState('-updated_at');\n", 'Contracts state')
    old = '''  const load = async () => {
    const contractData = await api('contracts/');
    setRows(unpack(contractData));
    if (isManager(user)) {
      const [templateData, workerData, clientData] = await Promise.all([
        api('contract-templates/'),
        api('workers/'),
        api('clients/'),
      ]);
      setTemplates(unpack(templateData).filter((template: any) => template.active));
      setWorkers(unpack(workerData).filter((worker: any) => worker.active));
      setClients(unpack(clientData).filter((client: any) => client.active));
    }
  };

  useEffect(() => {
    void load();
  }, []);
'''
    new = '''  const load = async () => {
    const params = new URLSearchParams();
    if (listQuery.trim()) params.set('search', listQuery.trim());
    if (listStatus) params.set('status', listStatus);
    params.set('ordering', listSort);
    const contractData = await api(`contracts/?${params.toString()}`);
    setRows(unpack(contractData));
    if (isManager(user)) {
      const [templateData, workerData, clientData] = await Promise.all([
        api('contract-templates/'),
        api('workers/?ordering=user__last_name'),
        api('clients/?ordering=name'),
      ]);
      setTemplates(unpack(templateData).filter((template: any) => template.active));
      setWorkers(unpack(workerData).filter((worker: any) => worker.active));
      setClients(unpack(clientData).filter((client: any) => client.active));
    }
  };

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), listQuery ? 250 : 0);
    return () => window.clearTimeout(timer);
  }, [listQuery, listStatus, listSort]);
'''
    chunk = must_replace(chunk, old, new, 'Contracts load')
    marker = '''      <div className="panel">
        {rows.map((contract) => ('''
    toolbar = '''      <ListToolbar
        query={listQuery}
        onQuery={setListQuery}
        placeholder="Vertrag, Mitarbeiter oder Kunde suchen …"
        status={listStatus}
        onStatus={setListStatus}
        statusOptions={[{ value: 'draft', label: 'Entwurf' }, { value: 'ready', label: 'Prüfbereit' }, { value: 'sent', label: 'Versendet' }, { value: 'signed', label: 'Unterzeichnet' }, { value: 'expired', label: 'Abgelaufen' }, { value: 'cancelled', label: 'Storniert' }]}
        sort={listSort}
        onSort={setListSort}
        sortOptions={[{ value: '-updated_at', label: 'Zuletzt geändert' }, { value: 'ends_on', label: 'Vertragsende zuerst' }, { value: '-created_at', label: 'Neueste zuerst' }]}
        count={rows.length}
      />
      <div className="panel">
        {rows.map((contract) => ('''
    return must_replace(chunk, marker, toolbar, 'Contracts toolbar')

text = replace_section(text, 'function Contracts(', 'function Documents(', patch_contracts)

def patch_documents(chunk):
    chunk = must_replace(chunk, "  const [toast, setToast] = useState('');\n", "  const [toast, setToast] = useState('');\n  const [listQuery, setListQuery] = useState('');\n  const [listFolder, setListFolder] = useState('');\n  const [listSort, setListSort] = useState('-created_at');\n", 'Documents state')
    old = '''  const load = async () => {
    const [documentData, payrollData] = await Promise.all([api('documents/'), api('payroll/')]);
    setRows(unpack(documentData));
    setPayroll(unpack(payrollData));
    if (isManager(user)) {
      const [workerData, clientData] = await Promise.all([api('workers/'), api('clients/')]);
      setWorkers(unpack(workerData).filter((worker: any) => worker.active));
      setClients(unpack(clientData).filter((client: any) => client.active));
    }
  };

  useEffect(() => {
    void load();
  }, []);
'''
    new = '''  const load = async () => {
    const params = new URLSearchParams();
    if (listQuery.trim()) params.set('search', listQuery.trim());
    if (listFolder) params.set('folder', listFolder);
    params.set('ordering', listSort);
    const [documentData, payrollData] = await Promise.all([api(`documents/?${params.toString()}`), api('payroll/')]);
    setRows(unpack(documentData));
    setPayroll(unpack(payrollData));
    if (isManager(user)) {
      const [workerData, clientData] = await Promise.all([api('workers/?ordering=user__last_name'), api('clients/?ordering=name')]);
      setWorkers(unpack(workerData).filter((worker: any) => worker.active));
      setClients(unpack(clientData).filter((client: any) => client.active));
    }
  };

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), listQuery ? 250 : 0);
    return () => window.clearTimeout(timer);
  }, [listQuery, listFolder, listSort]);
'''
    chunk = must_replace(chunk, old, new, 'Documents load')
    marker = '''      <div className="columns">
        <div className="panel">
          <h3>Dokumente</h3>'''
    toolbar = '''      <ListToolbar
        query={listQuery}
        onQuery={setListQuery}
        placeholder="Dokument, Mitarbeiter oder Kunde suchen …"
        status={listFolder}
        onStatus={setListFolder}
        statusOptions={[{ value: 'general', label: 'Allgemein' }, { value: 'contracts', label: 'Verträge' }, { value: 'payroll', label: 'Lohnabrechnungen' }, { value: 'certificates', label: 'Nachweise' }, { value: 'orders', label: 'Aufträge' }]}
        sort={listSort}
        onSort={setListSort}
        sortOptions={[{ value: '-created_at', label: 'Neueste zuerst' }, { value: 'title', label: 'Titel A–Z' }, { value: 'folder', label: 'Nach Ordner' }]}
        count={rows.length}
      />
      <div className="columns">
        <div className="panel">
          <h3>Dokumente</h3>'''
    return must_replace(chunk, marker, toolbar, 'Documents toolbar')

text = replace_section(text, 'function Documents(', 'function Orders(', patch_documents)

def patch_orders(chunk):
    chunk = must_replace(chunk, "  const [toast, setToast] = useState('');\n", "  const [toast, setToast] = useState('');\n  const [listQuery, setListQuery] = useState('');\n  const [listStatus, setListStatus] = useState('');\n  const [listSort, setListSort] = useState('-starts_at');\n", 'Orders state')
    old = '''  const load = async () => {
    const orderData = await api('orders/');
    setRows(unpack(orderData));
    if (isManager(user)) {
      const [clientData, locationData] = await Promise.all([api('clients/'), api('locations/')]);
      setClients(unpack(clientData).filter((client: any) => client.active));
      setLocations(unpack(locationData).filter((location: any) => location.active));
    }
  };

  useEffect(() => {
    void load();
  }, []);
'''
    new = '''  const load = async () => {
    const params = new URLSearchParams();
    if (listQuery.trim()) params.set('search', listQuery.trim());
    if (listStatus) params.set('status', listStatus);
    params.set('ordering', listSort);
    const orderData = await api(`orders/?${params.toString()}`);
    setRows(unpack(orderData));
    if (isManager(user)) {
      const [clientData, locationData] = await Promise.all([api('clients/?ordering=name'), api('locations/')]);
      setClients(unpack(clientData).filter((client: any) => client.active));
      setLocations(unpack(locationData).filter((location: any) => location.active));
    }
  };

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), listQuery ? 250 : 0);
    return () => window.clearTimeout(timer);
  }, [listQuery, listStatus, listSort]);
'''
    chunk = must_replace(chunk, old, new, 'Orders load')
    marker = '''      <div className="panel">
        {rows.map((order) => ('''
    toolbar = '''      <ListToolbar
        query={listQuery}
        onQuery={setListQuery}
        placeholder="Auftrag, Kunde oder Einsatzort suchen …"
        status={listStatus}
        onStatus={setListStatus}
        statusOptions={[{ value: 'new', label: 'Neu' }, { value: 'planning', label: 'In Planung' }, { value: 'confirmed', label: 'Bestätigt' }, { value: 'done', label: 'Abgeschlossen' }, { value: 'cancelled', label: 'Storniert' }]}
        sort={listSort}
        onSort={setListSort}
        sortOptions={[{ value: '-starts_at', label: 'Neueste Einsätze' }, { value: 'starts_at', label: 'Nächste Einsätze' }, { value: '-created_at', label: 'Zuletzt angelegt' }, { value: '-requested_staff', label: 'Größter Bedarf' }]}
        count={rows.length}
      />
      <div className="panel">
        {rows.map((order) => ('''
    return must_replace(chunk, marker, toolbar, 'Orders toolbar')

text = replace_section(text, 'function Orders(', 'function Messages(', patch_orders)
app.write_text(text, encoding='utf-8')
