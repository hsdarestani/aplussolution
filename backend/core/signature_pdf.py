import base64
import io
import re

from django.core.files.base import ContentFile
from pypdf import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .models import ContractSignature


_DATA_URL = re.compile(r'^data:image/(?:png|jpeg|jpg);base64,(.+)$', re.IGNORECASE | re.DOTALL)
_ROLE_LABELS = {
    ContractSignature.Role.EMPLOYEE: 'Mitarbeiter',
    ContractSignature.Role.EMPLOYER: 'Arbeitgeber',
    ContractSignature.Role.CLIENT: 'Kunde',
}


def _image_bytes(value):
    if not isinstance(value, str):
        return None
    match = _DATA_URL.match(value.strip())
    if not match:
        return None
    try:
        return base64.b64decode(match.group(1), validate=True)
    except Exception:
        return None


def stamp_drawn_signatures(contract):
    """Stamp browser-drawn signature PNGs onto the last page of the generated PDF.

    Typed/legacy signatures are left untouched. The signature hash continues to be
    calculated from the original submitted data in services.sign_contract.
    """
    if not contract.pdf:
        return False

    signatures = []
    for signature in contract.signatures.order_by('signed_at'):
        image = _image_bytes(signature.signature_data)
        if image:
            signatures.append((signature, image))
    if not signatures:
        return False

    contract.pdf.open('rb')
    try:
        source = contract.pdf.read()
    finally:
        contract.pdf.close()

    reader = PdfReader(io.BytesIO(source))
    if not reader.pages:
        return False
    writer = PdfWriter()

    for index, page in enumerate(reader.pages):
        if index == len(reader.pages) - 1:
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)
            packet = io.BytesIO()
            overlay = canvas.Canvas(packet, pagesize=(width, height))

            count = len(signatures)
            margin = 42.0
            gap = 18.0
            usable = max(120.0, width - (2 * margin) - (gap * max(0, count - 1)))
            slot = usable / max(1, count)
            image_height = 34.0
            image_y = 48.0

            for position, (signature, image_bytes) in enumerate(signatures):
                x = margin + position * (slot + gap)
                role = _ROLE_LABELS.get(signature.role, signature.role)
                overlay.setFont('Helvetica', 7)
                overlay.setFillColorRGB(0.35, 0.39, 0.45)
                overlay.drawString(x, image_y + image_height + 4, role)
                try:
                    image_reader = ImageReader(io.BytesIO(image_bytes))
                    overlay.drawImage(
                        image_reader,
                        x,
                        image_y,
                        width=max(70.0, slot - 8),
                        height=image_height,
                        preserveAspectRatio=True,
                        anchor='sw',
                        mask='auto',
                    )
                except Exception:
                    continue
                overlay.setFont('Helvetica', 7)
                overlay.setFillColorRGB(0.15, 0.18, 0.22)
                overlay.drawString(x, 38.0, signature.signer_name[:70])

            overlay.save()
            packet.seek(0)
            page.merge_page(PdfReader(packet).pages[0])
        writer.add_page(page)

    output = io.BytesIO()
    writer.write(output)
    filename = contract.pdf.name.rsplit('/', 1)[-1]
    contract.pdf.save(filename, ContentFile(output.getvalue()), save=False)
    contract.save(update_fields=['pdf', 'updated_at'])
    return True
