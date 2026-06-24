from pathlib import Path
from io import BytesIO
import zipfile

import pandas as pd
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Inspecciona archivos históricos CDA: parquet, csv, xlsx o zip."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            type=str,
            default=None,
            help="Ruta del archivo o carpeta a inspeccionar. Si no se indica, usa core/data.",
        )
        parser.add_argument(
            "--rows",
            type=int,
            default=5,
            help="Número de filas de muestra.",
        )

    def handle(self, *args, **options):
        rows = options["rows"]

        if options["path"]:
            target_path = Path(options["path"])
        else:
            core_dir = Path(__file__).resolve().parents[2]
            target_path = core_dir / "data"

        self.stdout.write(self.style.SUCCESS(f"Inspeccionando: {target_path}"))

        if not target_path.exists():
            self.stdout.write(self.style.ERROR("La ruta no existe."))
            return

        if target_path.is_dir():
            files = [
                p for p in target_path.iterdir()
                if p.suffix.lower() in [".parquet", ".csv", ".xlsx", ".zip"]
            ]

            if not files:
                self.stdout.write(self.style.WARNING("No se encontraron archivos compatibles."))
                return

            for file_path in files:
                self.inspect_file(file_path, rows)

        else:
            self.inspect_file(target_path, rows)

    def inspect_file(self, file_path: Path, rows: int):
        self.stdout.write("\n" + "=" * 100)
        self.stdout.write(self.style.SUCCESS(f"Archivo: {file_path.name}"))
        self.stdout.write("=" * 100)

        suffix = file_path.suffix.lower()

        try:
            if suffix == ".parquet":
                df = pd.read_parquet(file_path)
                self.print_dataframe_info(df, rows)

            elif suffix == ".csv":
                df = pd.read_csv(file_path, nrows=rows)
                self.print_dataframe_info(df, rows)

            elif suffix == ".xlsx":
                df = pd.read_excel(file_path, nrows=rows)
                self.print_dataframe_info(df, rows)

            elif suffix == ".zip":
                self.inspect_zip(file_path, rows)

            else:
                self.stdout.write(self.style.WARNING("Formato no soportado."))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error inspeccionando archivo: {e}"))

    def inspect_zip(self, file_path: Path, rows: int):
        with zipfile.ZipFile(file_path, "r") as zip_file:
            members = [
                m for m in zip_file.namelist()
                if m.lower().endswith((".parquet", ".csv", ".xlsx"))
            ]

            if not members:
                self.stdout.write(self.style.WARNING("El ZIP no contiene parquet, csv ni xlsx."))
                return

            for member in members:
                self.stdout.write("\n" + "-" * 100)
                self.stdout.write(self.style.SUCCESS(f"Archivo dentro del ZIP: {member}"))
                self.stdout.write("-" * 100)

                with zip_file.open(member) as f:
                    content = f.read()

                try:
                    if member.lower().endswith(".parquet"):
                        df = pd.read_parquet(BytesIO(content))

                    elif member.lower().endswith(".csv"):
                        df = pd.read_csv(BytesIO(content), nrows=rows)

                    elif member.lower().endswith(".xlsx"):
                        df = pd.read_excel(BytesIO(content), nrows=rows)

                    else:
                        continue

                    self.print_dataframe_info(df, rows)

                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Error leyendo {member}: {e}"))

    def print_dataframe_info(self, df: pd.DataFrame, rows: int):
        self.stdout.write(self.style.SUCCESS(f"Filas cargadas en muestra: {len(df)}"))
        self.stdout.write(self.style.SUCCESS(f"Total columnas: {len(df.columns)}"))

        self.stdout.write("\nCOLUMNAS:")
        for i, col in enumerate(df.columns, start=1):
            self.stdout.write(f"{i}. {col} | tipo: {df[col].dtype}")

        self.stdout.write("\nMUESTRA DE DATOS:")
        sample = df.head(rows).fillna("").to_string(index=False)
        self.stdout.write(sample)