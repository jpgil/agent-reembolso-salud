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
- **0% Hardcoding en `tools/pendientes.py`:** Eliminados los diccionarios y heurísticas fijas de pacientes, RUTs, médicos y medicamentos; los beneficiarios y sus circuitos se cargan dinámicamente desde la tabla Markdown de `AGENTS.md`.
- **Formato `.txt` simplificado (`CLAVE: VALOR`) y soporte `LEGACY: true`:** Reemplazo de la plantilla extensa de 60 líneas por un bloque plano de claves en mayúsculas con montos enteros puros, manteniendo soporte para texto libre mediante la marca `LEGACY: true`.
- **Consolidación de `AGENTS.md`:** Unificado en un único archivo `AGENTS.md` en la raíz del repositorio con reglas deterministas sin ambigüedades conversacionales.

### Removed
- Eliminadas las carpetas ocultas `0 INBOX/.agents`, `0 INBOX/.claude`, el enlace simbólico `0 INBOX/tools` y el archivo duplicado `0 INBOX/AGENTS.md`.
