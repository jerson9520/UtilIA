from pathlib import Path
from threading import Lock

import pandas as pd
from django.conf import settings

from core.services.aspect_service import AspectService
from core.services.recommendation_service import RecommendationService
from core.services.prediction_service import PredictionService


class HistoricalService:
    """
    Servicio de consulta histórica optimizado.

    - Carga el parquet una sola vez por proceso.
    - Mantiene subconjuntos en caché por código histórico.
    - Permite omitir registros detallados en consultas por paquete.
    """

    _dataframe_cache = None
    _codigo_cache = {}
    _load_lock = Lock()
    _codigo_lock = Lock()

    MAX_RECORDS_RESPONSE = 500

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
                "message": (
                    "No se encontró historico_normalizado.parquet. "
                    "Ejecuta build_processed_history."
                ),
                "path": str(self.processed_file_path),
            }

        dataframe = self._load_history()

        return {
            "status": "ok",
            "source": self.processed_file_path.name,
            "rows": int(len(dataframe)),
            "useful_rows": int(len(dataframe)),
            "columns_count": int(len(dataframe.columns)),
            "columns": list(dataframe.columns),
            "marcas_top": (
                dataframe["marca"]
                .value_counts()
                .head(20)
                .to_dict()
            ),
            "lineas_top": (
                dataframe["linea"]
                .value_counts()
                .head(20)
                .to_dict()
            ),
            "codigos_top": (
                dataframe["codigo_historico"]
                .value_counts()
                .head(20)
                .to_dict()
            ),
            "sample_useful": (
                dataframe
                .head(20)
                .fillna("")
                .astype(str)
                .to_dict(orient="records")
            ),
            "cache": {
                "historico_cargado": True,
                "codigos_cacheados": len(
                    HistoricalService._codigo_cache
                ),
            },
        }

    def base_history(
        self,
        marca=None,
        linea=None,
        anio_modelo=None,
        codigo_historico=None,
        include_records=True,
    ):
        if codigo_historico:
            dataframe = self._get_by_codigo(
                codigo_historico
            )
        else:
            dataframe = self._load_history()

        dataframe = self._apply_filters(
            dataframe=dataframe,
            marca=marca,
            linea=linea,
            anio_modelo=anio_modelo,
            codigo_historico=None,
        )

        if dataframe.empty:
            return self._empty_response(
                marca,
                linea,
                anio_modelo,
                codigo_historico,
            )

        return self._build_response(
            dataframe=dataframe,
            filters={
                "marca": marca,
                "linea": linea,
                "anio_modelo": anio_modelo,
                "codigo_historico": codigo_historico,
            },
            nivel_usado=None,
            include_records=include_records,
        )

    def smart_base_history(
        self,
        marca=None,
        linea=None,
        anio_modelo=None,
        codigo_historico=None,
        include_records=True,
    ):
        if not codigo_historico:
            return {
                "status": "error",
                "message": (
                    "El parámetro codigo_historico es obligatorio."
                ),
            }

        dataframe = self._get_by_codigo(
            codigo_historico
        )

        if dataframe.empty:
            return self._empty_response(
                marca,
                linea,
                anio_modelo,
                codigo_historico,
            )

        niveles = [
            {
                "nivel": 1,
                "descripcion": (
                    "Marca + línea + modelo + código histórico"
                ),
                "filtros": {
                    "marca": marca,
                    "linea": linea,
                    "anio_modelo": anio_modelo,
                },
            },
            {
                "nivel": 2,
                "descripcion": (
                    "Marca + línea + código histórico"
                ),
                "filtros": {
                    "marca": marca,
                    "linea": linea,
                },
            },
            {
                "nivel": 3,
                "descripcion": (
                    "Marca + código histórico"
                ),
                "filtros": {
                    "marca": marca,
                },
            },
            {
                "nivel": 4,
                "descripcion": (
                    "Código histórico solamente"
                ),
                "filtros": {},
            },
        ]

        minimum_records = 30
        selected_dataframe = None
        selected_level = None

        for level in niveles:
            temp = self._apply_filters(
                dataframe=dataframe,
                marca=level["filtros"].get("marca"),
                linea=level["filtros"].get("linea"),
                anio_modelo=level["filtros"].get(
                    "anio_modelo"
                ),
                codigo_historico=None,
            )

            if len(temp) >= minimum_records:
                selected_dataframe = temp
                selected_level = {
                    "nivel": level["nivel"],
                    "descripcion": level["descripcion"],
                    "cantidad_encontrada": int(len(temp)),
                    "minimo_requerido": minimum_records,
                }
                break

        if selected_dataframe is None:
            selected_dataframe = dataframe
            selected_level = {
                "nivel": 5,
                "descripcion": (
                    "Mejor esfuerzo con registros disponibles "
                    "del código histórico"
                ),
                "cantidad_encontrada": int(
                    len(dataframe)
                ),
                "minimo_requerido": minimum_records,
            }

        return self._build_response(
            dataframe=selected_dataframe,
            filters={
                "marca": marca,
                "linea": linea,
                "anio_modelo": anio_modelo,
                "codigo_historico": self._normalize_code(
                    codigo_historico
                ),
            },
            nivel_usado=selected_level,
            include_records=include_records,
        )

    def _load_history(self):
        if HistoricalService._dataframe_cache is not None:
            return HistoricalService._dataframe_cache

        with HistoricalService._load_lock:
            if HistoricalService._dataframe_cache is not None:
                return HistoricalService._dataframe_cache

            if not self.processed_file_path.exists():
                raise FileNotFoundError(
                    "No se encontró histórico procesado: "
                    f"{self.processed_file_path}"
                )

            dataframe = pd.read_parquet(
                self.processed_file_path
            )

            dataframe["codigo_historico"] = (
                dataframe["codigo_historico"]
                .astype(str)
                .str.strip()
                .str.replace(".0", "", regex=False)
                .str.zfill(6)
            )

            dataframe["marca"] = (
                dataframe["marca"]
                .astype(str)
                .str.strip()
                .str.upper()
            )

            dataframe["linea"] = (
                dataframe["linea"]
                .astype(str)
                .str.strip()
                .str.upper()
            )

            HistoricalService._dataframe_cache = dataframe

        return HistoricalService._dataframe_cache

    def _get_by_codigo(self, codigo_historico):
        codigo = self._normalize_code(
            codigo_historico
        )

        if codigo in HistoricalService._codigo_cache:
            return HistoricalService._codigo_cache[codigo]

        with HistoricalService._codigo_lock:
            if codigo in HistoricalService._codigo_cache:
                return HistoricalService._codigo_cache[
                    codigo
                ]

            dataframe = self._load_history()

            code_dataframe = dataframe[
                dataframe["codigo_historico"] == codigo
            ].copy()

            HistoricalService._codigo_cache[
                codigo
            ] = code_dataframe

        return HistoricalService._codigo_cache[codigo]

    def _apply_filters(
        self,
        dataframe,
        marca=None,
        linea=None,
        anio_modelo=None,
        codigo_historico=None,
    ):
        filtered = dataframe

        if marca:
            filtered = filtered[
                filtered["marca"]
                == str(marca).strip().upper()
            ]

        if linea:
            filtered = filtered[
                filtered["linea"]
                == str(linea).strip().upper()
            ]

        if anio_modelo is not None and str(
            anio_modelo
        ).strip():
            filtered = filtered[
                filtered["anio_modelo"]
                == float(anio_modelo)
            ]

        if codigo_historico:
            filtered = filtered[
                filtered["codigo_historico"]
                == self._normalize_code(
                    codigo_historico
                )
            ]

        return filtered

    def _build_response(
        self,
        dataframe,
        filters,
        nivel_usado=None,
        include_records=True,
    ):
        if dataframe.empty:
            return self._empty_response(
                filters.get("marca"),
                filters.get("linea"),
                filters.get("anio_modelo"),
                filters.get("codigo_historico"),
            )

        p5 = float(
            dataframe["valor_medicion"].quantile(
                0.05
            )
        )

        p95 = float(
            dataframe["valor_medicion"].quantile(
                0.95
            )
        )

        depurated = dataframe[
            (
                dataframe["valor_medicion"]
                >= p5
            )
            & (
                dataframe["valor_medicion"]
                <= p95
            )
        ]

        if depurated.empty:
            depurated = dataframe

        codigo_historico = filters.get(
            "codigo_historico"
        )

        aspecto = (
            self.aspect_service
            .get_by_codigo_historico(
                codigo_historico
            )
        )

        statistics = {
            "reales": {
                "cantidad": int(len(dataframe)),
                "min": float(
                    dataframe[
                        "valor_medicion"
                    ].min()
                ),
                "max": float(
                    dataframe[
                        "valor_medicion"
                    ].max()
                ),
                "promedio": float(
                    dataframe[
                        "valor_medicion"
                    ].mean()
                ),
                "mediana": float(
                    dataframe[
                        "valor_medicion"
                    ].median()
                ),
                "p5": p5,
                "p95": p95,
            },
            "depuradas": {
                "cantidad": int(len(depurated)),
                "min": float(
                    depurated[
                        "valor_medicion"
                    ].min()
                ),
                "max": float(
                    depurated[
                        "valor_medicion"
                    ].max()
                ),
                "promedio": float(
                    depurated[
                        "valor_medicion"
                    ].mean()
                ),
                "mediana": float(
                    depurated[
                        "valor_medicion"
                    ].median()
                ),
            },
            "recomendacion": {
                "valor_referencia": float(
                    depurated[
                        "valor_medicion"
                    ].median()
                ),
                "metodo": "MEDIANA_DEPURADA",
                "motivo": (
                    "Se usa la mediana del histórico "
                    "depurado para reducir el impacto "
                    "de valores extremos."
                ),
            },
        }

        ia_historica = (
            self.recommendation_service
            .build_recommendation(
                df=dataframe,
                nivel_usado=nivel_usado,
            )
        )

        ia_catboost = self._predict_catboost(
            dataframe=dataframe,
            filters=filters,
        )

        decision_ia = self._build_ai_decision(
            ia_historica=ia_historica,
            ia_catboost=ia_catboost,
            nivel_usado=nivel_usado,
        )

        records = []

        if include_records:
            records = self._serialize_records(
                dataframe
            )

        return {
            "status": "ok",
            "source": (
                self.processed_file_path.name
            ),
            "nivel_usado": nivel_usado,
            "filters": filters,
            "aspecto": aspecto,
            "estadisticas": statistics,
            "ia": ia_historica,
            "ia_catboost": ia_catboost,
            "decision_ia": decision_ia,
            "registros_mostrados": len(records),
            "registros": records,
        }

    def _predict_catboost(
        self,
        dataframe,
        filters,
    ):
        try:
            base_row = dataframe.iloc[0]

            return self.prediction_service.predict(
                marca=(
                    filters.get("marca")
                    or base_row.get("marca")
                ),
                linea=(
                    filters.get("linea")
                    or base_row.get("linea")
                ),
                anio_modelo=(
                    filters.get("anio_modelo")
                    or base_row.get("anio_modelo")
                ),
                codigo_historico=(
                    filters.get(
                        "codigo_historico"
                    )
                    or base_row.get(
                        "codigo_historico"
                    )
                ),
                valor_norma=base_row.get(
                    "valor_norma"
                ),
                tipo_linea=base_row.get(
                    "tipo_linea"
                ),
                tipo_servicio=base_row.get(
                    "tipo_servicio"
                ),
                tipo_combustible=base_row.get(
                    "tipo_combustible"
                ),
                peso_bruto=base_row.get(
                    "peso_bruto"
                ),
            )

        except Exception as exc:
            return {
                "status": "error",
                "message": str(exc),
            }

    def _serialize_records(
        self,
        dataframe,
    ):
        columns = [
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

        available_columns = [
            column
            for column in columns
            if column in dataframe.columns
        ]

        return (
            dataframe[available_columns]
            .head(self.MAX_RECORDS_RESPONSE)
            .fillna("")
            .astype(str)
            .to_dict(orient="records")
        )

    def _normalize_code(
        self,
        codigo_historico,
    ):
        return (
            str(codigo_historico or "")
            .strip()
            .replace("-", "")
            .replace(".0", "")
            .zfill(6)
        )

    def _build_ai_decision(
        self,
        ia_historica,
        ia_catboost,
        nivel_usado=None,
    ):
        valor_historico = None
        valor_catboost = None

        if ia_historica:
            valor_historico = (
                ia_historica.get(
                    "valor_objetivo"
                )
            )

        if (
            ia_catboost
            and ia_catboost.get("status") == "ok"
        ):
            valor_catboost = (
                ia_catboost.get(
                    "valor_predicho"
                )
            )

        if (
            valor_historico is None
            and valor_catboost is None
        ):
            return {
                "status": "error",
                "message": (
                    "No fue posible calcular "
                    "una decisión IA."
                ),
            }

        if (
            valor_historico is not None
            and valor_catboost is None
        ):
            return {
                "status": "ok",
                "valor_final": round(
                    float(valor_historico),
                    2,
                ),
                "metodo": "HISTORICO",
                "peso_historico": 1.0,
                "peso_catboost": 0.0,
                "interpretacion": (
                    "La decisión se basa únicamente "
                    "en la base histórica disponible."
                ),
            }

        if (
            valor_historico is None
            and valor_catboost is not None
        ):
            return {
                "status": "ok",
                "valor_final": round(
                    float(valor_catboost),
                    2,
                ),
                "metodo": "CATBOOST",
                "peso_historico": 0.0,
                "peso_catboost": 1.0,
                "interpretacion": (
                    "La decisión se basa únicamente "
                    "en el modelo IA entrenado."
                ),
            }

        nivel = (
            nivel_usado.get("nivel")
            if nivel_usado
            else None
        )

        cantidad = (
            nivel_usado.get(
                "cantidad_encontrada",
                0,
            )
            if nivel_usado
            else 0
        )

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
            float(valor_historico)
            * peso_historico
            + float(valor_catboost)
            * peso_catboost
        )

        diferencia = abs(
            float(valor_historico)
            - float(valor_catboost)
        )

        return {
            "status": "ok",
            "valor_final": round(
                valor_final,
                2,
            ),
            "historico": round(
                float(valor_historico),
                2,
            ),
            "catboost": round(
                float(valor_catboost),
                2,
            ),
            "diferencia": round(
                diferencia,
                2,
            ),
            "metodo": (
                "PROMEDIO_PONDERADO_"
                "HISTORICO_CATBOOST"
            ),
            "peso_historico": peso_historico,
            "peso_catboost": peso_catboost,
            "interpretacion": (
                "La decisión IA combina la mediana "
                "histórica depurada con la predicción "
                "del modelo CatBoost."
            ),
        }

    def _empty_response(
        self,
        marca,
        linea,
        anio_modelo,
        codigo_historico,
    ):
        return {
            "status": "ok",
            "message": (
                "No se encontraron registros históricos "
                "para el código enviado."
            ),
            "source": (
                self.processed_file_path.name
            ),
            "filters": {
                "marca": marca,
                "linea": linea,
                "anio_modelo": anio_modelo,
                "codigo_historico": (
                    self._normalize_code(
                        codigo_historico
                    )
                ),
            },
            "cantidad": 0,
            "aspecto": (
                self.aspect_service
                .get_by_codigo_historico(
                    codigo_historico
                )
            ),
            "estadisticas": None,
            "ia": None,
            "ia_catboost": None,
            "decision_ia": None,
            "registros_mostrados": 0,
            "registros": [],
        }

    @classmethod
    def clear_cache(cls):
        """
        Usar después de reemplazar historico_normalizado.parquet.
        """
        with cls._load_lock:
            cls._dataframe_cache = None

        with cls._codigo_lock:
            cls._codigo_cache = {}