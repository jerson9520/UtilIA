import random


class PackageAnalysisService:
    def __init__(self, historical_service):
        self.historical_service = historical_service

    def analyze(self, payload):
        marca = payload.get("marca")
        linea = payload.get("linea")
        modelo = payload.get("modelo")
        estacion = payload.get("estacion")
        aspectos = payload.get("aspectos") or []

        resultados = []

        for item in aspectos:
            codigo = str(item.get("codigo")).strip().zfill(6)
            valor_recibido = item.get("valor")

            base = self.historical_service.smart_base_history(
                marca=marca,
                linea=linea,
                anio_modelo=modelo,
                codigo_historico=codigo,
            )

            if base.get("status") != "ok":
                resultados.append({
                    "codigo": codigo,
                    "status": "error",
                    "message": base.get("message", "No fue posible analizar el aspecto."),
                })
                continue

            aspecto = base.get("aspecto") or {}
            decision = base.get("decision_ia") or {}
            ia = base.get("ia") or {}
            rango = ia.get("rango_ideal") or {}
            confianza = (ia.get("confianza") or {}).get("nivel")

            valor_base = decision.get("valor_final") or ia.get("valor_objetivo")
            valor_ia = self._controlled_variation(valor_base, rango, codigo)

            resultados.append({
                "codigo": codigo,
                "aspecto": aspecto.get("nombre_aspecto"),
                "valor_recibido": valor_recibido,
                "valor_ia": valor_ia,
                "rango_ia": {
                    "min": rango.get("min"),
                    "max": rango.get("max"),
                },
                "origen": "HISTORICO_CATBOOST",
                "confianza": confianza,
                "detalle": {
                    "nivel_usado": base.get("nivel_usado"),
                    "depuracion": ia.get("depuracion"),
                    "historico": decision.get("historico"),
                    "catboost": decision.get("catboost"),
                },
            })

        return {
            "status": "ok",
            "vehiculo": {
                "marca": marca,
                "linea": linea,
                "modelo": modelo,
                "estacion": estacion,
            },
            "total_aspectos": len(resultados),
            "aspectos": resultados,
        }

    def _controlled_variation(self, valor_base, rango, codigo):
        if valor_base is None:
            return None

        valor_base = float(valor_base)

        minimo = rango.get("min")
        maximo = rango.get("max")

        if minimo is None or maximo is None:
            return round(valor_base, 2)

        minimo = float(minimo)
        maximo = float(maximo)

        amplitud = maximo - minimo

        if amplitud <= 0:
            return round(valor_base, 2)

        random.seed(str(codigo))

        variacion = random.uniform(-0.08, 0.08) * amplitud
        valor = valor_base + variacion

        valor = max(minimo, min(valor, maximo))

        return round(valor, 2)