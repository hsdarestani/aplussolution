from pathlib import Path


def replace_once(path, old, new):
    file = Path(path)
    text = file.read_text(encoding='utf-8')
    if old not in text:
        raise SystemExit(f'Patch target not found in {path}: {old[:100]!r}')
    file.write_text(text.replace(old, new, 1), encoding='utf-8')


# Integrate the standalone operations center into the existing single-file application.
replace_once(
    'frontend/src/App.tsx',
    "import { api, consumeOAuth, login, logout, me, socialUrl, User } from './api';",
    "import { api, consumeOAuth, login, logout, me, socialUrl, User } from './api';\nimport Operations from './Operations';",
)
replace_once(
    'frontend/src/App.tsx',
    "  | 'profile';",
    "  | 'profile'\n  | 'operations';",
)
replace_once(
    'frontend/src/App.tsx',
    "  profile: peopleOutline,\n};",
    "  profile: peopleOutline,\n  operations: refreshOutline,\n};",
)
replace_once(
    'frontend/src/App.tsx',
    "    ['messages', 'Nachrichten'],\n  ],\n  manager:",
    "    ['messages', 'Nachrichten'],\n    ['operations', 'Steuerzentrale'],\n  ],\n  manager:",
)
replace_once(
    'frontend/src/App.tsx',
    "    ['messages', 'Nachrichten'],\n  ],\n  worker:",
    "    ['messages', 'Nachrichten'],\n    ['operations', 'Steuerzentrale'],\n  ],\n  worker:",
)
replace_once(
    'frontend/src/App.tsx',
    "    ['time', 'Arbeitszeitkonto'],\n    ['contracts', 'Meine Verträge'],",
    "    ['time', 'Arbeitszeitkonto'],\n    ['operations', 'Verfügbarkeit & Tausch'],\n    ['contracts', 'Meine Verträge'],",
)
replace_once(
    'frontend/src/App.tsx',
    "    ['dashboard', 'Start'],\n    ['orders', 'Aufträge'],",
    "    ['dashboard', 'Start'],\n    ['operations', 'Servicecenter'],\n    ['orders', 'Aufträge'],",
)
replace_once(
    'frontend/src/App.tsx',
    "  else if (view === 'profile') content = <Profile user={user} />;",
    "  else if (view === 'profile') content = <Profile user={user} />;\n  else if (view === 'operations') content = <Operations user={user} />;",
)

# Harden scheduling against overlaps and explicit unavailability.
replace_once(
    'backend/core/views.py',
    """    def assign(self, request, pk=None):
        shift = self.get_object()
        worker_id = request.data.get('worker')
        shift.worker = WorkerProfile.objects.get(pk=worker_id) if worker_id else None
        shift.is_open = not bool(worker_id)
        shift.status = Shift.Status.CONFIRMED if worker_id else Shift.Status.PUBLISHED
        shift.save()
        audit(request, 'shift.assigned', shift, {'worker': worker_id})
        return Response(self.get_serializer(shift).data)
""",
    """    def assign(self, request, pk=None):
        shift = self.get_object()
        worker_id = request.data.get('worker')
        worker = WorkerProfile.objects.get(pk=worker_id, active=True) if worker_id else None
        if worker:
            if Shift.objects.filter(
                worker=worker,
                starts_at__lt=shift.ends_at,
                ends_at__gt=shift.starts_at,
            ).exclude(pk=shift.pk).exclude(status=Shift.Status.CANCELLED).exists():
                return Response({'detail': 'Der Mitarbeiter hat in diesem Zeitraum bereits eine Schicht.'}, status=400)
            if Availability.objects.filter(
                worker=worker,
                available=False,
                starts_at__lt=shift.ends_at,
                ends_at__gt=shift.starts_at,
            ).exists():
                return Response({'detail': 'Der Mitarbeiter ist in diesem Zeitraum nicht verfügbar.'}, status=400)
        shift.worker = worker
        shift.is_open = not bool(worker)
        shift.status = Shift.Status.CONFIRMED if worker else Shift.Status.PUBLISHED
        shift.save()
        if worker:
            Notification.objects.create(
                user=worker.user,
                kind=f'shift-assigned-{shift.id}',
                title='Neue Schicht zugeteilt',
                body=f'{shift.starts_at:%d.%m.%Y %H:%M} – {shift.location.name}',
                action_url='/schedule',
            )
        audit(request, 'shift.assigned', shift, {'worker': worker_id})
        return Response(self.get_serializer(shift).data)
""",
)
replace_once(
    'backend/core/views.py',
    """        shift.worker = request.user.worker_profile
        shift.is_open = False
        shift.status = Shift.Status.CONFIRMED
        shift.save()
        audit(request, 'shift.claimed', shift)
        return Response(self.get_serializer(shift).data)
""",
    """        worker = request.user.worker_profile
        if Shift.objects.filter(
            worker=worker,
            starts_at__lt=shift.ends_at,
            ends_at__gt=shift.starts_at,
        ).exclude(pk=shift.pk).exclude(status=Shift.Status.CANCELLED).exists():
            return Response({'detail': 'Du hast in diesem Zeitraum bereits eine Schicht.'}, status=400)
        if Availability.objects.filter(
            worker=worker,
            available=False,
            starts_at__lt=shift.ends_at,
            ends_at__gt=shift.starts_at,
        ).exists():
            return Response({'detail': 'Du bist für diesen Zeitraum als nicht verfügbar eingetragen.'}, status=400)
        shift.worker = worker
        shift.is_open = False
        shift.status = Shift.Status.CONFIRMED
        shift.save()
        audit(request, 'shift.claimed', shift)
        return Response(self.get_serializer(shift).data)
""",
)

# Notify relevant portals immediately when a contract is sent.
replace_once(
    'backend/core/views.py',
    """        contract.status = Contract.Status.SENT
        contract.sent_at = timezone.now()
        contract.save()
        audit(request, 'contract.sent', contract)
        return Response(self.get_serializer(contract).data)
""",
    """        contract.status = Contract.Status.SENT
        contract.sent_at = timezone.now()
        contract.save()
        recipients = list(User.objects.filter(role__in=['admin', 'manager'], is_active=True))
        if contract.worker_id:
            recipients.append(contract.worker.user)
        if contract.client_id:
            recipients.extend(contract.client.contacts.filter(is_active=True))
        for recipient in {item.pk: item for item in recipients}.values():
            Notification.objects.create(
                user=recipient,
                kind=f'contract-sent-{contract.id}',
                title='Vertrag zur Prüfung bereit',
                body=contract.title,
                action_url='/contracts',
            )
        audit(request, 'contract.sent', contract)
        return Response(self.get_serializer(contract).data)
""",
)

# Notify conversation participants and maintain read receipts.
replace_once(
    'backend/core/views.py',
    """        message = Message.objects.create(conversation=conversation, sender=request.user, body=body)
        return Response(MessageSerializer(message, context={'request': request}).data, status=201)
""",
    """        message = Message.objects.create(conversation=conversation, sender=request.user, body=body)
        message.read_by.add(request.user)
        for participant in conversation.participants.exclude(pk=request.user.pk):
            Notification.objects.create(
                user=participant,
                kind=f'message-{message.id}',
                title=conversation.title or 'Neue Nachricht',
                body=body[:180],
                action_url='/messages',
            )
        return Response(MessageSerializer(message, context={'request': request}).data, status=201)
""",
)

# Scope client coverage and expose worker swap metadata.
replace_once(
    'backend/core/advanced_views.py',
    """                'order': str(order.id),
                'title': order.title,
                'client_name': order.client.name,
""",
    """                'order': str(order.id),
                'client': str(order.client_id),
                'title': order.title,
                'client_name': order.client.name,
""",
)
replace_once(
    'backend/core/advanced_views.py',
    """            'pending_swaps': ShiftSwapRequest.objects.filter(status=ShiftSwapRequest.Status.PENDING).count(),
            'pending_time_off': TimeOffRequest.objects.filter(status=TimeOffRequest.Status.PENDING).count(),
""",
    """            'pending_swaps': ShiftSwapRequest.objects.filter(status=ShiftSwapRequest.Status.PENDING).count(),
            'swaps': [
                _serialize_swap(item)
                for item in ShiftSwapRequest.objects.select_related(
                    'shift__position', 'requested_by__user', 'offered_to__user'
                ).order_by('-created_at')[:50]
            ],
            'swap_candidates': [
                {'id': str(worker.id), 'name': worker.user.get_full_name() or worker.user.email}
                for worker in WorkerProfile.objects.filter(active=True).select_related('user').order_by('user__first_name')
            ],
            'pending_time_off': TimeOffRequest.objects.filter(status=TimeOffRequest.Status.PENDING).count(),
""",
)
replace_once(
    'backend/core/advanced_views.py',
    """        data.update({
            'availabilities': AvailabilitySerializer(
""",
    """        data.update({
            'current_worker_id': str(worker.id),
            'swap_candidates': [
                {'id': str(candidate.id), 'name': candidate.user.get_full_name() or candidate.user.email}
                for candidate in WorkerProfile.objects.filter(active=True).exclude(pk=worker.pk).select_related('user').order_by('user__first_name')
            ],
            'availabilities': AvailabilitySerializer(
""",
)
replace_once(
    'backend/core/advanced_views.py',
    """        companies = user.client_companies.all()
        data.update({
            'coverage_gaps': _schedule_findings()['coverage_gaps'],
""",
    """        companies = user.client_companies.all()
        company_ids = {str(pk) for pk in companies.values_list('pk', flat=True)}
        client_findings = _schedule_findings()['coverage_gaps']
        data.update({
            'coverage_gaps': [item for item in client_findings if item.get('client') in company_ids],
""",
)
replace_once(
    'backend/core/advanced_views.py',
    """    decision = str(request.data.get('status', '')).lower()
    user = request.user
""",
    """    decision = str(request.data.get('status', '')).lower()
    user = request.user
    if _is_manager(user) and request.data.get('offered_to'):
        try:
            obj.offered_to = WorkerProfile.objects.get(pk=request.data.get('offered_to'), active=True)
            obj.save(update_fields=['offered_to'])
        except WorkerProfile.DoesNotExist:
            return Response({'detail': 'Zielmitarbeiter wurde nicht gefunden.'}, status=404)
""",
)

# Correct worker-side swap action visibility and add manager approval UI.
replace_once(
    'frontend/src/Operations.tsx',
    "  const [templateFile, setTemplateFile] = useState<File>();",
    "  const [templateFile, setTemplateFile] = useState<File>();\n  const [swapTargets, setSwapTargets] = useState<Record<string, string>>({});",
)
replace_once(
    'frontend/src/Operations.tsx',
    """          <div className="operations-grid two">
            <section className="operations-panel">
              <div className="operations-head"><div><h3>Planungswerkzeuge</h3><p>Woche kopieren und Entwürfe gesammelt veröffentlichen.</p></div><IonIcon icon={calendarOutline} /></div>
""",
    """          <div className="operations-grid two">
            <section className="operations-panel">
              <div className="operations-head"><div><h3>Schichttausch freigeben</h3><p>Offene Anfragen prüfen und Zielmitarbeiter festlegen.</p></div><IonIcon icon={swapHorizontalOutline} /></div>
              {data.swaps?.filter((item: any) => item.status === 'pending').map((item: any) => (
                <div className="operations-row" key={item.id}>
                  <IonIcon icon={swapHorizontalOutline} />
                  <div className="operations-grow"><b>{item.requested_by_name} · {item.shift_title}</b><p>{dateTime(item.shift_starts_at)}</p><small>{item.note}</small></div>
                  <IonSelect className="swap-target" interface="popover" placeholder="Ziel" value={swapTargets[item.id] || item.offered_to || ''} onIonChange={(event) => setSwapTargets({ ...swapTargets, [item.id]: String(value(event)) })}>
                    {data.swap_candidates?.filter((candidate: any) => candidate.id !== item.requested_by).map((candidate: any) => <IonSelectOption value={candidate.id} key={candidate.id}>{candidate.name}</IonSelectOption>)}
                  </IonSelect>
                  <IonButton size="small" color="success" disabled={!swapTargets[item.id] && !item.offered_to} onClick={() => run(`operations/swaps/${item.id}/decide/`, { status: 'approved', offered_to: swapTargets[item.id] || item.offered_to }, 'Tausch wurde freigegeben.')}>Freigeben</IonButton>
                  <IonButton size="small" color="danger" onClick={() => decideSwap(item.id, 'rejected')}>Ablehnen</IonButton>
                </div>
              ))}
              {!data.swaps?.some((item: any) => item.status === 'pending') && <Empty>Keine offenen Tauschanfragen.</Empty>}
            </section>
            <section className="operations-panel">
              <div className="operations-head"><div><h3>Planungswerkzeuge</h3><p>Woche kopieren und Entwürfe gesammelt veröffentlichen.</p></div><IonIcon icon={calendarOutline} /></div>
""",
)
replace_once(
    'frontend/src/Operations.tsx',
    "item.status === 'pending' && item.requested_by === user.worker_profile_id",
    "item.status === 'pending' && item.requested_by === data.current_worker_id",
)
replace_once(
    'frontend/src/Operations.tsx',
    "item.status === 'pending' && item.offered_to_name &&",
    "item.status === 'pending' && item.offered_to === data.current_worker_id &&",
)

# Add a small style for manager swap target selector.
css = Path('frontend/src/operations.css')
css.write_text(css.read_text(encoding='utf-8') + "\n.swap-target { min-width: 150px; border: 1px solid var(--line); border-radius: 10px; padding-inline: 8px; }\n", encoding='utf-8')

print('Workforce completion integration patches applied.')
