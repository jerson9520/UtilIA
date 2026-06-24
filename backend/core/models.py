from django.db import models


class MarcaVehiculo(models.Model):
    nombre = models.CharField(max_length=150, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Marca de vehículo"
        verbose_name_plural = "Marcas de vehículos"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class LineaVehiculo(models.Model):
    marca = models.ForeignKey(
        MarcaVehiculo,
        on_delete=models.CASCADE,
        related_name="lineas"
    )
    nombre = models.CharField(max_length=150)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Línea de vehículo"
        verbose_name_plural = "Líneas de vehículos"
        ordering = ["marca__nombre", "nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["marca", "nombre"],
                name="unique_linea_por_marca"
            )
        ]

    def __str__(self):
        return f"{self.marca.nombre} - {self.nombre}"


class GrupoPrueba(models.Model):
    nombre = models.CharField(max_length=200, unique=True)
    descripcion = models.TextField(blank=True, null=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Grupo de prueba"
        verbose_name_plural = "Grupos de prueba"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Aspecto(models.Model):
    class TipoEvaluacion(models.TextChoices):
        MINIMO = "MINIMO", "Mínimo permitido"
        MAXIMO = "MAXIMO", "Máximo permitido"
        RANGO = "RANGO", "Rango permitido"
        REFERENCIAL = "REFERENCIAL", "Referencial"

    codigo = models.CharField(max_length=80, unique=True)
    nombre = models.CharField(max_length=250)
    grupo_prueba = models.ForeignKey(
        GrupoPrueba,
        on_delete=models.PROTECT,
        related_name="aspectos"
    )
    unidad_medida = models.CharField(max_length=50, blank=True, null=True)

    tipo_evaluacion = models.CharField(
        max_length=20,
        choices=TipoEvaluacion.choices,
        default=TipoEvaluacion.REFERENCIAL
    )

    descripcion = models.TextField(blank=True, null=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Aspecto técnico"
        verbose_name_plural = "Aspectos técnicos"
        ordering = ["grupo_prueba__nombre", "codigo"]

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"


class NormativaAspecto(models.Model):
    aspecto = models.ForeignKey(
        Aspecto,
        on_delete=models.CASCADE,
        related_name="normativas"
    )

    nombre_norma = models.CharField(max_length=200)
    version = models.CharField(max_length=100, blank=True, null=True)

    valor_minimo = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        blank=True,
        null=True
    )
    valor_maximo = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        blank=True,
        null=True
    )
    valor_objetivo = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        blank=True,
        null=True
    )

    aplica_desde_modelo = models.IntegerField(blank=True, null=True)
    aplica_hasta_modelo = models.IntegerField(blank=True, null=True)

    tipo_servicio = models.CharField(max_length=120, blank=True, null=True)
    tipo_combustible = models.CharField(max_length=120, blank=True, null=True)
    tipo_linea = models.CharField(max_length=120, blank=True, null=True)

    observacion = models.TextField(blank=True, null=True)
    activo = models.BooleanField(default=True)

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Normativa por aspecto"
        verbose_name_plural = "Normativas por aspecto"
        ordering = ["aspecto__codigo", "nombre_norma"]

    def __str__(self):
        return f"{self.aspecto.codigo} - {self.nombre_norma}"


class HistoricoPruebaVehiculo(models.Model):
    placa = models.CharField(max_length=20, db_index=True)

    marca = models.ForeignKey(
        MarcaVehiculo,
        on_delete=models.PROTECT,
        blank=True,
        null=True
    )
    linea = models.ForeignKey(
        LineaVehiculo,
        on_delete=models.PROTECT,
        blank=True,
        null=True
    )

    modelo = models.IntegerField(blank=True, null=True)
    tipo_servicio = models.CharField(max_length=120, blank=True, null=True)
    tipo_combustible = models.CharField(max_length=120, blank=True, null=True)
    tipo_linea = models.CharField(max_length=120, blank=True, null=True)

    grupo_prueba = models.ForeignKey(
        GrupoPrueba,
        on_delete=models.PROTECT,
        blank=True,
        null=True
    )
    aspecto = models.ForeignKey(
        Aspecto,
        on_delete=models.PROTECT,
        blank=True,
        null=True
    )

    valor_medido = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        blank=True,
        null=True
    )

    valor_norma = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        blank=True,
        null=True
    )

    resultado = models.CharField(max_length=80, blank=True, null=True)
    fecha_prueba = models.DateTimeField(blank=True, null=True)

    datos_originales = models.JSONField(blank=True, null=True)

    fecha_cargue = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Histórico de prueba de vehículo"
        verbose_name_plural = "Histórico de pruebas de vehículos"
        ordering = ["-fecha_prueba"]
        indexes = [
            models.Index(fields=["placa"]),
            models.Index(fields=["modelo"]),
            models.Index(fields=["resultado"]),
            models.Index(fields=["fecha_prueba"]),
        ]

    def __str__(self):
        return f"{self.placa} - {self.aspecto} - {self.valor_medido}"