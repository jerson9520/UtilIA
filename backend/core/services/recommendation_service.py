class RecommendationService:
    def build_recommendation(self, df, nivel_usado=None):
        cantidad = int(len(df))

        df_depurado, depuracion = self._clean_outliers(df)

        mediana_depurada = float(df_depurado["valor_medicion"].median())
        promedio_depurado = float(df_depurado["valor_medicion"].mean())

        rango_ideal = {
            "min": round(float(df_depurado["valor_medicion"].quantile(0.25)), 2),
            "max": round(float(df_depurado["valor_medicion"].quantile(0.75)), 2),
        }

        confianza = self._calculate_confidence(
            cantidad=cantidad,
            nivel=nivel_usado.get("nivel") if nivel_usado else None,
            p5=depuracion.get("limite_inferior"),
            p95=depuracion.get("limite_superior"),
            mediana=mediana_depurada,
        )

        return {
            "valor_objetivo": round(mediana_depurada, 2),
            "rango_ideal": rango_ideal,
            "confianza": confianza,
            "metodo": "HISTORICO_DEPURADO_MEDIANA",
            "criterio": (
                "Se usa la mediana depurada del histórico para reducir el impacto "
                "de valores atípicos y representar mejor el comportamiento esperado."
            ),
            "detalle": {
                "cantidad_base": cantidad,
                "mediana_depurada": round(mediana_depurada, 2),
                "promedio_depurado": round(promedio_depurado, 2),
                "limite_inferior": depuracion.get("limite_inferior"),
                "limite_superior": depuracion.get("limite_superior"),
            },
            "depuracion": depuracion,
        }

    def _clean_outliers(self, df):
        total_original = int(len(df))

        p5 = float(df["valor_medicion"].quantile(0.05))
        p95 = float(df["valor_medicion"].quantile(0.95))

        mediana = float(df["valor_medicion"].median())
        dispersion = 0

        if mediana > 0:
            dispersion = (p95 - p5) / mediana

        if dispersion > 3:
            lower_q = 0.10
            upper_q = 0.90
            metodo = "PERCENTIL_10_90"
        else:
            lower_q = 0.05
            upper_q = 0.95
            metodo = "PERCENTIL_5_95"

        limite_inferior = float(df["valor_medicion"].quantile(lower_q))
        limite_superior = float(df["valor_medicion"].quantile(upper_q))

        df_depurado = df[
            (df["valor_medicion"] >= limite_inferior)
            & (df["valor_medicion"] <= limite_superior)
        ].copy()

        return df_depurado, {
            "metodo": metodo,
            "registros_originales": total_original,
            "registros_utilizados": int(len(df_depurado)),
            "registros_excluidos": int(total_original - len(df_depurado)),
            "limite_inferior": round(limite_inferior, 4),
            "limite_superior": round(limite_superior, 4),
            "dispersion": round(dispersion, 4),
            "motivo": (
                "Se excluyen valores extremos hacia arriba y hacia abajo para evitar "
                "que datos atípicos desvíen el valor recomendado."
            ),
        }

    def _calculate_confidence(self, cantidad, nivel, p5, p95, mediana):
        dispersion = 0

        if mediana > 0 and p5 is not None and p95 is not None:
            dispersion = (p95 - p5) / mediana

        score = 0

        if cantidad >= 1000:
            score += 50
        elif cantidad >= 200:
            score += 40
        elif cantidad >= 50:
            score += 30
        elif cantidad >= 30:
            score += 20
        else:
            score += 10

        if nivel == 1:
            score += 35
        elif nivel == 2:
            score += 25
        elif nivel == 3:
            score += 15
        else:
            score += 5

        if dispersion <= 1:
            score += 15
        elif dispersion <= 2:
            score += 10
        else:
            score += 5

        score = min(score, 100)

        if score >= 85:
            label = "ALTA"
            stars = "★★★★★"
        elif score >= 70:
            label = "MEDIA_ALTA"
            stars = "★★★★☆"
        elif score >= 55:
            label = "MEDIA"
            stars = "★★★☆☆"
        elif score >= 40:
            label = "BAJA"
            stars = "★★☆☆☆"
        else:
            label = "MUY_BAJA"
            stars = "★☆☆☆☆"

        return {
            "score": round(score, 2),
            "nivel": label,
            "estrellas": stars,
            "dispersion": round(dispersion, 4),
        }