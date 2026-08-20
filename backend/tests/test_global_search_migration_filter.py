import pytest

from core.models import Contract, ContractTemplate, User, WorkerProfile


@pytest.mark.django_db
def test_global_search_filters_migration_only_workers_before_limit(auth_admin, worker_user):
    for index in range(5):
        user = User.objects.create_user(
            f'anna-migration-{index}@sync.invalid',
            'StrongPass123!',
            first_name='Anna',
            last_name=f'Aaa Migration {index}',
            role=User.Role.WORKER,
            is_onboarded=True,
        )
        WorkerProfile.objects.create(
            user=user,
            employee_number=f'MIG-{index:03d}',
            employment_type='minijob',
            monthly_hours='38.90',
            tariff_hourly_rate='14.50',
        )

    response = auth_admin.get('/api/search/global/?q=Anna&limit=3')
    assert response.status_code == 200

    workers = response.data['groups']['workers']
    assert any(item['id'] == str(worker_user.worker_profile.id) for item in workers)
    assert all('@sync.invalid' not in item['subtitle'].lower() for item in workers)
    assert all('@sync.invalid' not in item['subtitle'].lower() for item in response.data['results'])


@pytest.mark.django_db
def test_global_search_hides_contracts_for_migration_only_workers(auth_admin, admin_user):
    user = User.objects.create_user(
        'legacy-worker@sync.invalid',
        'StrongPass123!',
        first_name='Legacy',
        last_name='Migration',
        role=User.Role.WORKER,
        is_onboarded=False,
    )
    worker = WorkerProfile.objects.create(
        user=user,
        employee_number='MIG-CONTRACT',
        employment_type='minijob',
        monthly_hours='38.90',
        tariff_hourly_rate='14.50',
    )
    template = ContractTemplate.objects.create(
        name='Migration Search Template',
        slug='migration-search-template',
        kind=ContractTemplate.Kind.EMPLOYMENT,
        schema={},
    )
    contract = Contract.objects.create(
        template=template,
        worker=worker,
        title='Migration Search Contract',
        status=Contract.Status.READY,
        created_by=admin_user,
    )

    response = auth_admin.get('/api/search/global/?q=Migration&limit=10')
    assert response.status_code == 200
    assert all(item['id'] != str(contract.id) for item in response.data['results'])
    assert all('@sync.invalid' not in item['subtitle'].lower() for item in response.data['results'])
