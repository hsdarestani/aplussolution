"""Safely enrich one existing employee profile using confidential JSON on stdin.

This repository file contains no employee identity or personal values.
Run only inside the trusted backend container with an authenticated operator.
The caller supplies an input payload out-of-band; never commit that payload.
"""
import json
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from django.db import transaction
from core.models import AuditLog, EmployeeMasterData, WorkerProfile
from core.wiw_sync import calculate_completeness

ALLOWED_FIELDS = frozenset({
    "birth_date", "birth_place", "birth_country", "nationality",
    "street", "postal_code", "city", "full_address",
    "residence_permit_type", "residence_permit_unlimited",
    "residence_card_valid_until", "residence_permit_issued_on",
    "residence_permit_issued_by", "work_authorization",
    "residence_document_number", "eye_color", "height_cm",
})
MAX_BYTES = 16384

def empty(value):
    return value in (None, "", [], {})

def main():
    raw = sys.stdin.buffer.read(MAX_BYTES + 1)
    if not raw or len(raw) > MAX_BYTES:
        raise RuntimeError("Missing or oversized input. No changes made.")
    payload = json.loads(raw)
    if not isinstance(payload, dict) or payload.get("operation") != "enrich_existing_worker_residence_v1":
        raise RuntimeError("Invalid operation. No changes made.")
    identity = payload.get("identity")
    incoming = payload.get("master_data")
    if not isinstance(identity, dict) or not isinstance(incoming, dict):
        raise RuntimeError("Invalid payload. No changes made.")
    if set(identity) != {"first_name", "last_name", "birth_date"}:
        raise RuntimeError("Three identity keys are required.")
    if not all(isinstance(v, str) and v.strip() for v in identity.values()):
        raise RuntimeError("Missing identity value.")
    if not incoming or set(incoming) - ALLOWED_FIELDS:
        raise RuntimeError("Unexpected employee field.")
    if incoming.get("birth_date") != identity["birth_date"]:
        raise RuntimeError("Birth date must match identity.")
    if any(not isinstance(v, (str, int, bool)) for v in incoming.values()):
        raise RuntimeError("Unexpected field value type.")

    with transaction.atomic():
        candidates = list(
            WorkerProfile.objects.select_for_update()
            .select_related("user")
            .filter(
                user__first_name__iexact=identity["first_name"].strip(),
                user__last_name__iexact=identity["last_name"].strip(),
            )
        )
        if len(candidates) != 1:
            raise RuntimeError("Expected exactly one existing employee.")
        worker = candidates[0]
        master = (
            EmployeeMasterData.objects.select_for_update()
            .filter(worker=worker).first()
        )
        if master is None:
            raise RuntimeError("No existing master record; refusing creation.")
        data = dict(master.data or {})
        original_birth = data.get("birth_date")
        if not empty(original_birth) and str(original_birth) != identity["birth_date"]:
            raise RuntimeError("Existing birth date conflicts; no changes made.")

        added, unchanged, conflicts = [], [], []
        sources = dict(master.source_map or {})
        for key, value in incoming.items():
            if empty(value):
                continue
            prior = data.get(key)
            if empty(prior):
                data[key] = value
                sources[key] = "uploaded_residence_permit_admin_review"
                added.append(key)
            elif str(prior) == str(value):
                unchanged.append(key)
            else:
                conflicts.append(key)

        if added:
            master.data = data
            master.source_map = sources
            completeness, missing = calculate_completeness(data)
            master.completeness = completeness
            master.missing_fields = missing
            master.verified_at = None
            master.verified_by = None
            master.save(update_fields=[
                "data", "source_map", "completeness", "missing_fields",
                "verified_at", "verified_by", "updated_at",
            ])
        AuditLog.objects.create(
            actor=None,
            action="worker_akte.residence_card_enrichment",
            object_type="WorkerProfile",
            object_id=str(worker.pk),
            metadata={
                "added_fields": sorted(added),
                "unchanged_fields": sorted(unchanged),
                "conflicting_fields_preserved": sorted(conflicts),
                "source": "operator_supplied_residence_permit",
                "values_logged": False,
            },
        )
        master.refresh_from_db()
        if any(master.data.get(key) != incoming[key] for key in added):
            raise RuntimeError("Persisted read-back did not match.")
    print("EXISTING_WORKER_ENRICHMENT_COMMITTED")
    print("fields_added_count=" + str(len(added)))
    print("fields_unchanged_count=" + str(len(unchanged)))
    print("fields_conflicting_preserved_count=" + str(len(conflicts)))
    print("conflicting_field_names=" + ",".join(sorted(conflicts)))
    print("new_employee_accounts=0")
    print("personal_values_logged=0")

if __name__ == "__main__":
    main()
