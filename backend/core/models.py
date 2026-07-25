import uuid
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True
    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError('E-Mail-Adresse ist erforderlich.')
        email = self.normalize_email(email)
        user = self.model(email=email, username=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user
    def create_superuser(self, email, password=None, **extra):
        extra.setdefault('is_staff', True); extra.setdefault('is_superuser', True); extra.setdefault('role', 'admin')
        return self.create_user(email, password, **extra)


class TimestampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        abstract = True


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'admin', 'Administration'
        MANAGER = 'manager', 'Disposition'
        WORKER = 'worker', 'Mitarbeiter'
        CLIENT = 'client', 'Kunde'
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.WORKER)
    phone = models.CharField(max_length=40, blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    locale = models.CharField(max_length=10, default='de')
    is_onboarded = models.BooleanField(default=False)
    deletion_requested_at = models.DateTimeField(blank=True, null=True)
    username = models.CharField(max_length=150, blank=True)
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    objects = UserManager()
    def __str__(self):
        return self.get_full_name() or self.email


class ClientCompany(TimestampedModel):
    name = models.CharField(max_length=200)
    customer_number = models.CharField(max_length=50, unique=True)
    contacts = models.ManyToManyField(User, related_name='client_companies', blank=True, limit_choices_to={'role': User.Role.CLIENT})
    address = models.TextField(blank=True)
    vat_id = models.CharField(max_length=50, blank=True)
    contract_visibility_enabled = models.BooleanField(default=True)
    active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    def __str__(self): return self.name


class WorkerProfile(TimestampedModel):
    class EmploymentType(models.TextChoices):
        MINI = 'minijob', 'Minijob'
        PART = 'teilzeit', 'Teilzeit'
        FULL = 'vollzeit', 'Vollzeit'
        STUDENT = 'student', 'Studentische Aushilfe'
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='worker_profile')
    employee_number = models.CharField(max_length=50, unique=True)
    employment_type = models.CharField(max_length=20, choices=EmploymentType.choices, default=EmploymentType.MINI)
    monthly_hours = models.DecimalField(max_digits=7, decimal_places=2, blank=True, null=True)
    tariff_hourly_rate = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    extra_allowance = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    ranking_points = models.IntegerField(default=0)
    skills = models.JSONField(default=list, blank=True)
    active = models.BooleanField(default=True)
    def __str__(self): return f'{self.employee_number} – {self.user}'


class Location(TimestampedModel):
    client = models.ForeignKey(ClientCompany, on_delete=models.CASCADE, related_name='locations', null=True, blank=True)
    name = models.CharField(max_length=200)
    address = models.TextField()
    latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    geofence_radius_m = models.PositiveIntegerField(default=250)
    timezone = models.CharField(max_length=50, default='Europe/Berlin')
    active = models.BooleanField(default=True)
    def __str__(self): return self.name


class Position(TimestampedModel):
    name = models.CharField(max_length=120, unique=True)
    color = models.CharField(max_length=20, default='#2457E6')
    required_skills = models.JSONField(default=list, blank=True)
    active = models.BooleanField(default=True)
    def __str__(self): return self.name


class ClientOrder(TimestampedModel):
    class Status(models.TextChoices):
        NEW='new','Neu'; PLANNING='planning','In Planung'; CONFIRMED='confirmed','Bestätigt'; DONE='done','Abgeschlossen'; CANCELLED='cancelled','Storniert'
    client = models.ForeignKey(ClientCompany, on_delete=models.CASCADE, related_name='orders')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    requested_staff = models.PositiveIntegerField(default=1)
    functions = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    attachment = models.FileField(upload_to='orders/', blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_orders')


class Availability(TimestampedModel):
    worker = models.ForeignKey(WorkerProfile, on_delete=models.CASCADE, related_name='availabilities')
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    available = models.BooleanField(default=True)
    note = models.CharField(max_length=250, blank=True)


class Shift(TimestampedModel):
    class Status(models.TextChoices):
        DRAFT='draft','Entwurf'; PUBLISHED='published','Veröffentlicht'; CONFIRMED='confirmed','Bestätigt'; COMPLETED='completed','Abgeschlossen'; CANCELLED='cancelled','Storniert'
    order = models.ForeignKey(ClientOrder, on_delete=models.SET_NULL, related_name='shifts', null=True, blank=True)
    client = models.ForeignKey(ClientCompany, on_delete=models.CASCADE, related_name='shifts')
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name='shifts')
    position = models.ForeignKey(Position, on_delete=models.PROTECT, related_name='shifts')
    worker = models.ForeignKey(WorkerProfile, on_delete=models.SET_NULL, related_name='shifts', blank=True, null=True)
    starts_at = models.DateTimeField(); ends_at = models.DateTimeField()
    break_minutes = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    is_open = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    required_count = models.PositiveIntegerField(default=1)
    published_at = models.DateTimeField(blank=True, null=True)
    class Meta:
        ordering = ['starts_at']
        indexes = [models.Index(fields=['starts_at', 'ends_at']), models.Index(fields=['worker', 'starts_at'])]


class TimeEntry(TimestampedModel):
    worker = models.ForeignKey(WorkerProfile, on_delete=models.CASCADE, related_name='time_entries')
    shift = models.ForeignKey(Shift, on_delete=models.SET_NULL, related_name='time_entries', null=True, blank=True)
    clock_in = models.DateTimeField(); clock_out = models.DateTimeField(blank=True, null=True)
    clock_in_lat = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    clock_in_lng = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    clock_out_lat = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    clock_out_lng = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    photo = models.ImageField(upload_to='timeclock/', blank=True, null=True)
    approved = models.BooleanField(default=False)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_time_entries')
    edit_reason = models.TextField(blank=True)
    @property
    def worked_minutes(self):
        end = self.clock_out or timezone.now()
        return max(0, int((end - self.clock_in).total_seconds() // 60) - (self.shift.break_minutes if self.shift else 0))


class TimeOffRequest(TimestampedModel):
    class Status(models.TextChoices): PENDING='pending','Offen'; APPROVED='approved','Genehmigt'; REJECTED='rejected','Abgelehnt'
    worker = models.ForeignKey(WorkerProfile, on_delete=models.CASCADE, related_name='time_off_requests')
    starts_on = models.DateField(); ends_on = models.DateField(); reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    decided_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)


class ShiftSwapRequest(TimestampedModel):
    class Status(models.TextChoices): PENDING='pending','Offen'; APPROVED='approved','Genehmigt'; REJECTED='rejected','Abgelehnt'; CANCELLED='cancelled','Storniert'
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name='swap_requests')
    requested_by = models.ForeignKey(WorkerProfile, on_delete=models.CASCADE, related_name='swap_requests')
    offered_to = models.ForeignKey(WorkerProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='swap_offers')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    note = models.TextField(blank=True)


class ContractTemplate(TimestampedModel):
    class Kind(models.TextChoices):
        EMPLOYMENT='employment','Arbeitsvertrag'; TERMINATION='termination','Aufhebungsvertrag'; REHIRE='rehire','Wiederaufnahme'; CLIENT_AUEV='client_auev','Einzelarbeitnehmerüberlassungsvertrag'
    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=30, choices=Kind.choices)
    version = models.CharField(max_length=30, default='1.0')
    schema = models.JSONField(default=dict)
    html_template = models.TextField()
    active = models.BooleanField(default=True)
    class Meta: unique_together = ('name', 'version')


class Contract(TimestampedModel):
    class Status(models.TextChoices):
        DRAFT='draft','Entwurf'; READY='ready','Prüfbereit'; SENT='sent','Versendet'; SIGNED='signed','Unterzeichnet'; EXPIRED='expired','Abgelaufen'; CANCELLED='cancelled','Storniert'
    template = models.ForeignKey(ContractTemplate, on_delete=models.PROTECT, related_name='contracts')
    worker = models.ForeignKey(WorkerProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='contracts')
    client = models.ForeignKey(ClientCompany, on_delete=models.SET_NULL, null=True, blank=True, related_name='contracts')
    title = models.CharField(max_length=250)
    variables = models.JSONField(default=dict)
    starts_on = models.DateField(blank=True, null=True)
    ends_on = models.DateField(blank=True, null=True)
    reminder_date = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    pdf = models.FileField(upload_to='contracts/%Y/%m/', blank=True, null=True)
    sent_at = models.DateTimeField(blank=True, null=True)
    signed_at = models.DateTimeField(blank=True, null=True)
    signed_by_name = models.CharField(max_length=200, blank=True)
    signature_data = models.TextField(blank=True)
    signature_hash = models.CharField(max_length=128, blank=True)
    signature_ip = models.GenericIPAddressField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_contracts')


class Document(TimestampedModel):
    class Folder(models.TextChoices):
        GENERAL='general','Allgemein'; CONTRACTS='contracts','Verträge'; PAYROLL='payroll','Lohnabrechnungen'; CERTIFICATES='certificates','Nachweise'; ORDERS='orders','Aufträge'
    class Visibility(models.TextChoices):
        ADMIN='admin','Nur Administration'; WORKER='worker','Mitarbeiter'; CLIENT='client','Kunde'; SHARED='shared','Geteilt'
    title = models.CharField(max_length=250)
    file = models.FileField(upload_to='documents/%Y/%m/')
    folder = models.CharField(max_length=30, choices=Folder.choices, default=Folder.GENERAL)
    visibility = models.CharField(max_length=20, choices=Visibility.choices, default=Visibility.ADMIN)
    worker = models.ForeignKey(WorkerProfile, on_delete=models.CASCADE, null=True, blank=True, related_name='documents')
    client = models.ForeignKey(ClientCompany, on_delete=models.CASCADE, null=True, blank=True, related_name='documents')
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='uploaded_documents')


class PayrollStatement(TimestampedModel):
    worker = models.ForeignKey(WorkerProfile, on_delete=models.CASCADE, related_name='payroll_statements')
    period = models.DateField(help_text='Erster Tag des Abrechnungsmonats')
    gross_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    net_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    document = models.FileField(upload_to='payroll/%Y/%m/')
    class Meta: unique_together = ('worker', 'period')


class WorkerRating(TimestampedModel):
    worker = models.ForeignKey(WorkerProfile, on_delete=models.CASCADE, related_name='ratings')
    client = models.ForeignKey(ClientCompany, on_delete=models.CASCADE, related_name='ratings')
    shift = models.ForeignKey(Shift, on_delete=models.SET_NULL, null=True, blank=True, related_name='ratings')
    score = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    punctuality = models.PositiveSmallIntegerField(default=5, validators=[MinValueValidator(1), MaxValueValidator(5)])
    quality = models.PositiveSmallIntegerField(default=5, validators=[MinValueValidator(1), MaxValueValidator(5)])
    teamwork = models.PositiveSmallIntegerField(default=5, validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)


class Conversation(TimestampedModel):
    title = models.CharField(max_length=200, blank=True)
    participants = models.ManyToManyField(User, related_name='conversations')
    is_announcement = models.BooleanField(default=False)


class Message(TimestampedModel):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    body = models.TextField()
    attachment = models.FileField(upload_to='messages/', blank=True, null=True)
    read_by = models.ManyToManyField(User, blank=True, related_name='read_messages')


class Notification(TimestampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    kind = models.CharField(max_length=50, default='general')
    action_url = models.CharField(max_length=500, blank=True)
    read_at = models.DateTimeField(blank=True, null=True)


class AuditLog(TimestampedModel):
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=100)
    object_type = models.CharField(max_length=100)
    object_id = models.CharField(max_length=100, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    class Meta: ordering = ['-created_at']
