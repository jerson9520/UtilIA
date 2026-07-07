from pathlib import Path
import json

import pandas as pd
from catboost import CatBoostRegressor
from django.conf import settings


class PredictionService:
    def __init__(self):
        base_dir = Path(settings.BASE_DIR)

        self.model_path = (
            base_dir / "core" / "data" / "models" / "ia_valor_medicion_catboost.cbm"
        )

        self.metrics_path = (
            base_dir / "core" / "data" / "metrics" / "ia_valor_medicion_metrics.json"
        )

        self.features = [
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

        self.model = None
        self.metrics = {}

        self._load()

    def _load(self):
        if not self.model_path.exists():
            raise FileNotFoundError(f"No existe el modelo IA: {self.model_path}")

        self.model = CatBoostRegressor()
        self.model.load_model(str(self.model_path))

        if self.metrics_path.exists():
            with open(self.metrics_path, "r", encoding="utf-8") as f:
                self.metrics = json.load(f)

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
        payload = {
            "marca": str(marca).strip().upper(),
            "linea": str(linea).strip().upper(),
            "anio_modelo": float(anio_modelo),
            "codigo_historico": str(codigo_historico).strip().zfill(6),
            "valor_norma": float(valor_norma),
            "tipo_linea": str(tipo_linea).strip(),
            "tipo_servicio": str(tipo_servicio).strip(),
            "tipo_combustible": str(tipo_combustible).strip(),
            "peso_bruto": float(peso_bruto),
        }

        df = pd.DataFrame([payload], columns=self.features)

        prediction = float(self.model.predict(df)[0])

        return {
            "status": "ok",
            "origen": "IA_CATBOOST",
            "valor_predicho": round(prediction, 4),
            "features": payload,
            "metricas_modelo": self.metrics.get("metrics", {}),
            "modelo": self.model_path.name,
        }