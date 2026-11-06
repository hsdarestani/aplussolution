from django.contrib.auth import get_user_model
from django.test import TestCase
from core.models import WorkerProfile
from core.serializers import WorkerProfileSerializer


class WorkerDisplayNameTests(TestCase):
    def test_display_name_preserves_statutory_identity(self):
        user = get_user_model().objects.create_user(
            email='display-alias@example.invalid', password='test-password-only',
            first_name='Jamoliddin', last_name='Dadamirzaev',
        )
        worker = WorkerProfile.objects.create(user=user, employee_number='TEST-ALIAS-1')
        original = WorkerProfileSerializer(worker).data['user_detail']
        assert original['name'] == 'Jamoliddin Dadamirzaev'
        worker.display_name = 'Jamal D.'
        worker.save(update_fields=['display_name'])
        detail = WorkerProfileSerializer(worker).data['user_detail']
        assert detail['name'] == 'Jamal D.'
        assert detail['display_name'] == 'Jamal D.'
        assert detail['legal_name'] == 'Jamoliddin Dadamirzaev'
        assert detail['first_name'] == 'Jamoliddin'
        assert detail['last_name'] == 'Dadamirzaev'
        assert user.get_full_name() == 'Jamoliddin Dadamirzaev'
