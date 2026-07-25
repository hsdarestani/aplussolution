import os
from django.core.management.base import BaseCommand
from core.models import User,Position,ContractTemplate
EMPLOYMENT_HTML='''<h1>Arbeitsvertrag</h1>Zwischen {{ company_name }} und {{ employee_name }} wird folgender Arbeitsvertrag geschlossen.<br><br><b>1b – Einsatzbereich:</b> {{ einsatzbereich }}<br><b>3a – Vertragslaufzeit:</b> {{ start_date }} bis {{ end_date|default:"unbefristet" }}<br><b>3b – Neuanstellung:</b> {{ neuanstellung|yesno:"Ja,Nein" }}<br><b>4 – Tätigkeit:</b> {{ taetigkeit }}<br><b>5 – Arbeitszeit:</b> {{ employment_type }}{% if monthly_hours %}, {{ monthly_hours }} Stunden/Monat{% endif %}<br><b>6a – Tariflicher Stundenlohn:</b> {{ tariff_hourly_rate }} EUR<br><b>7 – Übertarifliche Zulage:</b> {{ extra_allowance|default:"0,00" }} EUR<br><br>Weitere Vertragsbedingungen werden aus dem anwaltlich freigegebenen Muster übernommen.'''
class Command(BaseCommand):
    help='Erstellt Grunddaten und den ersten Administrator.'
    def handle(self,*args,**kwargs):
        email=os.getenv('DJANGO_SUPERUSER_EMAIL')
        if email and not User.objects.filter(email=email).exists(): User.objects.create_superuser(email=email,password=os.getenv('DJANGO_SUPERUSER_PASSWORD'),first_name=os.getenv('DJANGO_SUPERUSER_FIRST_NAME','A+'),last_name=os.getenv('DJANGO_SUPERUSER_LAST_NAME','Admin'))
        for name in ['Servicekraft','Hostess','Eventhelfer','Lagerhelfer','Inventurhelfer','Promoter','Logistiker']: Position.objects.get_or_create(name=name)
        ContractTemplate.objects.get_or_create(name='Arbeitsvertrag – Grundmuster',version='1.0',defaults={'kind':'employment','schema':{'fields':['employee_name','einsatzbereich','start_date','end_date','neuanstellung','taetigkeit','employment_type','monthly_hours','tariff_hourly_rate','extra_allowance']},'html_template':EMPLOYMENT_HTML})
        self.stdout.write(self.style.SUCCESS('Grunddaten sind bereit.'))
