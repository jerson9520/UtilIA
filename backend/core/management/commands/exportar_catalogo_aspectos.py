from pathlib import Path

import duckdb
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Exporta catálogo único de aspectos detectados en el histórico CDA."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            type=str,
            default="/app/core/data/raw/Historico Pruebas/*/data.parquet",
            help="Ruta o patrón glob de archivos parquet.",
        )
        parser.add_argument(
            "--output",
            type=str,
            default="/app/core/data/processed/catalogo_aspectos_detectado.csv",
            help="Ruta de salida CSV.",
        )

    def handle(self, *args, **options):
        path = options["path"]
        output = options["output"]

        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        self.stdout.write(self.style.SUCCESS(f"Leyendo histórico: {path}"))
        self.stdout.write(self.style.SUCCESS(f"Generando catálogo: {output}"))

        con = duckdb.connect(database=":memory:")

        con.execute(f"""
            CREATE OR REPLACE VIEW historico AS
            SELECT *
            FROM read_parquet('{path}', union_by_name=true);
        """)

        query = f"""
            COPY (
                WITH datos AS (
                    SELECT
                        GRUPO,
                        SUBGRUPO,
                        ITEM,
                        'G' || GRUPO || '-SG' || SUBGRUPO || '-IT' || ITEM AS codigo_aspecto,
                        TRY_CAST(REPLACE(VR_MEDICION, ',', '.') AS DOUBLE) AS valor_medido,
                        TRY_CAST(REPLACE(VR_NORMA, ',', '.') AS DOUBLE) AS valor_norma,
                        PLACA,
                        MARCA,
                        LINEA
                    FROM historico
                )
                SELECT
                    codigo_aspecto,
                    GRUPO AS grupo,
                    SUBGRUPO AS subgrupo,
                    ITEM AS item,

                    '' AS nombre_aspecto,
                    'POR_CLASIFICAR' AS categoria_aspecto,
                    'POR_DEFINIR' AS tipo_evaluacion,
                    '' AS unidad_medida,
                    'SI' AS usar_para_modelo,

                    COUNT(*) AS total_registros,
                    COUNT(DISTINCT PLACA) AS total_placas,
                    COUNT(DISTINCT MARCA) AS total_marcas,
                    COUNT(DISTINCT LINEA) AS total_lineas,

                    SUM(CASE WHEN valor_medido IS NOT NULL THEN 1 ELSE 0 END) AS registros_con_medicion,
                    SUM(CASE WHEN valor_medido IS NOT NULL AND valor_medido <> 0 THEN 1 ELSE 0 END) AS registros_medicion_mayor_cero,

                    MIN(valor_medido) AS min_medido,
                    MAX(valor_medido) AS max_medido,
                    AVG(valor_medido) AS promedio_medido,

                    MIN(valor_norma) AS min_norma,
                    MAX(valor_norma) AS max_norma,

                    CASE
                        WHEN SUM(CASE WHEN valor_medido IS NOT NULL AND valor_medido <> 0 THEN 1 ELSE 0 END) = 0
                        THEN 'POSIBLE_VISUAL_O_BINARIO'
                        WHEN MIN(valor_norma) = 0 AND MAX(valor_norma) = 0
                        THEN 'REVISAR_NORMA_CERO'
                        ELSE 'POSIBLE_MECANICO'
                    END AS sugerencia_ia

                FROM datos
                GROUP BY codigo_aspecto, GRUPO, SUBGRUPO, ITEM
                ORDER BY GRUPO, SUBGRUPO, ITEM
            )
            TO '{output}'
            WITH (HEADER, DELIMITER ',');
        """

        con.execute(query)

        total = con.execute("""
            SELECT COUNT(DISTINCT GRUPO || '-' || SUBGRUPO || '-' || ITEM)
            FROM historico;
        """).fetchone()[0]

        con.close()

        self.stdout.write(self.style.SUCCESS("=" * 80))
        self.stdout.write(self.style.SUCCESS(f"Catálogo exportado correctamente. Aspectos detectados: {total}"))
        self.stdout.write(self.style.SUCCESS(f"Archivo generado: {output}"))
        self.stdout.write(self.style.SUCCESS("=" * 80))