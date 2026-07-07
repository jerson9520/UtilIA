from pathlib import Path

import pandas as pd
from django.conf import settings

from core.services.aspect_service import AspectService
from core.services.recommendation_service import RecommendationService
from core.services.prediction_service import PredictionService


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
        self.prediction_service = PredictionService()

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

        ia_catboost = None

        try:
            base_row = df.iloc[0]

            ia_catboost = self.prediction_service.predict(
                marca=filters.get("marca") or base_row.get("marca"),
                linea=filters.get("linea") or base_row.get("linea"),
                anio_modelo=filters.get("anio_modelo") or base_row.get("anio_modelo"),
                codigo_historico=filters.get("codigo_historico") or base_row.get("codigo_historico"),
                valor_norma=base_row.get("valor_norma"),
                tipo_linea=base_row.get("tipo_linea"),
                tipo_servicio=base_row.get("tipo_servicio"),
                tipo_combustible=base_row.get("tipo_combustible"),
                peso_bruto=base_row.get("peso_bruto"),
            )
        except Exception as e:
            ia_catboost = {
                "status": "error",
                "message": str(e),
            }

        decision_ia = self._build_ai_decision(
            ia_historica=ia,
            ia_catboost=ia_catboost,
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
            "ia_catboost": ia_catboost,
            "decision_ia": decision_ia,
            "registros_mostrados": len(registros),
            "registros": registros,
        }

    def _build_ai_decision(self, ia_historica, ia_catboost, nivel_usado=None):
        valor_historico = None
        valor_catboost = None

        if ia_historica:
            valor_historico = ia_historica.get("valor_objetivo")

        if ia_catboost and ia_catboost.get("status") == "ok":
            valor_catboost = ia_catboost.get("valor_predicho")

        if valor_historico is None and valor_catboost is None:
            return {
                "status": "error",
                "message": "No fue posible calcular una decisión IA.",
            }

        if valor_historico is not None and valor_catboost is None:
            return {
                "status": "ok",
                "valor_final": round(float(valor_historico), 2),
                "metodo": "HISTORICO",
                "peso_historico": 1.0,
                "peso_catboost": 0.0,
                "interpretacion": "La decisión se basa únicamente en la base histórica disponible.",
            }

        if valor_historico is None and valor_catboost is not None:
            return {
                "status": "ok",
                "valor_final": round(float(valor_catboost), 2),
                "metodo": "CATBOOST",
                "peso_historico": 0.0,
                "peso_catboost": 1.0,
                "interpretacion": "La decisión se basa únicamente en el modelo IA entrenado.",
            }

        nivel = nivel_usado.get("nivel") if nivel_usado else None
        cantidad = nivel_usado.get("cantidad_encontrada", 0) if nivel_usado else 0

        if nivel == 1 and cantidad >= 200:
            peso_historico = 0.70
            peso_catboost = 0.30
        elif nivel in [1, 2] and cantidad >= 50:
            peso_historico = 0.60
            peso_catboost = 0.40
        elif cantidad >= 30:
            peso_historico = 0.50
            peso_catboost = 0.50
        else:
            peso_historico = 0.30
            peso_catboost = 0.70

        valor_final = (
            float(valor_historico) * peso_historico
            + float(valor_catboost) * peso_catboost
        )

        diferencia = abs(float(valor_historico) - float(valor_catboost))

        return {
            "status": "ok",
            "valor_final": round(valor_final, 2),
            "historico": round(float(valor_historico), 2),
            "catboost": round(float(valor_catboost), 2),
            "diferencia": round(diferencia, 2),
            "metodo": "PROMEDIO_PONDERADO_HISTORICO_CATBOOST",
            "peso_historico": peso_historico,
            "peso_catboost": peso_catboost,
            "interpretacion": (
                "La decisión IA combina la mediana histórica depurada con la predicción "
                "del modelo CatBoost, ponderando más el histórico cuando existen suficientes "
                "registros exactos."
            ),
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