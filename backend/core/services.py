import hashlib,io,json
from django.conf import settings
from django.core.files.base import ContentFile
from django.template import Context,Template
from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer
from .models import AuditLog
def client_ip(request):
    forwarded=request.META.get('HTTP_X_FORWARDED_FOR'); return forwarded.split(',')[0].strip() if forwarded else request.META.get('REMOTE_ADDR')
def audit(request,action,obj,metadata=None): AuditLog.objects.create(actor=request.user if request.user.is_authenticated else None,action=action,object_type=obj.__class__.__name__,object_id=str(getattr(obj,'pk','')),metadata=metadata or {},ip_address=client_ip(request))
def render_contract_pdf(contract):
    html=Template(contract.template.html_template).render(Context({**contract.variables,'contract':contract,'company_name':settings.COMPANY_NAME}))
    plain=html.replace('<h1>','').replace('</h1>','\n\n').replace('<h2>','<b>').replace('</h2>','</b>\n').replace('<br>','\n').replace('<br/>','\n').replace('<br />','\n')
    buffer=io.BytesIO(); doc=SimpleDocTemplate(buffer,pagesize=A4,rightMargin=20*mm,leftMargin=20*mm,topMargin=18*mm,bottomMargin=18*mm,title=contract.title,author=settings.COMPANY_NAME)
    styles=getSampleStyleSheet(); styles.add(ParagraphStyle(name='ContractTitle',parent=styles['Title'],alignment=TA_CENTER,spaceAfter=14)); story=[Paragraph(contract.title,styles['ContractTitle'])]
    for block in plain.split('\n\n'):
        if block.strip(): story.extend([Paragraph(block.strip().replace('\n','<br/>'),styles['BodyText']),Spacer(1,7)])
    if contract.signed_at: story.extend([Spacer(1,16),Paragraph(f'Elektronisch unterzeichnet von: {contract.signed_by_name}',styles['BodyText']),Paragraph(f'Zeitpunkt: {timezone.localtime(contract.signed_at):%d.%m.%Y %H:%M}',styles['BodyText']),Paragraph(f'Prüfsumme: {contract.signature_hash}',styles['BodyText'])])
    doc.build(story); return ContentFile(buffer.getvalue(),name=f'{contract.id}.pdf')
def sign_contract(contract,signer_name,signature_data,request):
    if not signer_name or not signature_data: raise ValueError('Name und Signatur sind erforderlich.')
    payload=json.dumps({'contract':str(contract.id),'name':signer_name,'signature':signature_data,'timestamp':timezone.now().isoformat()},sort_keys=True)
    contract.signed_by_name=signer_name; contract.signature_data=signature_data; contract.signed_at=timezone.now(); contract.signature_ip=client_ip(request); contract.signature_hash=hashlib.sha256(payload.encode()).hexdigest(); contract.status='signed'; contract.pdf.save(f'{contract.id}.pdf',render_contract_pdf(contract),save=False); contract.save(); audit(request,'contract.signed',contract,{'signer':signer_name,'hash':contract.signature_hash}); return contract
