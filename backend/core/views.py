from django.http import HttpResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response

from core.services.aspect_service import AspectService
from core.services.historical_service import HistoricalService
from core.services.excel_export_service import ExcelExportService
from core.services.prediction_service import PredictionService
from core.services.package_analysis_service import PackageAnalysisService


aspect_service = AspectService()
historical_service = HistoricalService()
excel_export_service = ExcelExportService()
prediction_service = PredictionService()
package_analysis_service = PackageAnalysisService(historical_service)


@api_view(["GET"])
def audit_aspects(request):
    return Response(aspect_service.audit())


@api_view(["GET"])
def list_aspects(request):
    return Response(
        aspect_service.list_aspects(
            grupo=request.GET.get("grupo"),
            unidad=request.GET.get("unidad"),
            codigo_aspecto=request.GET.get("codigo_aspecto"),
        )
    )


@api_view(["GET"])
def audit_historical(request):
    return Response(historical_service.audit())


@api_view(["GET"])
def base_historical(request):
    return Response(
        historical_service.base_history(
            marca=request.GET.get("marca"),
            linea=request.GET.get("linea"),
            anio_modelo=request.GET.get("anio_modelo"),
            codigo_historico=request.GET.get("codigo_historico"),
        )
    )


@api_view(["GET"])
def smart_base_historical(request):
    return Response(
        historical_service.smart_base_history(
            marca=request.GET.get("marca"),
            linea=request.GET.get("linea"),
            anio_modelo=request.GET.get("anio_modelo"),
            codigo_historico=request.GET.get("codigo_historico"),
        )
    )


@api_view(["GET"])
def export_base_historical_excel(request):
    result = historical_service.smart_base_history(
        marca=request.GET.get("marca"),
        linea=request.GET.get("linea"),
        anio_modelo=request.GET.get("anio_modelo"),
        codigo_historico=request.GET.get("codigo_historico"),
    )

    excel_file = excel_export_service.export_base_history(result)

    response = HttpResponse(
        excel_file.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    response["Content-Disposition"] = 'attachment; filename="base_historica_inteligente.xlsx"'

    return response


@api_view(["GET"])
def predict_ai_value(request):
    result = prediction_service.predict(
        marca=request.GET.get("marca"),
        linea=request.GET.get("linea"),
        anio_modelo=request.GET.get("anio_modelo"),
        codigo_historico=request.GET.get("codigo_historico"),
        valor_norma=request.GET.get("valor_norma"),
        tipo_linea=request.GET.get("tipo_linea"),
        tipo_servicio=request.GET.get("tipo_servicio"),
        tipo_combustible=request.GET.get("tipo_combustible"),
        peso_bruto=request.GET.get("peso_bruto"),
    )

    return Response(result)

@api_view(["POST"])
def analyze_package(request):
    result = package_analysis_service.analyze(request.data)
    return Response(result)