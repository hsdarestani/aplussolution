from pathlib import Path

path = Path('backend/core/serializers.py')
text = path.read_text()
old = """    def validate_name(self, value):
        canonical = canonical_position_name(value)
        if not canonical:
            allowed = ', '.join(CANONICAL_POSITIONS)
            raise serializers.ValidationError(f'Aktuell sind nur diese Positionen vorgesehen: {allowed}.')
        qs = Position.objects.filter(name__iexact=canonical)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('Diese Position ist bereits vorhanden.')
        return canonical
"""
new = """    def validate_name(self, value):
        cleaned = str(value or '').strip()
        canonical = canonical_position_name(cleaned)
        target = canonical or cleaned
        qs = Position.objects.filter(name__iexact=target)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('Diese Position ist bereits vorhanden.')
        return target
"""
if text.count(old) != 1:
    raise SystemExit(f'Expected one validation block, found {text.count(old)}')
text = text.replace(old, new, 1)
text = text.replace('from .workforce_scope import CANONICAL_POSITIONS, canonical_position_name\n', 'from .workforce_scope import canonical_position_name\n', 1)
path.write_text(text)
