"""Apply an encrypted Personalfragebogen payload to ONE existing worker.

Input: JSON via stdin, decrypted inside production host (never print personal values).
No user creation, no changing login email/name/role, no destructive overwrites.
"""
import json
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from django.db import transaction
from core.models import EmployeeMasterData, WorkerProfile, AuditLog
from core.wiw_sync import calculate_completeness

ALLOWED = frozenset({
    "street", "postal_code", "city", "full_address", "birth_date",
    "nationality", "birth_name", "birth_place", "birth_country",
    "social_insurance_number", "health_insurance_name",
    "tax_identification_number", "tax_class", "child_allowance",
    "tax_allowance", "religion", "spouse_religion", "iban",
    "bank_account_holder", "bank_name", "salutation", "insurance_type",
    "has_children", "children_under_25", "other_employments",
    "signature_place_and_date_as_written",
})

def missing(v):
    return v is None or v == "" or v == [] or v == {}

def main():
    raw = sys.stdin.buffer.read(20001)
    if not raw or len(raw) > 20000:
        raise RuntimeError("INVALID_INPUT_LENGTH")
    p = json.loads(raw)
    if p.get("operation") != "enrich_existing_worker_personalfragebogen_v1":
        raise RuntimeError("INVALID_OPERATION")
    target, incoming, profile = p.get("target"), p.get("master_data"), p.get("profile", {})
    if not isinstance(target, dict) or not isinstance(incoming, dict) or not isinstance(profile, dict):
        raise RuntimeError("INVALID_STRUCTURE")
    if set(target) != {"first_name", "last_name", "email", "birth_date"}:
        raise RuntimeError("INVALID_IDENTITY_FIELDS")
    if any(not isinstance(v, str) or not v.strip() for v in target.values()):
        raise RuntimeError("INVALID_IDENTITY")
    if not incoming or set(incoming) - ALLOWED:
        raise RuntimeError("INVALID_DATA_FIELDS")
    if set(profile) - {"phone"}:
        raise RuntimeError("INVALID_PROFILE_FIELDS")
    if incoming.get("birth_date") != target["birth_date"]:
        raise RuntimeError("IDENTITY_BIRTH_DATE_MISMATCH")
    if any(missing(v) for v in incoming.values()):
        raise RuntimeError("BLANK_VALUES_NOT_ALLOWED")
    if "other_employments" in incoming and not isinstance(incoming["other_employments"], list):
        raise RuntimeError("INVALID_OTHER_EMPLOYMENTS")
    with transaction.atomic():
        found = list(WorkerProfile.objects.select_for_update().select_related("user").filter(
            user__first_name__iexact=target["first_name"],
            user__last_name__iexact=target["last_name"],
            user__email__iexact=target["email"],
        )[:2])
        if len(found) != 1 or found[0].user.role != "worker":
            raise RuntimeError("EXACT_EXISTING_WORKER_NOT_FOUND")
        worker = found[0]
        master, created = EmployeeMasterData.objects.select_for_update().get_or_create(worker=worker)
        data = dict(master.data or {})
        prior_birth = data.get("birth_date")
        if not missing(prior_birth) and str(prior_birth) != target["birth_date"]:
            raise RuntimeError("EXISTING_BIRTH_DATE_CONFLICT")
        inserted, same, conflicts = [], [], []
        sources = dict(master.source_map or {})
        for key, value in incoming.items():
            old = data.get(key)
            if missing(old) or old == "-":
                data[key] = value
                sources[key] = "personalfragebogen_2026_11_03_verified_pdf"
                inserted.append(key)
            elif old == value:
                same.append(key)
            else:
                conflicts.append(key)
        phone_result = "unchanged"
        phone = profile.get("phone")
        if isinstance(phone, str) and phone.strip():
            if missing(worker.user.phone):
                worker.user.phone = phone.strip()
                worker.user.save(update_fields=["phone"])
                phone_result = "added"
            elif worker.user.phone != phone.strip():
                phone_result = "conflict_preserved"
        if inserted:
            master.data = data
            master.source_map = sources
            master.completeness, master.missing_fields = calculate_completeness(data)
            master.verified_at = None
            master.verified_by = None
            master.save()
        if inserted or phone_result == "added":
            AuditLog.objects.create(
                actor=None, action="worker_akte.personnel_enrichment",
                object_type="WorkerProfile", object_id=str(worker.pk),
                metadata={"added_fields": sorted(inserted),
                          "preserved_conflicts": sorted(conflicts),
                          "phone_result": phone_result,
                          "source": "encrypted_operator_personalfragebogen",
                          "personal_values_logged": False,
                          "created_worker": False},
            )
        master.refresh_from_db()
        for key in inserted:
            if master.data.get(key) != incoming[key]:
                raise RuntimeError("READBACK_VERIFICATION_FAILED")
    print("EXISTING_WORKER_PERSONALFRAGEBOGEN_OK")
    print("worker_created=0")
    print("master_record_created=" + str(int(created)))
    print("fields_added=" + str(len(inserted)))
    print("fields_same=" + str(len(same)))
    print("fields_conflict_preserved=" + str(len(conflicts)))
    print("conflict_field_names=" + ",".join(sorted(conflicts)))
    print("phone_result=" + phone_result)
    print("personal_values_logged=0")

if __name__ == "__main__":
    main()
