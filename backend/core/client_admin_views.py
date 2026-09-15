from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import transaction
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .credential_reset import generated_worker_password
from .models import ClientCompany, User
from .permissions import IsAdmin
from .services import audit


@api_view(['POST'])
@permission_classes([IsAdmin])
def reset_client_password(request, pk):
    """Reset or create the portal password for one client contact.

    Admins may reset an existing linked client contact, reactivate an inactive
    linked contact, or create the first portal contact when a contact_email is
    supplied. Existing users from another account/company are never attached
    implicitly.
    """
    client = ClientCompany.objects.prefetch_related('contacts').filter(pk=pk).first()
    if not client:
        return Response({'detail': 'Kunde wurde nicht gefunden.'}, status=404)

    linked_contacts = client.contacts.filter(role=User.Role.CLIENT)
    contact_id = request.data.get('contact_id')
    contact = None
    created = False
    reactivated = False

    if contact_id:
        contact = linked_contacts.filter(pk=contact_id).first()
        if not contact:
            return Response({'detail': 'Der ausgewählte Portal-Zugang gehört nicht zu diesem Kunden.'}, status=400)
    else:
        contact = linked_contacts.filter(is_active=True).order_by('date_joined', 'id').first()
        if not contact:
            contact = linked_contacts.order_by('date_joined', 'id').first()

    password = generated_worker_password()

    with transaction.atomic():
        if not contact:
            email = str(request.data.get('contact_email') or '').strip().lower()
            if not email:
                return Response({
                    'detail': 'Für diesen Kunden ist noch kein Portal-Zugang hinterlegt. Bitte eine Kontakt-E-Mail angeben.'
                }, status=400)
            try:
                validate_email(email)
            except DjangoValidationError:
                return Response({'detail': 'Bitte eine gültige Kontakt-E-Mail angeben.'}, status=400)

            existing = User.objects.filter(email__iexact=email).first()
            if existing:
                return Response({
                    'detail': 'Diese E-Mail-Adresse ist bereits registriert und kann nicht automatisch diesem Kunden zugeordnet werden.'
                }, status=400)

            contact = User.objects.create_user(
                email=email,
                password=password,
                first_name=str(request.data.get('contact_first_name') or '').strip(),
                last_name=str(request.data.get('contact_last_name') or '').strip(),
                phone=str(request.data.get('contact_phone') or '').strip(),
                role=User.Role.CLIENT,
                is_onboarded=True,
                is_active=True,
            )
            client.contacts.add(contact)
            created = True
        else:
            reactivated = not contact.is_active
            contact.set_password(password)
            contact.is_active = True
            contact.is_onboarded = True
            update_fields = ['password', 'is_active', 'is_onboarded']

            incoming_fields = {
                'contact_first_name': 'first_name',
                'contact_last_name': 'last_name',
                'contact_phone': 'phone',
            }
            for incoming, field in incoming_fields.items():
                if incoming in request.data:
                    setattr(contact, field, str(request.data.get(incoming) or '').strip())
                    update_fields.append(field)
            contact.save(update_fields=update_fields)

        audit(
            request,
            'client.portal_password_reset',
            client,
            {
                'contact_user_id': str(contact.id),
                'portal_access_created': created,
                'portal_access_reactivated': reactivated,
            },
        )

    if created:
        detail = 'Portal-Zugang wurde erstellt und ein temporäres Passwort vergeben.'
    elif reactivated:
        detail = 'Portal-Zugang wurde reaktiviert und das Passwort zurückgesetzt.'
    else:
        detail = 'Das Kundenpasswort wurde zurückgesetzt.'

    return Response({
        'detail': detail,
        'contact_id': str(contact.id),
        'email': contact.email,
        'temporary_password': password,
        'portal_access_created': created,
        'portal_access_reactivated': reactivated,
    })
