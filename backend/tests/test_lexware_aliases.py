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
