# Protocolo Operativo para Agentes AI (AGENTS.md)

Gestión de comprobantes, liquidaciones, recetas e historiales médicos familiares configurados en la tabla de beneficiarios (Sección 3).

> [!IMPORTANT]
> **RESTRICCIÓN DE ALCANCE:**
> El agente solo tiene autorización de acceso al directorio raíz de este repositorio y a `~/Downloads`.
> Está prohibido inspeccionar o modificar otros directorios del sistema, crear carpetas ocultas (`.agents`, `.claude`) o duplicar `AGENTS.md` en subdirectorios. Todos los scripts y binarios viven en `tools/` y los ejecuta el agente internamente.

---

## 1. Ingesta desde `~/Downloads`

Ante cualquier solicitud de procesar nuevos documentos o liquidaciones, ejecutar primero:

```bash
python3 tools/pendientes.py --scan-downloads --minutes 60
```

1. **Clasificación y destino según tipo de archivo:**
   * `Comprobante-Liquidacion-XXXXXXXXX.pdf` (9 dígitos): ejecutar `python3 tools/pendientes.py --match-liquidaciones` para cruzarlo y moverlo a su carpeta en `1 a isapre/`.
   * `WhatsApp Image YYYY-MM-DD at HH.MM.SS.jpeg` (y variantes) o `.pdf` de boletas, bonos, facturas y órdenes médicas: extraer texto (`--extract`), crear su subcarpeta en `0 INBOX/`, mover (`mv`) el archivo renombrado adentro y generar su `.txt`.
   * Recetas médicas permanentes: mover (`mv`) a `RECETAS/` con nombre estandarizado y generar obligatoriamente su archivo `.txt` homónimo (si algún archivo en `RECETAS/` no tiene su `.txt`, extraer su texto con `--extract` y generarlo). Si renueva una receta anterior del mismo tratamiento, mover la anterior (junto con su `.txt`) a `RECETAS/archivadas/`.
2. **Regla de movimiento (`mv`):**
   * Todo archivo tomado desde `~/Downloads` debe **moverse (`mv`)** a su destino. Prohibido usar `cp` desde `~/Downloads` o dejar copias allí.

---

## 2. Extracción de Texto

```bash
python3 tools/pendientes.py --extract "<ruta_archivo>"
```

1. **Archivos `.pdf`:** Ejecuta `pdftotext -layout` por defecto.
2. **Imágenes (`.jpeg`, `.jpg`, `.png`) o PDFs escaneados (`< 20` caracteres):** Ejecuta el binario `tools/ocr` (si no existe o cambió `tools/ocr.swift`, se compila automáticamente con `swiftc -O tools/ocr.swift -o tools/ocr`).
3. **Fechas:** Usar siempre la fecha real de emisión del documento (`YYYYMMDD` en nombres de carpetas/archivos y `YYYY-MM-DD` en el campo `FECHA` del `.txt`), nunca la fecha de descarga.

---

## 3. Pacientes, RUTs y Circuitos

| Paciente | RUT | Rol | Consultas y Exámenes | Medicamentos | Historial Anual |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Nombre Apellido Titular** | `11111111-1` | Titular | `ISAPRE_SURA` | `SOLO_SURA` | [HISTORIAL_TITULAR.md](HISTORIAL_TITULAR.md) |
| **Nombre Apellido Carga Uno** | `22222222-2` | Carga | `ISAPRE_SURA` | `SOLO_SURA` | [HISTORIAL_CARGA_1.md](HISTORIAL_CARGA_1.md) |
| **Nombre Apellido Carga Dos** | `33333333-3` | Carga solo Isapre | `SOLO_ISAPRE` | No cubierto | [HISTORIAL_CARGA_2.md](HISTORIAL_CARGA_2.md) |

---

## 4. Circuitos de Reembolso

### Nivel 0: Pagos o Transferencias Pendientes de Boleta (`ESTADO: PENDIENTE_BOLETA`)
* Cuando el usuario informe que transfirió/pagó a un profesional pero aún no recibe la boleta (con o sin comprobante de transferencia en `~/Downloads`):
  1. Crear la subcarpeta en `0 INBOX/YYYYMMDD_Consulta_[Especialidad]_[Dr_Nombre]/` (moviendo adentro el comprobante de transferencia si existe).
  2. Generar su archivo `.txt` con `ESTADO: PENDIENTE_BOLETA`, `FOLIO_BOLETA: PENDIENTE` y `MONTO_TOTAL: <monto_transferido>`.
  3. Cuando el médico envíe la boleta y esté en `~/Downloads`, moverla (`mv`) a esa misma carpeta en `0 INBOX/`, actualizar `FOLIO_BOLETA` y cambiar `ESTADO: PENDIENTE_ISAPRE` (o `PENDIENTE_SURA`).

### `ISAPRE_SURA` (Consultas, Exámenes y Hospitalizaciones con cobertura Isapre + Seguro Complementario)
1. **Ingreso a Isapre (`0 INBOX` -> `1 a isapre`):**
   * El usuario sube los documentos a [Sucursal Virtual Banmédica](https://www.banmedica.cl/sucursal-virtual/) e informa el ID (`6000...`, 12 dígitos).
   * El agente actualiza `ID_ISAPRE` y `ESTADO: EN_ISAPRE` en el `.txt`, y mueve la carpeta a `1 a isapre/<Nombre_Carpeta> <ID_Isapre>`.
2. **Cruce de Liquidación (`~/Downloads` -> `1 a isapre`):**
   ```bash
   python3 tools/pendientes.py --match-liquidaciones
   ```
   * Cruza `Comprobante-Liquidacion-XXXXXXXXX.pdf` por `FOLIO_BOLETA`, mueve (`mv`) el PDF a su carpeta en `1 a isapre/` y actualiza en el `.txt`: `LIQUIDACION_ISAPRE`, `BONIFICACION_ISAPRE`, `COPAGO_ISAPRE`, `ESTIMADO_SURA_80` (`round(0.80 * Copago_Isapre)`) y `ESTADO: LISTO_PARA_SURA`.
3. **Envío a SURA (`1 a isapre` -> `2 a SURA`):**
   * Los archivos de la carpeta se mantienen individuales (prohibido unirlos en un solo PDF) para enviarlos uno por uno en [WhatsApp SURA](https://wa.me/56994041806).
   * Al guiar cada envío a SURA, el agente debe:
     1. Copiar el RUT del paciente al portapapeles: `python3 tools/pendientes.py --copy-rut <paciente>`
     2. Indicar el nombre exacto del directorio y listar los archivos individuales a arrastrar (excluyendo el `.txt`).
   * Cuando el usuario entrega el ID SURA (8 dígitos), el agente actualiza `ID_SURA` y `ESTADO: EN_SURA` en el `.txt`, y mueve la carpeta a `2 a SURA/<Nombre_Carpeta> <ID_Isapre> <ID_SURA>`.
4. **Pago SURA (`2 a SURA` -> `3 pagadas`):**
   * Al confirmarse el depósito, el agente actualiza `PAGADO_SURA: <monto>` y `ESTADO: PAGADO` en el `.txt`, y luego mueve la carpeta a `3 pagadas/`.

### `SOLO_SURA` (Medicamentos con cobertura directa en Seguro Complementario)
* Para medicamentos permanentes, copiar (`cp`, conservando el original en `RECETAS/`) la receta vigente desde `RECETAS/` hacia la carpeta del medicamento en `0 INBOX/`.
* Seguir el paso de envío a SURA (copiar RUT con `--copy-rut`, indicar directorio y archivos) y, con el ID SURA (8 dígitos), actualizar el `.txt` (`ESTADO: EN_SURA`) y mover de `0 INBOX` a `2 a SURA/<Nombre_Carpeta> <ID_SURA>`.

### `SOLO_ISAPRE` (Consultas y Exámenes con cobertura exclusiva en Isapre)
* Ingresan a `0 INBOX`. Apenas el usuario entrega el ID Banmédica (`6000...`), el agente actualiza `ID_ISAPRE: <ID>` y `ESTADO: PAGADO` en el `.txt`, y mueve la carpeta directamente a `3 pagadas/<Nombre_Carpeta> <ID_Isapre>`.

### Inmutabilidad de `3 pagadas`
* `3 pagadas` es de solo lectura. Prohibido editar, renombrar o recalcular cualquier archivo o carpeta que ya esté dentro de `3 pagadas`.

---

## 5. Nomenclatura

* **Archivos:** `YYYYMMDD_[Tipo_Documento]_[Detalle]_[Proveedor].[ext]`
* **Recetas en `RECETAS/`:** `YYYYMMDD_Receta_[Med1]_[Med2]_[Profesional].[ext]`
* **Subcarpetas:**
  * Consultas: `YYYYMMDD_Consulta_[Especialidad]_[Dr_Nombre]`
  * Medicamentos: `YYYYMMDD_Medicamentos_[Med1]_[Med2]`
  * Exámenes/Derivaciones: `YYYYMMDD_Derivacion_[Examen]_[Proveedor]`
  * Hospitalizaciones: `YYYYMMDD_[Procedimiento]_[Paciente]_[Año]`

---

## 6. Formato del Archivo `.txt`

Todo directorio y toda receta en `RECETAS/` debe tener obligatoriamente un archivo `.txt` que lo resuma (homónimo al documento principal), con formato `CLAVE: VALOR`:

```text
PACIENTE: Nombre Apellido Carga Uno
RUT_PACIENTE: 22222222-2
PRESTACION: Consulta Especialidad Médica
PROVEEDOR: Dr. Nombre Profesional (Especialidad)
FECHA: 2026-09-30
FOLIO_BOLETA: 1450
CIRCUITO: ISAPRE_SURA
ESTADO: EN_SURA
ID_ISAPRE: 600012345678
LIQUIDACION_ISAPRE: 390000000
ID_SURA: 20000000
MONTO_TOTAL: 250000
BONIFICACION_ISAPRE: 32800
COPAGO_ISAPRE: 217200
ESTIMADO_SURA_80: 173760
PAGADO_SURA: PENDIENTE
NOTAS:
- Detalle breve.
```

* **Montos numéricos:** Enteros sin `$` ni puntos. Usar `0` cuando un monto aún no se conoce (ej. `BONIFICACION_ISAPRE: 0` antes de liquidar).
* **IDs o pagos no asignados aún:** Usar `PENDIENTE` o `N/A` (en `SOLO_SURA`, usar `ID_ISAPRE: N/A` y `LIQUIDACION_ISAPRE: N/A`).
* `CIRCUITO`: `ISAPRE_SURA` | `SOLO_SURA` | `SOLO_ISAPRE`
* `ESTADO`: `PENDIENTE_BOLETA` | `PENDIENTE_ISAPRE` | `PENDIENTE_SURA` | `EN_ISAPRE` | `LISTO_PARA_SURA` | `EN_SURA` | `PAGADO` | `VIGENTE` | `ARCHIVADA` | `ORDEN_VIGENTE`
* **Soporte `LEGACY: true`:** Si un archivo `.txt` contiene el campo `LEGACY: true`, el script y el agente asumen que es texto libre y deben leer todo el contenido del `.txt` para tomar decisiones.

---

## 7. Actualización de Estado e Historiales

Tras crear, editar o mover cualquier carpeta, o cuando el usuario consulte qué hay pendiente, ejecutar:

```bash
python3 tools/pendientes.py --update
```

Actualiza [`PENDIENTES_MEDICOS.md`](PENDIENTES_MEDICOS.md) y los historiales anuales configurados en la Sección 3 (`HISTORIAL_<BENEFICIARIO>.md`).

---

## 8. Autoevaluación y Mantenimiento

1. **Salud de herramientas:** Si `pdftotext`, `tools/ocr` o algún script falla o requiere recompilación, informarlo en esa misma respuesta y ofrecer repararlo de inmediato.
2. **Auditoría de desvíos:** Revisar la salida `[SALUD DE HERRAMIENTAS Y AUDITORÍA DE PROCESO]` de `tools/pendientes.py` y proponer corregir cualquier alerta detectada.
3. **Mejora continua y registro de cambios:** Cuando aparezca un paso manual repetitivo, un formato de documento no reconocido o un caso fuera de regla, informarlo en esa misma respuesta (tras completar la tarea en curso), ofrecer actualizar `tools/pendientes.py` o `AGENTS.md`, y registrar el cambio en [`tools/changelog.md`](tools/changelog.md) (documentando exclusivamente cambios técnicos de flujo/scripts; **prohibido incluir nombres de beneficiarios, RUTs, médicos o datos de reembolsos personales**).
