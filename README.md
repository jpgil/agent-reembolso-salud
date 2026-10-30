# agent-reembolso

Flujo agéntico para gestionar **reembolsos médicos familiares** en Chile: boletas, bonos y órdenes médicas se llevan por etapas a través de una **Isapre** y un **Seguro Complementario** (SURA), con seguimiento de lo pendiente e historiales médicos anuales por persona.

El repositorio es una plantilla anonimizada: no contiene datos personales, solo el protocolo, los scripts y la estructura de carpetas. Un agente de IA de línea de comandos (`agy` o `claude`) sigue el protocolo de [`AGENTS.md`](AGENTS.md) y usa los scripts de `tools/` para hacer el trabajo repetitivo.

## Qué hace

- **Ingesta desde `~/Downloads`:** detecta boletas, bonos, órdenes médicas, recetas y comprobantes de liquidación, y los mueve (`mv`) a su carpeta.
- **Extracción de texto:** `pdftotext -layout` para PDFs y OCR nativo de macOS (framework Vision, `tools/ocr.swift`) para imágenes y PDFs escaneados.
- **Seguimiento por etapas:** cada trámite es una carpeta con un `.txt` resumen (`CLAVE: VALOR`) que avanza por `0 INBOX` → `1 a isapre` → `2 a SURA` → `3 pagadas`.
- **Cruce de liquidaciones:** asocia cada `Comprobante-Liquidacion-XXXXXXXXX.pdf` a su boleta y calcula el copago y el estimado a recibir de SURA.
- **Circuitos de reembolso:** `ISAPRE_SURA`, `SOLO_SURA` y `SOLO_ISAPRE`, según el tipo de prestación y el beneficiario.
- **Pendientes e historiales:** genera `PENDIENTES_MEDICOS.md` y un `HISTORIAL_<PERSONA>.md` con ventana móvil de 12 meses (consultas, procedimientos, exámenes, medicamentos y recetas vigentes), citando el `.txt` de origen en la columna `Fuente`. Nunca borra filas existentes, así puedes anotar a mano.
- **Autoauditoría:** `--health` revisa las herramientas y detecta desvíos del proceso.

## Estructura

```text
0 INBOX/      Documentos nuevos o pagos pendientes de boleta
1 a isapre/   Trámites en Isapre, esperando liquidación
2 a SURA/     Trámites en SURA, esperando depósito
3 pagadas/    Archivo cerrado (solo lectura)
RECETAS/      Recetas permanentes vigentes (con .txt obligatorio)
GES/          Respaldo de recetas y certificados GES
tools/        pendientes.py, ocr.swift, lanzador, hook de Claude Code y changelog
AGENTS.md     Protocolo operativo para el agente
INSTALL.md    Instalación y personalización
```

## Requisitos

- macOS con Xcode Command Line Tools (`swiftc`) y Python 3.
- `pdftotext` (`brew install poppler`).
- Un agente CLI: Antigravity (`agy`) o Claude Code (`claude`). Claude Code necesita además el hook de [`tools/claude-agents-md-hook.sh`](tools/claude-agents-md-hook.sh) (y `jq`) para leer `AGENTS.md`.

## Inicio rápido

1. Clona el repositorio y abre `agy` o `claude` en su directorio.
2. Pide: *"Instala y configura este repositorio siguiendo `INSTALL.md`"*. El agente verifica dependencias, te pregunta los datos de tus beneficiarios y deja todo listo.
3. Para el uso diario, ejecuta `tools/agent-reembolso.sh` (usa `REEMBOLSO_AGENTE=claude` para Claude Code) y pide, por ejemplo, *"revisa qué hay pendiente"* o *"procesa lo que hay en Descargas"*.

También puedes usar el motor directamente:

```bash
python3 tools/pendientes.py --update              # pendientes + historiales
python3 tools/pendientes.py --scan-downloads --minutes 60
python3 tools/pendientes.py --match-liquidaciones
python3 tools/pendientes.py --health
```

## Privacidad

Los documentos médicos y los historiales generados están excluidos por `.gitignore`. Si usas el repo para tus datos reales, mantenlo **privado** o no subas esas carpetas.

## Cambios

El registro de cambios técnicos del flujo está en [`tools/changelog.md`](tools/changelog.md).

## Autor

Creado por **Juan Pablo Gil Ramírez**.

## Licencia

Distribuido bajo la **Licencia BSD de 3 cláusulas**: puedes usar, copiar, modificar y redistribuir el software, con o sin cambios y también con fines comerciales, siempre que conserves el aviso de copyright y la licencia, y no uses el nombre del autor para promocionar derivados sin permiso. Se entrega «tal cual», sin garantías. Texto completo en [`LICENSE`](LICENSE).
