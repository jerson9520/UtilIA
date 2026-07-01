from django.urls import path
from core.views import (
    audit_aspects,
    list_aspects,
    audit_historical,
    base_historical,
    smart_base_historical,
    export_base_historical_excel,
)

urlpatterns = [
    path("aspectos/audit/", audit_aspects, name="audit_aspects"),
    path("aspectos/", list_aspects, name="list_aspects"),

    path("historico/audit/", audit_historical, name="audit_historical"),
    path("historico/base/", base_historical, name="base_historical"),
    path("historico/smart-base/", smart_base_historical, name="smart_base_historical"),
    path("historico/base/export-excel/", export_base_historical_excel, name="export_base_historical_excel"),
]