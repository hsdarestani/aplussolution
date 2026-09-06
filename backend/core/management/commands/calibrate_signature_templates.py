from django.core.management.base import BaseCommand

from core.models import ContractTemplate


DGB_SIGNATURE_PLACEMENTS = {
    'employee': {
        'page': 6,
        'x': 0.090710,
        'y': 0.225683,
        'width': 0.329244,
        'height': 0.047512,
    },
    'employer': {
        'page': 6,
        'x': 0.090710,
        'y': 0.348027,
        'width': 0.329244,
        'height': 0.047512,
    },
}


class Command(BaseCommand):
    help = 'Pins signature fields for templates whose converted PDF geometry is known.'

    def handle(self, *args, **kwargs):
        template = ContractTemplate.objects.filter(slug='arbeitsvertrag-dgb-gvp').first()
        if not template:
            self.stdout.write(self.style.WARNING('DGB/GVP contract template is not installed.'))
            return

        schema = dict(template.schema or {})
        if schema.get('signature_placements') == DGB_SIGNATURE_PLACEMENTS:
            self.stdout.write(self.style.SUCCESS('DGB/GVP signature fields already calibrated.'))
            return

        # These coordinates are measured from the production LibreOffice-converted
        # A4 PDF (595.304 x 841.890 pt). They cover the two printed signature lines
        # on page 6 and deliberately bypass heuristic SmartDocs placement.
        schema['signature_placements'] = DGB_SIGNATURE_PLACEMENTS
        template.schema = schema
        template.save(update_fields=['schema', 'updated_at'])
        self.stdout.write(self.style.SUCCESS('DGB/GVP signature fields calibrated.'))
