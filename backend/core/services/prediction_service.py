from pathlib import Path
from threading import Lock
import json

import pandas as pd
from catboost import CatBoostRegressor
from django.conf import settings


class PredictionService:
    """
    Servicio de predicción CatBoost.

    El modelo y las métricas se cargan una sola vez por proceso de Django/Gunicorn.
    """

    _model_cache = None
    _metrics_cache = None
    _load_error = None
    _load_lock = Lock()

    FEATURES = [
        "marca",
        "linea",
        "anio_modelo",
        "codigo_historico",
        "valor_norma",
        "tipo_linea",
        "tipo_servicio",
        "tipo_combustible",
        "peso_bruto",
    ]

    def __init__(self):
        base_dir = Path(settings.BASE_DIR)

        self.model_path = (
            base_dir
            / "core"
            / "data"
            / "models"
            / "ia_valor_medicion_catboost.cbm"
        )

        self.metrics_path = (
            base_dir
            / "core"
            / "data"
            / "metrics"
            / "ia_valor_medicion_metrics.json"
        )

        self.features = self.FEATURES.copy()

        self._load()

    @property
    def model(self):
        return PredictionService._model_cache

    @property
    def metrics(self):
        return PredictionService._metrics_cache or {}

    @property
    def load_error(self):
        return PredictionService._load_error

    def _load(self):
        """
        Carga el modelo una sola vez.

        No genera una excepción durante migrate/check si el modelo todavía
        no existe. El error se devuelve únicamente cuando se intenta predecir.
        """
        if (
            PredictionService._model_cache is not None
            or PredictionService._load_error is not None
        ):
            return

        with PredictionService._load_lock:
            if (
                PredictionService._model_cache is not None
                or PredictionService._load_error is not None
            ):
                return

            if not self.model_path.exists():
                PredictionService._load_error = (
                    f"No existe el modelo IA: {self.model_path}"
                )
                PredictionService._metrics_cache = {}
                return

            try:
                model = CatBoostRegressor()
                model.load_model(str(self.model_path))

                PredictionService._model_cache = model
                PredictionService._load_error = None

                if self.metrics_path.exists():
                    with open(
                        self.metrics_path,
                        "r",
                        encoding="utf-8",
                    ) as file:
                        PredictionService._metrics_cache = json.load(file)
                else:
                    PredictionService._metrics_cache = {}

            except Exception as exc:
                PredictionService._model_cache = None
                PredictionService._metrics_cache = {}
                PredictionService._load_error = (
                    f"No fue posible cargar el modelo IA: {exc}"
                )

    def reload(self):
        """
        Permite recargar el modelo después de un entrenamiento sin reiniciar
        manualmente la clase. En producción normalmente se reinicia Gunicorn.
        """
        with PredictionService._load_lock:
            PredictionService._model_cache = None
            PredictionService._metrics_cache = None
            PredictionService._load_error = None

        self._load()

    def predict(
        self,
        marca,
        linea,
        anio_modelo,
        codigo_historico,
        valor_norma,
        tipo_linea,
        tipo_servicio,
        tipo_combustible,
        peso_bruto,
    ):
        if self.model is None:
            return {
                "status": "error",
                "origen": "IA_CATBOOST",
                "message": self.load_error or "Modelo IA no disponible.",
                "modelo": self.model_path.name,
            }

        try:
            payload = self._build_payload(
                marca=marca,
                linea=linea,
                anio_modelo=anio_modelo,
                codigo_historico=codigo_historico,
                valor_norma=valor_norma,
                tipo_linea=tipo_linea,
                tipo_servicio=tipo_servicio,
                tipo_combustible=tipo_combustible,
                peso_bruto=peso_bruto,
            )
        except (TypeError, ValueError) as exc:
            return {
                "status": "error",
                "origen": "IA_CATBOOST",
                "message": f"Datos de entrada inválidos: {exc}",
                "modelo": self.model_path.name,
            }

        dataframe = pd.DataFrame(
            [payload],
            columns=self.features,
        )

        try:
            prediction = float(self.model.predict(dataframe)[0])
        except Exception as exc:
            return {
                "status": "error",
                "origen": "IA_CATBOOST",
                "message": f"No fue posible ejecutar la predicción: {exc}",
                "modelo": self.model_path.name,
            }

        return {
            "status": "ok",
            "origen": "IA_CATBOOST",
            "valor_predicho": round(prediction, 4),
            "features": payload,
            "metricas_modelo": self.metrics.get("metrics", {}),
            "modelo": self.model_path.name,
        }

    def _build_payload(
        self,
        marca,
        linea,
        anio_modelo,
        codigo_historico,
        valor_norma,
        tipo_linea,
        tipo_servicio,
        tipo_combustible,
        peso_bruto,
    ):
        required_values = {
            "marca": marca,
            "linea": linea,
            "anio_modelo": anio_modelo,
            "codigo_historico": codigo_historico,
            "valor_norma": valor_norma,
            "tipo_linea": tipo_linea,
            "tipo_servicio": tipo_servicio,
            "tipo_combustible": tipo_combustible,
            "peso_bruto": peso_bruto,
        }

        missing = [
            key
            for key, value in required_values.items()
            if value is None or str(value).strip() == ""
        ]

        if missing:
            raise ValueError(
                f"Faltan campos obligatorios: {', '.join(missing)}"
            )

        return {
            "marca": str(marca).strip().upper(),
            "linea": str(linea).strip().upper(),
            "anio_modelo": float(anio_modelo),
            "codigo_historico": (
                str(codigo_historico)
                .strip()
                .replace("-", "")
                .zfill(6)
            ),
            "valor_norma": float(valor_norma),
            "tipo_linea": str(tipo_linea).strip(),
            "tipo_servicio": str(tipo_servicio).strip(),
            "tipo_combustible": str(tipo_combustible).strip(),
            "peso_bruto": float(peso_bruto),
        }