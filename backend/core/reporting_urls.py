from django.urls import path

from . import reporting_views


urlpatterns = [
    path('catalog/', reporting_views.report_catalog),
    path('options/', reporting_views.report_options),
    path('preview/', reporting_views.report_preview),
    path('definitions/', reporting_views.report_definitions),
    path('definitions/<uuid:pk>/', reporting_views.report_definition_detail),
    path('definitions/<uuid:pk>/run/', reporting_views.report_run),
    path('schedules/', reporting_views.report_schedules),
    path('schedules/<uuid:pk>/', reporting_views.report_schedule_detail),
    path('runs/', reporting_views.report_runs),
]
