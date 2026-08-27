from __future__ import annotations

from django.db import transaction

from .models import ClientCompany, ClientOrder, Contract, Document, Location, Position, Shift, ShiftImportPackage, TimeEntry, WorkerRating
from .workforce_scope import CANONICAL_CLIENTS, CANONICAL_POSITIONS, canonical_client_name, canonical_position_name

POSITION_COLORS = {
    'Servicekraft': '#155eef',
    'Serviceleitung': '#7a5af8',
    'Front Office': '#0891b2',
    'Housekeeping': '#16a34a',
    'Bar-Support': '#d97706',
}
