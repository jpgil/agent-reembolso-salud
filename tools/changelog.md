# Changelog

Todos los cambios relevantes en las herramientas (`tools/`) y en el protocolo operativo del flujo (`AGENTS.md`) se registran en este archivo.
El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

## [2026-10-30]

### Added
- **Nivel 0 (`ESTADO: PENDIENTE_BOLETA`) en `0 INBOX/`:** Seguimiento de pagos o transferencias realizados a prestadores médicos que aún no han emitido boleta, calculando los días de espera y mostrándolos como alerta prioritaria en `tools/pendientes.py` y `PENDIENTES_MEDICOS.md`.
- **Binario nativo `tools/ocr`:** Compilado con optimización (`swiftc -O tools/ocr.swift -o tools/ocr`) para acelerar el OCR con Apple Vision y reducir la latencia de arranque (~0.18 s vs ~1.05 s interpretado).
- **Motor de extracción híbrido (`--extract` en `tools/pendientes.py`):** Prioriza `pdftotext -layout` para archivos `.pdf` (~40 ms, preservando tablas horizontales) con fallback automático a `tools/ocr` para imágenes o PDFs escaneados (`< 20` caracteres) y recompilación automática si cambia `tools/ocr.swift`.
- **Ingesta y cruce automático desde `~/Downloads` (`--scan-downloads`, `--match-liquidaciones`):** Detección de imágenes de WhatsApp (`WhatsApp Image...`), liquidaciones (`Comprobante-Liquidacion-XXXXXXXXX.pdf`) y PDFs recientes; cruce automático por `FOLIO_BOLETA` y movimiento estricto (`mv`) hacia `1 a isapre/`.
- **Asistencia para envío a SURA (`--copy-rut`):** Copia al portapapeles (`pbcopy`) del RUT sin puntos y con guión del beneficiario consultado (incluyendo coincidencia dinámica por nombre, siglas o RUT).
- **Historiales médicos anuales por beneficiario (`--historiales`):** Generación automática de archivos `HISTORIAL_<PERSONA>.md` con vista simplificada de 3 columnas (`Fecha`, `Especialidad / Examen / Medicamento(s)`, `Médico / Centro`) y control de vigencia a 180 días de recetas permanentes.
- **Auditoría de salud y desvíos (`--health`):** Verificación automática de `pdftotext`, `tools/ocr`, cumplimiento de circuitos (`ISAPRE_SURA`, `SOLO_SURA`, `SOLO_ISAPRE`), existencia obligatoria de `.txt` en `RECETAS/` y directorios activos, cuadratura matemática de montos y archivos pendientes en `~/Downloads`.

### Changed
- **Historiales con columna `Fuente` y más secciones:** cada fila indica el `.txt` del que salió (consultas y terapias, procedimientos/cirugías/hospitalizaciones, exámenes, medicamentos y recetas vigentes). Las filas previas con 3 columnas se siguen leyendo.
- **Selección del `.txt` resumen por carpeta:** se prefiere el homónimo a la carpeta, luego el primero con `PACIENTE:`; ya no se toma el primero alfabético.
- **Asignación de paciente en historiales:** se usa `PACIENTE`/`RUT_PACIENTE`; el texto libre solo si faltan (evita asignar al titular las atenciones de las cargas).
- **`generate_patient_histories(..., merge_existing=False)`** permite reconstruir un historial solo desde los `.txt` (uso puntual, sin flag de CLI).
- **Ventana de historiales:** pasa de 366 días móviles a "desde el día 1 del mes de hace un año".
- **`--update` regenera también los historiales**, como indica `AGENTS.md` §7.
- **Mantención puntual:** se generaron los `.txt` resumen faltantes (homónimos a la carpeta) de las carpetas de `3 pagadas` dentro de la ventana y se reconstruyeron los historiales solo desde los `.txt`. No es un proceso recurrente ni una excepción a la inmutabilidad de `3 pagadas`.
- **`AGENTS.md`:** §6 (resumen homónimo a la carpeta, nombres únicos, renombrar al mover) y §7 (lógica, ventana, secciones y columna `Fuente` de los historiales); §8.3 refuerza el registro en el changelog.
- **Historiales: filas manuales protegidas:** al regenerar se leen y conservan filas con fecha con o sin backticks y de 2 a 4 columnas; las secciones desconocidas se conservan como "Otros registros". `AGENTS.md` §7 prohíbe regenerar ignorando las filas previas.
- **Formato de filas de historiales:** fecha sin backticks, prestación corta, solo el nombre del profesional y `Fuente` entre backticks (`shorten_history_text`, `history_row`). Las filas existentes se convirtieron una vez a este formato. Si una fila ya existe con la misma fuente, se conserva la existente (protege ediciones manuales y evita duplicados).
- **0% Hardcoding en `tools/pendientes.py`:** Eliminados los diccionarios y heurísticas fijas de pacientes, RUTs, médicos y medicamentos; los beneficiarios y sus circuitos se cargan dinámicamente desde la tabla Markdown de `AGENTS.md`.
- **Formato `.txt` simplificado (`CLAVE: VALOR`) y soporte `LEGACY: true`:** Reemplazo de la plantilla extensa de 60 líneas por un bloque plano de claves en mayúsculas con montos enteros puros, manteniendo soporte para texto libre mediante la marca `LEGACY: true`.
- **Consolidación de `AGENTS.md`:** Unificado en un único archivo `AGENTS.md` en la raíz del repositorio con reglas deterministas sin ambigüedades conversacionales.

- **Soporte de Claude Code además de `agy`:** `tools/agent-reembolso.sh` elige agente con `REEMBOLSO_AGENTE` y se agrega `tools/claude-agents-md-hook.sh`, hook `SessionStart` que carga `AGENTS.md` en Claude Code sin usar `CLAUDE.md`. `INSTALL.md` documenta ambos caminos.

### Fixed
- **`--historiales` ya no borra filas previas:** el generador reescribía cada `HISTORIAL_<PERSONA>.md` solo con lo hallado en `.txt` de `0 INBOX`–`3 pagadas`. Ahora lee las filas existentes (secciones 1-3) y las fusiona con las nuevas, sin duplicar por categoría, fecha y prestación.

### Removed
- Eliminadas las carpetas ocultas `0 INBOX/.agents`, `0 INBOX/.claude`, el enlace simbólico `0 INBOX/tools` y el archivo duplicado `0 INBOX/AGENTS.md`.
