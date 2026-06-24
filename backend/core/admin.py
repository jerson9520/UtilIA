from django.contrib import admin
from .models import (
    MarcaVehiculo,
    LineaVehiculo,
    GrupoPrueba,
    Aspecto,
    NormativaAspecto,
    HistoricoPruebaVehiculo,
)


@admin.register(MarcaVehiculo)
class MarcaVehiculoAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre", "activo")
    search_fields = ("nombre",)
    list_filter = ("activo",)


@admin.register(LineaVehiculo)
class LineaVehiculoAdmin(admin.ModelAdmin):
    list_display = ("id", "marca", "nombre", "activo")
    search_fields = ("nombre", "marca__nombre")
    list_filter = ("marca", "activo")


@admin.register(GrupoPrueba)
class GrupoPruebaAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre", "activo")
    search_fields = ("nombre",)
    list_filter = ("activo",)


@admin.register(Aspecto)
class AspectoAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "codigo",
        "nombre",
        "grupo_prueba",
        "unidad_medida",
        "tipo_evaluacion",
        "activo",
    )
    search_fields = ("codigo", "nombre", "grupo_prueba__nombre")
    list_filter = ("grupo_prueba", "tipo_evaluacion", "activo")


@admin.register(NormativaAspecto)
class NormativaAspectoAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "aspecto",
        "nombre_norma",
        "version",
        "valor_minimo",
        "valor_maximo",
        "valor_objetivo",
        "activo",
    )
    search_fields = (
        "aspecto__codigo",
        "aspecto__nombre",
        "nombre_norma",
        "version",
    )
    list_filter = (
        "activo",
        "nombre_norma",
        "tipo_servicio",
        "tipo_combustible",
        "tipo_linea",
    )


@admin.register(HistoricoPruebaVehiculo)
class HistoricoPruebaVehiculoAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "placa",
        "marca",
        "linea",
        "modelo",
        "grupo_prueba",
        "aspecto",
        "valor_medido",
        "valor_norma",
        "resultado",
        "fecha_prueba",
    )
    search_fields = (
        "placa",
        "marca__nombre",
        "linea__nombre",
        "aspecto__codigo",
        "aspecto__nombre",
    )
    list_filter = (
        "marca",
        "grupo_prueba",
        "resultado",
        "tipo_servicio",
        "tipo_combustible",
        "fecha_prueba",
    )
    readonly_fields = ("fecha_cargue",)