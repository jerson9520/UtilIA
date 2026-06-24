from pathlib import Path

import duckdb
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Analiza histórico CDA directamente desde archivos Parquet usando DuckDB."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            type=str,
            default="/app/core/data/raw/Historico Pruebas/*/data.parquet",
            help="Ruta o patrón glob de archivos parquet.",
        )
        parser.add_argument(
            "--top",
            type=int,
            default=20,
            help="Cantidad de registros top a mostrar.",
        )

    def handle(self, *args, **options):
        path = options["path"]
        top = options["top"]

        self.stdout.write(self.style.SUCCESS(f"Analizando histórico: {path}"))

        con = duckdb.connect(database=":memory:")

        con.execute(f"""
            CREATE OR REPLACE VIEW historico AS
            SELECT *
            FROM read_parquet('{path}', union_by_name=true);
        """)

        self.print_total_general(con)
        self.print_por_anio(con)
        self.print_top_marcas(con, top)
        self.print_top_lineas(con, top)
        self.print_top_aspectos(con, top)
        self.print_estadisticas_aspectos(con, top)
        self.print_extremos_sospechosos(con, top)

        con.close()

    def print_section(self, title):
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 100))
        self.stdout.write(self.style.SUCCESS(title))
        self.stdout.write(self.style.SUCCESS("=" * 100))

    def print_rows(self, rows, columns):
        if not rows:
            self.stdout.write("Sin resultados.")
            return

        self.stdout.write(" | ".join(columns))
        self.stdout.write("-" * 100)

        for row in rows:
            self.stdout.write(" | ".join(str(value) for value in row))

    def print_total_general(self, con):
        self.print_section("TOTAL GENERAL")

        query = """
            SELECT
                COUNT(*) AS total_registros,
                COUNT(DISTINCT PLACA) AS total_placas,
                COUNT(DISTINCT MARCA) AS total_marcas,
                COUNT(DISTINCT LINEA) AS total_lineas,
                COUNT(DISTINCT GRUPO || '-' || SUBGRUPO || '-' || ITEM) AS total_aspectos
            FROM historico;
        """

        rows = con.execute(query).fetchall()
        self.print_rows(
            rows,
            ["total_registros", "total_placas", "total_marcas", "total_lineas", "total_aspectos"]
        )

    def print_por_anio(self, con):
        self.print_section("REGISTROS POR AÑO")

        query = """
            SELECT
                ANIO_PROCESO,
                COUNT(*) AS total_registros,
                COUNT(DISTINCT PLACA) AS placas,
                COUNT(DISTINCT OT) AS ordenes_trabajo
            FROM historico
            GROUP BY ANIO_PROCESO
            ORDER BY ANIO_PROCESO;
        """

        rows = con.execute(query).fetchall()
        self.print_rows(rows, ["anio", "total_registros", "placas", "ordenes_trabajo"])

    def print_top_marcas(self, con, top):
        self.print_section(f"TOP {top} MARCAS")

        query = f"""
            SELECT
                MARCA,
                COUNT(*) AS total_registros,
                COUNT(DISTINCT PLACA) AS placas
            FROM historico
            GROUP BY MARCA
            ORDER BY total_registros DESC
            LIMIT {top};
        """

        rows = con.execute(query).fetchall()
        self.print_rows(rows, ["marca", "total_registros", "placas"])

    def print_top_lineas(self, con, top):
        self.print_section(f"TOP {top} LÍNEAS")

        query = f"""
            SELECT
                MARCA,
                LINEA,
                COUNT(*) AS total_registros,
                COUNT(DISTINCT PLACA) AS placas
            FROM historico
            GROUP BY MARCA, LINEA
            ORDER BY total_registros DESC
            LIMIT {top};
        """

        rows = con.execute(query).fetchall()
        self.print_rows(rows, ["marca", "linea", "total_registros", "placas"])

    def print_top_aspectos(self, con, top):
        self.print_section(f"TOP {top} ASPECTOS POR CANTIDAD DE DATOS")

        query = f"""
            SELECT
                GRUPO,
                SUBGRUPO,
                ITEM,
                COUNT(*) AS total_registros,
                COUNT(DISTINCT PLACA) AS placas
            FROM historico
            GROUP BY GRUPO, SUBGRUPO, ITEM
            ORDER BY total_registros DESC
            LIMIT {top};
        """

        rows = con.execute(query).fetchall()
        self.print_rows(rows, ["grupo", "subgrupo", "item", "total_registros", "placas"])

    def print_estadisticas_aspectos(self, con, top):
        self.print_section(f"ESTADÍSTICAS POR ASPECTO - TOP {top}")

        query = f"""
            WITH datos AS (
                SELECT
                    GRUPO,
                    SUBGRUPO,
                    ITEM,
                    TRY_CAST(REPLACE(VR_MEDICION, ',', '.') AS DOUBLE) AS valor_medido,
                    TRY_CAST(REPLACE(VR_NORMA, ',', '.') AS DOUBLE) AS valor_norma
                FROM historico
            )
            SELECT
                GRUPO,
                SUBGRUPO,
                ITEM,
                COUNT(*) AS total,
                MIN(valor_medido) AS min_medido,
                MAX(valor_medido) AS max_medido,
                AVG(valor_medido) AS promedio_medido,
                MIN(valor_norma) AS min_norma,
                MAX(valor_norma) AS max_norma
            FROM datos
            WHERE valor_medido IS NOT NULL
            GROUP BY GRUPO, SUBGRUPO, ITEM
            ORDER BY total DESC
            LIMIT {top};
        """

        rows = con.execute(query).fetchall()
        self.print_rows(
            rows,
            [
                "grupo",
                "subgrupo",
                "item",
                "total",
                "min_medido",
                "max_medido",
                "promedio_medido",
                "min_norma",
                "max_norma",
            ],
        )

    def print_extremos_sospechosos(self, con, top):
        self.print_section(f"VALORES EXTREMOS SOSPECHOSOS - TOP {top}")

        query = f"""
            WITH datos AS (
                SELECT
                    ANIO_PROCESO,
                    PLACA,
                    MARCA,
                    LINEA,
                    GRUPO,
                    SUBGRUPO,
                    ITEM,
                    TRY_CAST(REPLACE(VR_MEDICION, ',', '.') AS DOUBLE) AS valor_medido,
                    TRY_CAST(REPLACE(VR_NORMA, ',', '.') AS DOUBLE) AS valor_norma,
                    F_PROCESO
                FROM historico
            )
            SELECT
                ANIO_PROCESO,
                PLACA,
                MARCA,
                LINEA,
                GRUPO,
                SUBGRUPO,
                ITEM,
                valor_medido,
                valor_norma,
                F_PROCESO
            FROM datos
            WHERE valor_medido IS NOT NULL
              AND ABS(valor_medido) > 0
            ORDER BY ABS(valor_medido) DESC
            LIMIT {top};
        """

        rows = con.execute(query).fetchall()
        self.print_rows(
            rows,
            [
                "anio",
                "placa",
                "marca",
                "linea",
                "grupo",
                "subgrupo",
                "item",
                "valor_medido",
                "valor_norma",
                "fecha",
            ],
        )