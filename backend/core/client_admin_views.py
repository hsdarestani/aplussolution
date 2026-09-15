from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .credential_reset import generated_worker_password
from .models import ClientCompany, User
from .permissions import IsAdmin
from .services import audit


@api_view(['POST'])
@permission_classes([IsAdmin])
def reset_client_password(request, pk):
    """Reset the portal password for one contact attached to a client company.

    The endpoint is intentionally admin-only.  A specific contact can be supplied
    by the web profile; otherwise the oldest active client contact is used.  It
    never creates a new portal account implicitly.
    """
    client = ClientCompany.objects.prefetch_related('contacts').filter(pk=pk).first()
    if not client:
        return Response({'detail': 'Kunde wurde nicht gefunden.'}, status=404)

    contacts = client.contacts.filter(role=User.Role.CLIENT, is_active=True)
    contact_id = request.data.get('contact_id')
    if contact_id:
        contact = contacts.filter(pk=contact_id).first()
        if not contact:
            return Response({'detail': 'Der ausgewählte Portal-Zugang gehört nicht zu diesem Kunden.'}, status=400)
    else:
        contact = contacts.order_by('date_joined', 'id').first()

    if not contact:
        return Response({'detail': 'Für diesen Kunden ist kein aktiver Portal-Zugang hinterlegt.'}, status=400)

    password = generated_worker_password()
    contact.set_password(password)
    contact.save(update_fields=['password'])
    audit(request, 'client.password_reset', client, {'contact_user_id': str(contact.id)})

    return Response({
        'detail': 'Das Kundenpasswort wurde zurückgesetzt.',
        'contact_id': str(contact.id),
        'email': contact.email,
        'temporary_password': password,
    })
