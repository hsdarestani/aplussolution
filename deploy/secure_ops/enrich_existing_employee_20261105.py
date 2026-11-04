"""One-time existing-worker update from an encrypted, validated JSON payload on stdin.

This code contains no personnel information and must never log payload values.
It must not create workers or mutate an existing login identity.
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

ALLOWED = frozenset({
    "salutation", "street", "postal_code", "city", "full_address",
    "birth_date", "nationality", "birth_name", "birth_place", "birth_country",
    "health_insurance_name", "insurance_type", "social_insurance_number",
    "tax_identification_number", "tax_class",
    "iban", "bank_account_holder", "bank_name", "has_children",
    "children_under_25", "other_employments",
    "signature_place", "signature_place_and_date_as_written",
})

raw = sys.stdin.buffer.read(32769)
if not raw or len(raw) > 32768:
    raise RuntimeError("Payload empty or oversized; nothing changed")
payload = json.loads(raw)
if payload.get("operation") != "enrich_existing_worker_20261105_v1":
    raise RuntimeError("Unrecognized one-time operation")
identity = payload["identity"]
if set(identity) != {"first_name", "last_name", "birth_date"}:
    raise RuntimeError("Incomplete identity")
incoming = payload["master_data"]
if not isinstance(incoming, dict) or set(incoming) - ALLOWED:
    raise RuntimeError("Unexpected master field")
if incoming.get("birth_date") != identity["birth_date"]:
    raise RuntimeError("Birth date mismatches payload")
if not (incoming.get("iban") and incoming.get("tax_identification_number") and incoming.get("other_employments")):
    raise RuntimeError("Personalfragebogen source is incomplete")

def empty(v):
    return v is None or v == "" or v == [] or v == {}

with transaction.atomic():
    candidates = list(WorkerProfile.objects.select_for_update().select_related("user").filter(
        user__first_name__iexact=identity["first_name"].strip(),
        user__last_name__iexact=identity["last_name"].strip(),
    ))
    if len(candidates) != 1:
        raise RuntimeError(f"Expected exactly 1 existing worker; got {len(candidates)}")
    worker = candidates[0]
    master = EmployeeMasterData.objects.select_for_update().filter(worker=worker).first()
    if not master:
        raise RuntimeError("Existing worker master row absent, refusing to create one")
    data = dict(master.data or {})
    original_birth = data.get("birth_date")
    if not empty(original_birth) and str(original_birth) != identity["birth_date"]:
        raise RuntimeError("Existing birth date differs; refusing all changes")

    changed, conflicts, same = [], [], []
    sources = dict(master.source_map or {})
    for key, value in incoming.items():
        if empty(value):
            continue
        existing = data.get(key)
        if empty(existing):
            data[key] = value
            sources[key] = "verified_uploaded_personalfragebogen_20261105"
            changed.append(key)
        elif existing == value or str(existing) == str(value):
            same.append(key)
        else:
            conflicts.append(key)

    phone_status = "unchanged"
    incoming_phone = payload.get("phone", "").strip()
    if incoming_phone and empty(worker.user.phone):
        worker.user.phone = incoming_phone
        worker.user.save(update_fields=["phone"])
        phone_status = "filled"
    elif incoming_phone and worker.user.phone.strip() != incoming_phone:
        phone_status = "conflict_preserved"

    master.data = data
    master.source_map = sources
    completeness, missing = calculate_completeness(data)
    master.completeness = completeness
    master.missing_fields = missing
    master.verified_at = None
    master.verified_by = None
    master.save(update_fields=[
        "data", "source_map", "completeness", "missing_fields",
        "verified_at", "verified_by", "updated_at"
    ])
    AuditLog.objects.create(
        actor=None, action="worker_akte.secure_questionnaire_enrichment",
        object_type="WorkerProfile", object_id=str(worker.pk),
        metadata={"operation": "enrich_existing_worker_20261105_v1",
                  "fields_added": sorted(changed),
                  "conflicts_preserved": sorted(conflicts),
                  "identical_fields": sorted(same),
                  "phone_status": phone_status}
    )

    # Verify persisted values with read-back inside the same transaction.
    master.refresh_from_db()
    if any(master.data.get(key) != incoming[key] for key in changed):
        raise RuntimeError("Read-back failed; transaction rolled back")

print("SECURE_WORKER_ENRICHMENT_SUCCESS")
print("existing_worker_matches=1")
print("fields_added_count=" + str(len(changed)))
print("fields_already_same_count=" + str(len(same)))
print("fields_conflicting_preserved_count=" + str(len(conflicts)))
print("conflicting_field_names=" + ",".join(sorted(conflicts)))
print("phone_status=" + phone_status)
print("post_update_completeness_percent=" + str(completeness))
print("new_user_accounts=0")
print("sensitive_values_logged=0")
