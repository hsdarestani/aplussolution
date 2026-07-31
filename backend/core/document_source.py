import io
import zipfile


class InvalidTemplateSource(ValueError):
    pass


def validate_template_source(upload, source_format):
    position = upload.tell() if hasattr(upload, 'tell') else 0
    content = upload.read()
    if hasattr(upload, 'seek'):
        upload.seek(position)
    if not content:
        raise InvalidTemplateSource('Die hochgeladene Datei ist leer.')
    if source_format == 'docx':
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = set(archive.namelist())
                if '[Content_Types].xml' not in names or 'word/document.xml' not in names:
                    raise InvalidTemplateSource('Die Datei ist kein gültiges DOCX-Dokument.')
        except zipfile.BadZipFile as exc:
            raise InvalidTemplateSource('Die Datei ist kein gültiges DOCX-Dokument.') from exc
    elif source_format in {'pdf_overlay', 'static_pdf'}:
        if not content.lstrip().startswith(b'%PDF-'):
            raise InvalidTemplateSource('Die Datei ist kein gültiges PDF-Dokument.')
    return True
