import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from core.models import User, WorkerProfile
from core.payroll_views import _employee_matchers, _find_worker


ALIASES = [
    ("Fatemeh Bagheri Hosseinabadi", "Shahrzad", "Bagheri"),
    ("Julius Philipp Degen", "Julius", "Degen"),
    ("Mohammad Musa Jamali", "Musa", "Jamali"),
    ("Aikaterini Gentsou", "Katerina", "Gentsou"),
    ("Ashkan Asadian Ghaferokhi", "Ashkan", "Asadian"),
]


def _create_alias_workers():
    rows = []
    for index, (lexware_name, first_name, last_name) in enumerate(ALIASES, start=1):
        user = User.objects.create_user(
            f"lexware-alias-{index}@example.com",
            "StrongPass123!",
            first_name=first_name,
            last_name=last_name,
            role=User.Role.WORKER,
        )
        worker = WorkerProfile.objects.create(
            user=user,
            employee_number=f"ALIAS-{index:02d}",
            active=True,
        )
        rows.append((lexware_name, worker))
    return rows


@pytest.mark.django_db
def test_confirmed_lexware_aliases_match_master_data_import(auth_admin):
    rows = _create_alias_workers()
    upload = SimpleUploadedFile(
        "lexware-stammdaten.json",
        json.dumps({
            "employees": [
                {
                    "name": lexware_name,
                    "data": {
                        "compensation_type": "salary",
                        "monthly_salary": str(2000 + index),
                        "alias_test_marker": f"matched-{index}",
                    },
                }
                for index, (lexware_name, _worker) in enumerate(rows, start=1)
            ],
        }).encode("utf-8"),
        content_type="application/json",
    )

    response = auth_admin.post(
        "/api/workers/master-data/import/",
        {"file": upload},
        format="multipart",
    )

    assert response.status_code == 200
    assert response.data["unmatched"] == []
    assert len(response.data["employees"]) == len(ALIASES)

    imported_ids = {row["worker_id"] for row in response.data["employees"]}
    for index, (_lexware_name, worker) in enumerate(rows, start=1):
        worker.refresh_from_db()
        assert str(worker.id) in imported_ids
        assert worker.master_data.data["alias_test_marker"] == f"matched-{index}"


@pytest.mark.django_db
def test_confirmed_lexware_aliases_match_payroll_evidence():
    rows = _create_alias_workers()
    matchers = _employee_matchers()

    for lexware_name, worker in rows:
        matched = _find_worker({"employee_name": lexware_name}, matchers)
        assert matched is not None
        assert matched.id == worker.id


@pytest.mark.django_db
def test_lexware_sharp_s_name_matches_ascii_app_name(auth_admin):
    user = User.objects.create_user(
        "marie-krass@example.com",
        "StrongPass123!",
        first_name="Marie",
        last_name="Krass",
        role=User.Role.WORKER,
    )
    worker = WorkerProfile.objects.create(
        user=user,
        employee_number="MARIE-KRASS",
        active=True,
    )
    upload = SimpleUploadedFile(
        "lexware-stammdaten.json",
        json.dumps({
            "employees": [{
                "name": "Marie Kraß",
                "data": {
                    "compensation_type": "hourly",
                    "hourly_rate": "16.00",
                    "alias_test_marker": "sharp-s-matched",
                },
            }],
        }).encode("utf-8"),
        content_type="application/json",
    )

    response = auth_admin.post(
        "/api/workers/master-data/import/",
        {"file": upload},
        format="multipart",
    )

    assert response.status_code == 200
    assert response.data["unmatched"] == []
    assert response.data["employees"][0]["worker_id"] == str(worker.id)

    matchers = _employee_matchers()
    matched = _find_worker({"employee_name": "Marie Kraß"}, matchers)
    assert matched is not None
    assert matched.id == worker.id


@pytest.mark.django_db
def test_ashkan_confirmed_alias_matches_worker_with_additional_name_tokens(auth_admin):
    user = User.objects.create_user(
        "ashkan-asadian@example.com",
        "StrongPass123!",
        first_name="Ashkan",
        last_name="Asadian Example",
        role=User.Role.WORKER,
    )
    worker = WorkerProfile.objects.create(
        user=user,
        employee_number="ASHKAN-ASADIAN",
        active=True,
    )
    upload = SimpleUploadedFile(
        "lexware-stammdaten.json",
        json.dumps({
            "employees": [{
                "name": "Ashkan Asadian Ghaferokhi",
                "data": {
                    "compensation_type": "salary",
                    "monthly_salary": "3000.00",
                    "alias_test_marker": "ashkan-matched",
                },
            }],
        }).encode("utf-8"),
        content_type="application/json",
    )

    response = auth_admin.post(
        "/api/workers/master-data/import/",
        {"file": upload},
        format="multipart",
    )

    assert response.status_code == 200
    assert response.data["unmatched"] == []
    assert response.data["employees"][0]["worker_id"] == str(worker.id)

    matchers = _employee_matchers()
    matched = _find_worker({"employee_name": "Ashkan Asadian Ghaferokhi"}, matchers)
    assert matched is not None
    assert matched.id == worker.id


@pytest.mark.django_db
def test_confirmed_alias_can_attach_existing_non_worker_user(auth_admin):
    user = User.objects.create_user(
        "ashkan-existing@example.com",
        "StrongPass123!",
        first_name="Ashkan",
        last_name="Asadian",
        role=User.Role.ADMIN,
    )
    assert not WorkerProfile.objects.filter(user=user).exists()

    upload = SimpleUploadedFile(
        "lexware-stammdaten.json",
        json.dumps({
            "employees": [{
                "name": "Ashkan Asadian Ghaferokhi",
                "employee_number": "LEX-ASHKAN-001",
                "data": {
                    "compensation_type": "salary",
                    "monthly_salary": "3000.00",
                },
            }],
        }).encode("utf-8"),
        content_type="application/json",
    )

    response = auth_admin.post(
        "/api/workers/master-data/import/",
        {"file": upload},
        format="multipart",
    )

    assert response.status_code == 200
    assert response.data["unmatched"] == []
    worker = WorkerProfile.objects.get(user=user)
    assert worker.employee_number == "LEX-ASHKAN-001"
    assert user.role == User.Role.ADMIN
