from pathlib import Path

import pandas as pd
from django.conf import settings

from core.services.aspect_service import AspectService
from core.services.recommendation_service import RecommendationService


class HistoricalService:
    def __init__(self):
        self.processed_file_path = (
            Path(settings.BASE_DIR)
            / "core"
            / "data"
            / "processed"
            / "historico_normalizado.parquet"
        )

        self.aspect_service = AspectService()
        self.recommendation_service = RecommendationService()

    def audit(self):
        if not self.processed_file_path.exists():
            return {
                "status": "error",
                "message": "No se encontró historico_normalizado.parquet. Ejecuta build_processed_history.",
                "path": str(self.processed_file_path),
            }

        df = pd.read_parquet(self.processed_file_path)

        return {
            "status": "ok",
            "source": self.processed_file_path.name,
            "rows": len(df),
            "useful_rows": len(df),
            "columns_count": len(df.columns),
            "columns": list(df.columns),
            "marcas_top": df["marca"].value_counts().head(20).to_dict(),
            "lineas_top": df["linea"].value_counts().head(20).to_dict(),
            "codigos_top": df["codigo_historico"].value_counts().head(20).to_dict(),
            "sample_useful": df.head(20).fillna("").astype(str).to_dict(orient="records"),
        }

    def base_history(self, marca=None, linea=None, anio_modelo=None, codigo_historico=None):
        df = self._load_history()

        df = self._apply_filters(
            df=df,
            marca=marca,
            linea=linea,
            anio_modelo=anio_modelo,
            codigo_historico=codigo_historico,
        )

        if df.empty:
            return self._empty_response(marca, linea, anio_modelo, codigo_historico)

        return self._build_response(
            df=df,
            filters={
                "marca": marca,
                "linea": linea,
                "anio_modelo": anio_modelo,
                "codigo_historico": codigo_historico,
            },
            nivel_usado=None,
        )

    def smart_base_history(self, marca=None, linea=None, anio_modelo=None, codigo_historico=None):
        df = self._load_history()

        if codigo_historico:
            df = df[df["codigo_historico"] == str(codigo_historico).strip().zfill(6)]

        if df.empty:
            return self._empty_response(marca, linea, anio_modelo, codigo_historico)

        niveles = [
            {
                "nivel": 1,
                "descripcion": "Marca + línea + modelo + código histórico",
                "filtros": {"marca": marca, "linea": linea, "anio_modelo": anio_modelo},
            },
            {
                "nivel": 2,
                "descripcion": "Marca + línea + código histórico",
                "filtros": {"marca": marca, "linea": linea},
            },
            {
                "nivel": 3,
                "descripcion": "Marca + código histórico",
                "filtros": {"marca": marca},
            },
            {
                "nivel": 4,
                "descripcion": "Código histórico solamente",
                "filtros": {},
            },
        ]

        min_registros = 30
        selected_df = None
        selected_level = None

        for nivel in niveles:
            temp = df.copy()
            filtros = nivel["filtros"]

            if filtros.get("marca"):
                temp = temp[temp["marca"] == str(filtros["marca"]).strip().upper()]

            if filtros.get("linea"):
                temp = temp[temp["linea"] == str(filtros["linea"]).strip().upper()]

            if filtros.get("anio_modelo"):
                temp = temp[temp["anio_modelo"] == float(filtros["anio_modelo"])]

            if len(temp) >= min_registros:
                selected_df = temp
                selected_level = {
                    "nivel": nivel["nivel"],
                    "descripcion": nivel["descripcion"],
                    "cantidad_encontrada": int(len(temp)),
                    "minimo_requerido": min_registros,
                }
                break

        if selected_df is None:
            selected_df = df
            selected_level = {
                "nivel": 5,
                "descripcion": "Mejor esfuerzo con registros disponibles del código histórico",
                "cantidad_encontrada": int(len(df)),
                "minimo_requerido": min_registros,
            }

        return self._build_response(
            df=selected_df,
            filters={
                "marca": marca,
                "linea": linea,
                "anio_modelo": anio_modelo,
                "codigo_historico": codigo_historico,
            },
            nivel_usado=selected_level,
        )

    def _load_history(self):
        if not self.processed_file_path.exists():
            raise FileNotFoundError(
                f"No se encontró histórico procesado: {self.processed_file_path}"
            )

        return pd.read_parquet(self.processed_file_path)

    def _apply_filters(self, df, marca=None, linea=None, anio_modelo=None, codigo_historico=None):
        if marca:
            df = df[df["marca"] == str(marca).strip().upper()]

        if linea:
            df = df[df["linea"] == str(linea).strip().upper()]

        if anio_modelo:
            df = df[df["anio_modelo"] == float(anio_modelo)]

        if codigo_historico:
            df = df[df["codigo_historico"] == str(codigo_historico).strip().zfill(6)]

        return df

    def _build_response(self, df, filters, nivel_usado=None):
        p5 = df["valor_medicion"].quantile(0.05)
        p95 = df["valor_medicion"].quantile(0.95)

        df_depurado = df[
            (df["valor_medicion"] >= p5)
            & (df["valor_medicion"] <= p95)
        ].copy()

        codigo_historico = filters.get("codigo_historico")
        aspecto = self.aspect_service.get_by_codigo_historico(codigo_historico)

        estadisticas = {
            "reales": {
                "cantidad": int(len(df)),
                "min": float(df["valor_medicion"].min()),
                "max": float(df["valor_medicion"].max()),
                "promedio": float(df["valor_medicion"].mean()),
                "mediana": float(df["valor_medicion"].median()),
                "p5": float(p5),
                "p95": float(p95),
            },
            "depuradas": {
                "cantidad": int(len(df_depurado)),
                "min": float(df_depurado["valor_medicion"].min()),
                "max": float(df_depurado["valor_medicion"].max()),
                "promedio": float(df_depurado["valor_medicion"].mean()),
                "mediana": float(df_depurado["valor_medicion"].median()),
            },
            "recomendacion": {
                "valor_referencia": float(df_depurado["valor_medicion"].median()),
                "metodo": "MEDIANA_DEPURADA",
                "motivo": "Se usa la mediana del histórico depurado para reducir impacto de valores extremos.",
            },
        }

        ia = self.recommendation_service.build_recommendation(
            df=df,
            nivel_usado=nivel_usado,
        )

        registros = df[
            [
                "CDA",
                "ANIO_PROCESO",
                "OT",
                "F_PROCESO",
                "PLACA",
                "marca",
                "linea",
                "anio_modelo",
                "codigo_historico",
                "valor_medicion",
                "valor_norma",
                "tipo_linea",
                "tipo_servicio",
                "tipo_combustible",
                "peso_bruto",
                "APROBACION",
            ]
        ].head(500).fillna("").astype(str).to_dict(orient="records")

        return {
            "status": "ok",
            "source": self.processed_file_path.name,
            "nivel_usado": nivel_usado,
            "filters": filters,
            "aspecto": aspecto,
            "estadisticas": estadisticas,
            "ia": ia,
            "registros_mostrados": len(registros),
            "registros": registros,
        }

    def _empty_response(self, marca, linea, anio_modelo, codigo_historico):
        return {
            "status": "ok",
            "message": "No se encontraron registros con los filtros enviados.",
            "source": self.processed_file_path.name,
            "filters": {
                "marca": marca,
                "linea": linea,
                "anio_modelo": anio_modelo,
                "codigo_historico": codigo_historico,
            },
            "cantidad": 0,
            "aspecto": self.aspect_service.get_by_codigo_historico(codigo_historico),
            "estadisticas": None,
            "registros": [],
        }