from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Construye historico_normalizado.parquet desde los parquet reales del cliente."

    def handle(self, *args, **options):
        raw_dir = Path(settings.BASE_DIR) / "core" / "data" / "raw" / "Historico Pruebas"
        output_dir = Path(settings.BASE_DIR) / "core" / "data" / "processed"
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / "historico_normalizado.parquet"

        parquet_files = sorted(raw_dir.rglob("*.parquet"))

        if not parquet_files:
            self.stderr.write(self.style.ERROR(f"No se encontraron archivos parquet en: {raw_dir}"))
            return

        self.stdout.write("=" * 100)
        self.stdout.write("CONSTRUYENDO HISTÓRICO NORMALIZADO")
        self.stdout.write("=" * 100)
        self.stdout.write(f"Archivos encontrados: {len(parquet_files)}")

        frames = []
        total_original = 0
        total_util = 0

        for file_path in parquet_files:
            self.stdout.write("")
            self.stdout.write(f"Leyendo: {file_path}")

            df = pd.read_parquet(file_path)

            original_rows = len(df)
            total_original += original_rows

            self.stdout.write(f"Registros originales: {original_rows:,}")

            df = self._normalize(df)

            df = df[
                (df["valor_medicion"] > 0)
                & (df["valor_norma"] > 0)
            ].copy()

            util_rows = len(df)
            total_util += util_rows

            self.stdout.write(f"Registros útiles: {util_rows:,}")

            frames.append(df)

            del df

        self.stdout.write("")
        self.stdout.write("Concatenando datasets...")

        final_df = pd.concat(frames, ignore_index=True)

        self.stdout.write(f"Total original: {total_original:,}")
        self.stdout.write(f"Total útil: {total_util:,}")
        self.stdout.write(f"Total consolidado: {len(final_df):,}")

        final_df.to_parquet(output_path, index=False)

        self.stdout.write("")
        self.stdout.write("=" * 100)
        self.stdout.write("HISTÓRICO NORMALIZADO GENERADO")
        self.stdout.write("=" * 100)
        self.stdout.write(str(output_path))

    def _normalize(self, df):
        df = df.copy().fillna("")

        required_columns = [
            "CDA",
            "ANIO_PROCESO",
            "OT",
            "F_PROCESO",
            "PLACA",
            "MARCA",
            "LINEA",
            "GRUPO",
            "SUBGRUPO",
            "ITEM",
            "VR_MEDICION",
            "VR_NORMA",
            "TIPO_LINEA",
            "TIPO_SERVICIO",
            "TIPO_COMBUSTIBL",
            "ANIO_MODELO",
            "PESO_BRUTO",
            "APROBACION",
        ]

        missing = [column for column in required_columns if column not in df.columns]

        if missing:
            raise ValueError(f"Faltan columnas obligatorias: {missing}")

        df["codigo_historico"] = (
            df["GRUPO"].astype(str).str.strip().str.zfill(2)
            + df["SUBGRUPO"].astype(str).str.strip().str.zfill(2)
            + df["ITEM"].astype(str).str.strip().str.zfill(2)
        )

        df["marca"] = df["MARCA"].astype(str).str.strip().str.upper()
        df["linea"] = df["LINEA"].astype(str).str.strip().str.upper()

        df["anio_modelo"] = pd.to_numeric(df["ANIO_MODELO"], errors="coerce")
        df["valor_medicion"] = pd.to_numeric(df["VR_MEDICION"], errors="coerce")
        df["valor_norma"] = pd.to_numeric(df["VR_NORMA"], errors="coerce")
        df["peso_bruto"] = pd.to_numeric(df["PESO_BRUTO"], errors="coerce")

        df["tipo_linea"] = df["TIPO_LINEA"].astype(str).str.strip()
        df["tipo_servicio"] = df["TIPO_SERVICIO"].astype(str).str.strip()
        df["tipo_combustible"] = df["TIPO_COMBUSTIBL"].astype(str).str.strip()

        keep_columns = [
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

        return df[keep_columns]