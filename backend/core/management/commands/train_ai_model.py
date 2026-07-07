from pathlib import Path

import json
import joblib
import pandas as pd

from catboost import CatBoostRegressor
from django.conf import settings
from django.core.management.base import BaseCommand
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


class Command(BaseCommand):
    help = "Entrena modelo IA para predecir valor_medicion desde histórico normalizado."

    def handle(self, *args, **options):
        base_dir = Path(settings.BASE_DIR)

        input_path = base_dir / "core" / "data" / "processed" / "historico_normalizado.parquet"
        model_dir = base_dir / "core" / "data" / "models"
        metrics_dir = base_dir / "core" / "data" / "metrics"

        model_dir.mkdir(parents=True, exist_ok=True)
        metrics_dir.mkdir(parents=True, exist_ok=True)

        model_path = model_dir / "ia_valor_medicion_catboost.cbm"
        metadata_path = metrics_dir / "ia_valor_medicion_metrics.json"

        if not input_path.exists():
            self.stderr.write(self.style.ERROR("No existe historico_normalizado.parquet"))
            return

        self.stdout.write("=" * 100)
        self.stdout.write("ENTRENANDO MODELO IA CDA")
        self.stdout.write("=" * 100)

        df = pd.read_parquet(input_path)

        features = [
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

        target = "valor_medicion"

        df = df[features + [target]].copy()
        df = df.dropna()

        df = df[
            (df[target] > 0)
            & (df["valor_norma"] > 0)
            & (df["anio_modelo"] > 0)
        ].copy()

        # Limpiar extremos globales muy agresivos
        p01 = df[target].quantile(0.01)
        p99 = df[target].quantile(0.99)

        df = df[
            (df[target] >= p01)
            & (df[target] <= p99)
        ].copy()

        self.stdout.write(f"Registros entrenamiento: {len(df):,}")

        X = df[features]
        y = df[target]

        cat_features = [
            "marca",
            "linea",
            "codigo_historico",
            "tipo_linea",
            "tipo_servicio",
            "tipo_combustible",
        ]

        X_train, X_test, y_train, y_test = train_test_split(
            X,
            y,
            test_size=0.2,
            random_state=42,
        )

        model = CatBoostRegressor(
            iterations=800,
            learning_rate=0.08,
            depth=8,
            loss_function="MAE",
            eval_metric="MAE",
            random_seed=42,
            verbose=100,
        )

        model.fit(
            X_train,
            y_train,
            cat_features=cat_features,
            eval_set=(X_test, y_test),
            use_best_model=True,
        )

        predictions = model.predict(X_test)

        mae = mean_absolute_error(y_test, predictions)
        mse = mean_squared_error(y_test, predictions)
        r2 = r2_score(y_test, predictions)

        model.save_model(model_path)

        metadata = {
            "model": str(model_path),
            "target": target,
            "features": features,
            "cat_features": cat_features,
            "rows_total_training": int(len(df)),
            "rows_train": int(len(X_train)),
            "rows_test": int(len(X_test)),
            "metrics": {
                "mae": float(mae),
                "mse": float(mse),
                "r2": float(r2),
            },
        }

        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=4, ensure_ascii=False)

        self.stdout.write("")
        self.stdout.write("=" * 100)
        self.stdout.write("MODELO IA ENTRENADO")
        self.stdout.write("=" * 100)
        self.stdout.write(f"Modelo: {model_path}")
        self.stdout.write(f"Métricas: {metadata_path}")
        self.stdout.write(f"MAE: {mae:.4f}")
        self.stdout.write(f"MSE: {mse:.4f}")
        self.stdout.write(f"R2: {r2:.4f}")