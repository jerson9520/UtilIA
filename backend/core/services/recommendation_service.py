class RecommendationService:
    def build_recommendation(self, df, nivel_usado=None):
        cantidad = int(len(df))

        p5 = float(df["valor_medicion"].quantile(0.05))
        p95 = float(df["valor_medicion"].quantile(0.95))

        df_depurado = df[
            (df["valor_medicion"] >= p5)
            & (df["valor_medicion"] <= p95)
        ].copy()

        mediana_depurada = float(df_depurado["valor_medicion"].median())
        promedio_depurado = float(df_depurado["valor_medicion"].mean())

        rango_ideal = {
            "min": round(float(df_depurado["valor_medicion"].quantile(0.25)), 2),
            "max": round(float(df_depurado["valor_medicion"].quantile(0.75)), 2),
        }

        confianza = self._calculate_confidence(
            cantidad=cantidad,
            nivel=nivel_usado.get("nivel") if nivel_usado else None,
            p5=p5,
            p95=p95,
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
                "p5": round(p5, 2),
                "p95": round(p95, 2),
            },
        }

    def _calculate_confidence(self, cantidad, nivel, p5, p95, mediana):
        dispersion = 0

        if mediana > 0:
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