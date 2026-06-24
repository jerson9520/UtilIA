from pathlib import Path
from decimal import Decimal, InvalidOperation
from datetime import datetime, time

import pandas as pd
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import (
    MarcaVehiculo,
    LineaVehiculo,
    GrupoPrueba,
    Aspecto,
    HistoricoPruebaVehiculo,
)


class Command(BaseCommand):
    help = "Carga histórico real CDA desde archivos parquet, csv o xlsx hacia PostgreSQL."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            type=str,
            default=None,
            help="Ruta del archivo o carpeta a cargar.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Cantidad máxima de registros a cargar por archivo.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=1000,
            help="Tamaño del lote para inserción masiva.",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Elimina el histórico antes de cargar.",
        )

    def handle(self, *args, **options):
        path = options["path"]
        limit = options["limit"]
        batch_size = options["batch_size"]
        clear = options["clear"]

        if path:
            target_path = Path(path)
        else:
            core_dir = Path(__file__).resolve().parents[2]
            target_path = core_dir / "data" / "raw"

        self.stdout.write(self.style.SUCCESS(f"Ruta de cargue: {target_path}"))

        if not target_path.exists():
            self.stdout.write(self.style.ERROR("La ruta no existe."))
            return

        if clear:
            self.stdout.write(self.style.WARNING("Eliminando histórico anterior..."))
            HistoricoPruebaVehiculo.objects.all().delete()

        files = self.get_files(target_path)

        if not files:
            self.stdout.write(self.style.WARNING("No se encontraron archivos compatibles."))
            return

        self.stdout.write(self.style.SUCCESS(f"Archivos encontrados: {len(files)}"))

        total_insertados = 0

        marca_cache = {}
        linea_cache = {}
        grupo_cache = {}
        aspecto_cache = {}

        for file_path in files:
            insertados = self.load_file(
                file_path=file_path,
                limit=limit,
                batch_size=batch_size,
                marca_cache=marca_cache,
                linea_cache=linea_cache,
                grupo_cache=grupo_cache,
                aspecto_cache=aspecto_cache,
            )
            total_insertados += insertados

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 80))
        self.stdout.write(self.style.SUCCESS(f"Cargue finalizado. Total registros insertados: {total_insertados}"))
        self.stdout.write(self.style.SUCCESS("=" * 80))

    def get_files(self, target_path: Path):
        extensiones = [".parquet", ".csv", ".xlsx"]

        if target_path.is_file():
            return [target_path] if target_path.suffix.lower() in extensiones else []

        files = []
        for extension in extensiones:
            files.extend(target_path.rglob(f"*{extension}"))

        return sorted(files)

    def load_file(
        self,
        file_path: Path,
        limit,
        batch_size,
        marca_cache,
        linea_cache,
        grupo_cache,
        aspecto_cache,
    ):
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Cargando archivo: {file_path}"))

        try:
            df = self.read_dataframe(file_path)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"No se pudo leer el archivo: {e}"))
            return 0

        if limit:
            df = df.head(limit)

        self.stdout.write(f"Registros encontrados en archivo: {len(df)}")

        registros = []
        insertados = 0

        for _, row in df.iterrows():
            try:
                registro = self.build_historico_from_row(
                    row=row,
                    marca_cache=marca_cache,
                    linea_cache=linea_cache,
                    grupo_cache=grupo_cache,
                    aspecto_cache=aspecto_cache,
                )

                if registro:
                    registros.append(registro)

                if len(registros) >= batch_size:
                    insertados += self.bulk_insert(registros, batch_size)
                    registros = []
                    self.stdout.write(f"Insertados parcial: {insertados}")

            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Registro omitido por error: {e}"))

        if registros:
            insertados += self.bulk_insert(registros, batch_size)

        self.stdout.write(self.style.SUCCESS(f"Insertados desde archivo: {insertados}"))
        return insertados

    def read_dataframe(self, file_path: Path):
        suffix = file_path.suffix.lower()

        if suffix == ".parquet":
            return pd.read_parquet(file_path)

        if suffix == ".csv":
            return pd.read_csv(file_path, dtype=str)

        if suffix == ".xlsx":
            return pd.read_excel(file_path, dtype=str)

        raise ValueError(f"Formato no soportado: {suffix}")

    def build_historico_from_row(
        self,
        row,
        marca_cache,
        linea_cache,
        grupo_cache,
        aspecto_cache,
    ):
        placa = self.clean_text(row.get("PLACA"))
        marca_nombre = self.clean_text(row.get("MARCA"))
        linea_nombre = self.clean_text(row.get("LINEA"))

        grupo_codigo = self.clean_text(row.get("GRUPO"))
        subgrupo_codigo = self.clean_text(row.get("SUBGRUPO"))
        item_codigo = self.clean_text(row.get("ITEM"))

        if not placa:
            return None

        marca = self.get_or_create_marca(marca_nombre, marca_cache)
        linea = self.get_or_create_linea(marca, linea_nombre, linea_cache)
        grupo = self.get_or_create_grupo(grupo_codigo, subgrupo_codigo, grupo_cache)
        aspecto = self.get_or_create_aspecto(
            grupo=grupo,
            grupo_codigo=grupo_codigo,
            subgrupo_codigo=subgrupo_codigo,
            item_codigo=item_codigo,
            aspecto_cache=aspecto_cache,
        )

        fecha_prueba = self.parse_fecha(row.get("F_PROCESO"))

        anio_modelo = self.parse_int(row.get("ANIO_MODELO"))
        valor_medido = self.parse_decimal(row.get("VR_MEDICION"))
        valor_norma = self.parse_decimal(row.get("VR_NORMA"))

        resultado = self.clean_text(row.get("RESULTADO"))

        if not resultado:
            aprobacion = self.clean_text(row.get("APROBACION"))
            status = self.clean_text(row.get("STATUS"))

            if aprobacion:
                resultado = f"APROBACION_{aprobacion}"
            elif status:
                resultado = f"STATUS_{status}"

        datos_originales = self.build_json(row)

        return HistoricoPruebaVehiculo(
            placa=placa,
            marca=marca,
            linea=linea,
            modelo=anio_modelo,
            tipo_servicio=self.clean_text(row.get("TIPO_SERVICIO")),
            tipo_combustible=self.clean_text(row.get("TIPO_COMBUSTIBL")),
            tipo_linea=self.clean_text(row.get("TIPO_LINEA")),
            grupo_prueba=grupo,
            aspecto=aspecto,
            valor_medido=valor_medido,
            valor_norma=valor_norma,
            resultado=resultado,
            fecha_prueba=fecha_prueba,
            datos_originales=datos_originales,
        )

    def get_or_create_marca(self, nombre, cache):
        nombre = nombre or "SIN MARCA"

        if nombre in cache:
            return cache[nombre]

        marca, _ = MarcaVehiculo.objects.get_or_create(nombre=nombre)
        cache[nombre] = marca
        return marca

    def get_or_create_linea(self, marca, nombre, cache):
        nombre = nombre or "SIN LINEA"
        key = f"{marca.id}-{nombre}"

        if key in cache:
            return cache[key]

        linea, _ = LineaVehiculo.objects.get_or_create(
            marca=marca,
            nombre=nombre,
        )

        cache[key] = linea
        return linea

    def get_or_create_grupo(self, grupo_codigo, subgrupo_codigo, cache):
        grupo_codigo = grupo_codigo or "NA"
        subgrupo_codigo = subgrupo_codigo or "NA"

        nombre = f"Grupo {grupo_codigo} - Subgrupo {subgrupo_codigo}"

        if nombre in cache:
            return cache[nombre]

        grupo, _ = GrupoPrueba.objects.get_or_create(nombre=nombre)
        cache[nombre] = grupo
        return grupo

    def get_or_create_aspecto(
        self,
        grupo,
        grupo_codigo,
        subgrupo_codigo,
        item_codigo,
        aspecto_cache,
    ):
        grupo_codigo = grupo_codigo or "NA"
        subgrupo_codigo = subgrupo_codigo or "NA"
        item_codigo = item_codigo or "NA"

        codigo = f"G{grupo_codigo}-SG{subgrupo_codigo}-IT{item_codigo}"

        if codigo in aspecto_cache:
            return aspecto_cache[codigo]

        aspecto, _ = Aspecto.objects.get_or_create(
            codigo=codigo,
            defaults={
                "nombre": f"Aspecto {codigo}",
                "grupo_prueba": grupo,
                "unidad_medida": None,
                "tipo_evaluacion": Aspecto.TipoEvaluacion.REFERENCIAL,
            },
        )

        aspecto_cache[codigo] = aspecto
        return aspecto

    def bulk_insert(self, registros, batch_size):
        with transaction.atomic():
            HistoricoPruebaVehiculo.objects.bulk_create(
                registros,
                batch_size=batch_size,
            )
        return len(registros)

    def clean_text(self, value):
        if value is None:
            return None

        try:
            if pd.isna(value):
                return None
        except Exception:
            pass

        text = str(value).strip()

        if text.lower() in ["", "nan", "none", "null", "nat"]:
            return None

        return " ".join(text.split())

    def parse_decimal(self, value):
        text = self.clean_text(value)

        if not text:
            return None

        text = text.replace(",", ".")

        try:
            return Decimal(text)
        except InvalidOperation:
            return None

    def parse_int(self, value):
        decimal_value = self.parse_decimal(value)

        if decimal_value is None:
            return None

        try:
            return int(decimal_value)
        except Exception:
            return None

    def parse_fecha(self, value):
        text = self.clean_text(value)

        if not text:
            return None

        formatos = ["%Y%m%d", "%Y-%m-%d", "%d/%m/%Y"]

        for formato in formatos:
            try:
                fecha = datetime.strptime(text, formato).date()
                naive_datetime = datetime.combine(fecha, time.min)
                return timezone.make_aware(naive_datetime)
            except ValueError:
                continue

        return None

    def build_json(self, row):
        data = {}

        for key, value in row.items():
            data[str(key)] = self.clean_text(value)

        return data