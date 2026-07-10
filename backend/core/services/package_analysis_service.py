from secrets import SystemRandom
from time import perf_counter


class PackageAnalysisService:
    """
    Analiza varios aspectos en una sola petición.

    Reutiliza HistoricalService y evita devolver cientos de registros
    históricos por cada aspecto.
    """

    def __init__(self, historical_service):
        self.historical_service = historical_service
        self.random = SystemRandom()

    def analyze(self, payload):
        started_at = perf_counter()

        validation_error = self._validate_payload(payload)

        if validation_error:
            return {
                "status": "error",
                "message": validation_error,
                "total_aspectos": 0,
                "aspectos": [],
            }

        marca = str(payload.get("marca")).strip().upper()
        linea = str(payload.get("linea")).strip().upper()
        modelo = payload.get("modelo")
        estacion = payload.get("estacion")
        aspectos = payload.get("aspectos") or []

        resultados = []
        valores_usados = set()

        # Evita repetir la misma consulta si el código viene duplicado
        base_cache = {}

        for position, item in enumerate(aspectos, start=1):
            codigo = self._normalize_code(item.get("codigo"))
            valor_recibido = item.get("valor")

            cache_key = (
                marca,
                linea,
                str(modelo),
                codigo,
            )

            if cache_key not in base_cache:
                base_cache[cache_key] = (
                    self.historical_service.smart_base_history(
                        marca=marca,
                        linea=linea,
                        anio_modelo=modelo,
                        codigo_historico=codigo,
                        include_records=False,
                    )
                )

            base = base_cache[cache_key]

            if base.get("status") != "ok":
                resultados.append(
                    {
                        "codigo": codigo,
                        "status": "error",
                        "message": base.get(
                            "message",
                            "No fue posible analizar el aspecto.",
                        ),
                    }
                )
                continue

            if base.get("cantidad", 1) == 0 or not base.get("estadisticas"):
                aspecto = base.get("aspecto") or {}

                resultados.append(
                    {
                        "codigo": codigo,
                        "aspecto": aspecto.get("nombre_aspecto"),
                        "valor_recibido": valor_recibido,
                        "valor_ia": None,
                        "status": "sin_cobertura",
                        "origen": "SIN_HISTORICO_DISPONIBLE",
                        "confianza": "NO_DISPONIBLE",
                        "message": (
                            "El aspecto existe en el catálogo, pero no cuenta "
                            "con registros históricos para generar una "
                            "recomendación IA respaldada."
                        ),
                    }
                )
                continue

            aspecto = base.get("aspecto") or {}
            decision = base.get("decision_ia") or {}
            ia = base.get("ia") or {}
            rango = ia.get("rango_ideal") or {}
            confianza = (ia.get("confianza") or {}).get("nivel")

            valor_base = (
                decision.get("valor_final")
                if decision.get("valor_final") is not None
                else ia.get("valor_objetivo")
            )

            valor_ia = self._controlled_variation(
                valor_base=valor_base,
                rango=rango,
                valores_usados=valores_usados,
                position=position,
            )

            if valor_ia is not None:
                valores_usados.add(valor_ia)

            resultados.append(
                {
                    "codigo": codigo,
                    "aspecto": aspecto.get("nombre_aspecto"),
                    "valor_recibido": valor_recibido,
                    "valor_ia": valor_ia,
                    "rango_ia": {
                        "min": rango.get("min"),
                        "max": rango.get("max"),
                    },
                    "status": "ok",
                    "origen": "HISTORICO_CATBOOST",
                    "confianza": confianza,
                    "detalle": {
                        "nivel_usado": base.get("nivel_usado"),
                        "depuracion": ia.get("depuracion"),
                        "historico": decision.get("historico"),
                        "catboost": decision.get("catboost"),
                        "metodo": decision.get("metodo"),
                    },
                }
            )

        elapsed_ms = round(
            (perf_counter() - started_at) * 1000,
            2,
        )

        exitosos = sum(
            1
            for item in resultados
            if item.get("status") == "ok"
        )

        sin_cobertura = sum(
            1
            for item in resultados
            if item.get("status") == "sin_cobertura"
        )

        errores = sum(
            1
            for item in resultados
            if item.get("status") == "error"
        )

        return {
            "status": "ok",
            "vehiculo": {
                "marca": marca,
                "linea": linea,
                "modelo": modelo,
                "estacion": estacion,
            },
            "resumen": {
                "total_aspectos": len(resultados),
                "procesados": exitosos,
                "sin_cobertura": sin_cobertura,
                "errores": errores,
                "tiempo_procesamiento_ms": elapsed_ms,
            },
            "aspectos": resultados,
        }

    def _validate_payload(self, payload):
        if not isinstance(payload, dict):
            return "El cuerpo de la petición debe ser un objeto JSON."

        required = [
            "marca",
            "linea",
            "modelo",
            "aspectos",
        ]

        missing = [
            field
            for field in required
            if payload.get(field) is None
        ]

        if missing:
            return (
                "Faltan campos obligatorios: "
                + ", ".join(missing)
            )

        if not isinstance(payload.get("aspectos"), list):
            return "El campo aspectos debe ser una lista."

        if not payload.get("aspectos"):
            return "Debe enviar por lo menos un aspecto."

        return None

    def _normalize_code(self, codigo):
        if codigo is None:
            return ""

        return (
            str(codigo)
            .strip()
            .replace("-", "")
            .zfill(6)
        )

    def _controlled_variation(
        self,
        valor_base,
        rango,
        valores_usados,
        position,
    ):
        """
        Aplica una variación pequeña dentro del rango técnico.

        No modifica la predicción del modelo de manera amplia. Solo evita
        respuestas exactamente repetidas dentro del mismo paquete cuando
        el rango permite una pequeña variación.
        """
        if valor_base is None:
            return None

        valor_base = float(valor_base)

        minimo = rango.get("min")
        maximo = rango.get("max")

        if minimo is None or maximo is None:
            candidate = round(valor_base, 2)
            return self._avoid_duplicate(
                candidate=candidate,
                minimo=None,
                maximo=None,
                valores_usados=valores_usados,
                position=position,
            )

        minimo = float(minimo)
        maximo = float(maximo)
        amplitud = maximo - minimo

        if amplitud <= 0:
            return round(valor_base, 2)

        # Variación máxima del 3 % de la amplitud del rango
        variation = self.random.uniform(
            -0.03,
            0.03,
        ) * amplitud

        candidate = valor_base + variation
        candidate = max(minimo, min(candidate, maximo))
        candidate = round(candidate, 2)

        return self._avoid_duplicate(
            candidate=candidate,
            minimo=minimo,
            maximo=maximo,
            valores_usados=valores_usados,
            position=position,
        )

    def _avoid_duplicate(
        self,
        candidate,
        minimo,
        maximo,
        valores_usados,
        position,
    ):
        if candidate not in valores_usados:
            return candidate

        # Pequeño desplazamiento únicamente para evitar repetición
        adjustment = round(0.01 * position, 2)
        alternatives = [
            round(candidate + adjustment, 2),
            round(candidate - adjustment, 2),
        ]

        for alternative in alternatives:
            if minimo is not None:
                alternative = max(minimo, alternative)

            if maximo is not None:
                alternative = min(maximo, alternative)

            alternative = round(alternative, 2)

            if alternative not in valores_usados:
                return alternative

        return candidate