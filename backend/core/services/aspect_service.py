from pathlib import Path
import pandas as pd
from django.conf import settings


class AspectService:
    def __init__(self):
        self.file_path = (
            Path(settings.BASE_DIR)
            / "core"
            / "data"
            / "raw"
            / "Informe_Aspectos.xlsx"
        )

    def _read(self):
        return pd.read_excel(self.file_path, sheet_name="Sheet1")

    def _normalize_dataframe(self, df):
        df = df.copy().fillna("")

        df["codigo_historico"] = (
            df["Codigo grupo"].astype(str).str.replace(".0", "", regex=False).str.strip().str.zfill(2)
            + df["Codigo subgrupo"].astype(str).str.replace(".0", "", regex=False).str.strip().str.zfill(2)
            + df["Codigo aspecto"].astype(str).str.replace(".0", "", regex=False).str.strip().str.zfill(2)
        )

        return df

    def audit(self):
        if not self.file_path.exists():
            return {
                "status": "error",
                "message": "No se encontró Informe_Aspectos.xlsx",
                "path": str(self.file_path),
            }

        df = self._normalize_dataframe(self._read())

        return {
            "status": "ok",
            "file": self.file_path.name,
            "sheet": "Sheet1",
            "rows": len(df),
            "columns_count": len(df.columns),
            "columns": list(df.columns),
            "grupos": sorted(df["Nombre grupo"].dropna().astype(str).unique().tolist()),
            "unidades": sorted(df["Unidad medida"].dropna().astype(str).unique().tolist()),
            "sample": df.head(10).fillna("").astype(str).to_dict(orient="records"),
        }

    def list_aspects(self, grupo=None, unidad=None, codigo_aspecto=None):
        df = self._normalize_dataframe(self._read())

        if grupo:
            df = df[df["Nombre grupo"].astype(str).str.upper().str.contains(grupo.upper(), na=False)]

        if unidad:
            df = df[df["Unidad medida"].astype(str).str.upper() == unidad.upper()]

        if codigo_aspecto:
            df = df[df["codigo_historico"] == str(codigo_aspecto).strip().zfill(6)]

        cols = [
            "codigo_historico",
            "Codigo concat",
            "Nombre aspecto",
            "Nombre grupo",
            "Grupo revision",
            "Unidad medida",
            "Tipo falla",
            "Rango desde",
            "Rango hasta",
            "Codigo norma",
            "Codigo 3625",
        ]

        cols = [c for c in cols if c in df.columns]

        return {
            "status": "ok",
            "rows": len(df),
            "data": df[cols].head(500).fillna("").astype(str).to_dict(orient="records"),
        }

    def get_by_codigo_historico(self, codigo_historico):
        if not codigo_historico:
            return None

        df = self._normalize_dataframe(self._read())
        codigo = str(codigo_historico).strip().zfill(6)

        match = df[df["codigo_historico"] == codigo]

        if match.empty:
            return None

        row = match.iloc[0]

        return {
            "codigo_historico": str(row.get("codigo_historico", "")),
            "codigo_concat": str(row.get("Codigo concat", "")),
            "nombre_aspecto": str(row.get("Nombre aspecto", "")),
            "nombre_grupo": str(row.get("Nombre grupo", "")),
            "grupo_revision": str(row.get("Grupo revision", "")),
            "unidad_medida": str(row.get("Unidad medida", "")),
            "tipo_falla": str(row.get("Tipo falla", "")),
            "rango_desde": str(row.get("Rango desde", "")),
            "rango_hasta": str(row.get("Rango hasta", "")),
            "codigo_norma": str(row.get("Codigo norma", "")),
            "codigo_3625": str(row.get("Codigo 3625", "")),
        }