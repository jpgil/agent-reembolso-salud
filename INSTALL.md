# Guía de Instalación y Personalización (`agent-reembolso`)

Sistema agéntico de gestión de reembolsos médicos (Isapre + Seguro Complementario SURA), seguimiento de transferencias pendientes de boleta (Nivel 0), cruce automático de liquidaciones desde `~/Downloads`, extracción híbrida de texto (`pdftotext -layout` + Apple Vision OCR nativo) e historiales médicos anuales en Markdown por beneficiario.

> [!TIP]
> **Instalación asistida por IA:** Puedes abrir `agy` (o `claude`) en este directorio y pedirle simplemente:
> *"Instala y configura este repositorio siguiendo `INSTALL.md`"*. El agente verificará las dependencias, te pedirá los datos de tus beneficiarios y dejará todo compilado y listo.

> [!NOTE]
> **Aseguradoras por defecto:** el repo viene configurado para una Isapre (Banmédica) y un seguro complementario (SURA). Cada usuario puede cambiarlas pidiéndoselo al agente instalador (por ejemplo: *"Usa otra Isapre y otro seguro, adapta `AGENTS.md` y los scripts"*).

> [!WARNING]
> **Versión de referencia:** estas instrucciones fueron probadas el **30 de octubre de 2026**. Si hay versiones nuevas de macOS, Xcode, Python, Poppler, `agy` o `claude`, puede ser necesario ajustar detalles técnicos. El agente debe tomar este documento como un ejemplo y adaptarlo, no como una receta literal.

---

## 1. Requisitos del Sistema (macOS)

1. **macOS** (requerido para el framework nativo `Vision` de OCR en Swift y `pbcopy`).
2. **Xcode Command Line Tools (`swiftc`) y Python 3:**
   ```bash
   xcode-select --install
   ```
3. **`pdftotext` (Poppler):** para extracción instantánea (~40 ms) de liquidaciones y boletas en PDF conservando tablas horizontales:
   ```bash
   brew install poppler
   ```
4. **Un agente CLI, a elección** (el repo funciona con cualquiera de los dos):
   * **Antigravity CLI (`agy`)** instalado en `~/.local/bin/agy`.
   * **Claude Code (`claude`)**, por ejemplo instalado en `~/.local/bin/claude`. Verifica con `which claude`.

   > [!NOTE]
   > Este repo usa la convención **`AGENTS.md`** (estándar multi-agente). `agy` la lee directamente; **Claude Code por sí solo solo busca `CLAUDE.md`**, así que para que lea `AGENTS.md` se instala un hook `SessionStart` (sin crear ningún `CLAUDE.md`). El script del hook viene en [`tools/claude-agents-md-hook.sh`](tools/claude-agents-md-hook.sh): inyecta como contexto el `AGENTS.md` de usuario (`~/.claude/AGENTS.md`), los de la cadena de directorios desde la raíz del proyecto hasta el directorio de trabajo y lista los anidados. Requiere `jq` (`brew install jq`). Instalación en el §3, Paso 3b.

---

## 2. Estructura del Repositorio

```text
.
├── 0 INBOX/              # Bandeja de entrada de boletas/órdenes o pagos pendientes de boleta (Nivel 0)
│   └── Duplicados/       # Archivo de imágenes duplicadas o de menor resolución
├── 1 a isapre/           # Trámites subidos a Isapre esperando liquidación o paso a SURA
├── 2 a SURA/             # Trámites enviados a Seguro Complementario SURA esperando depósito
├── 3 pagadas/            # Archivo histórico inmutable (solo lectura) de reembolsos cerrados
├── RECETAS/              # Recetas permanentes vigentes (180 días) con su .txt obligatorio
│   ├── README.md
│   └── archivadas/       # Recetas anteriores reemplazadas o vencidas
├── GES/                  # Respaldo de recetas y certificados GES permanentes
├── tools/
│   ├── claude-agents-md-hook.sh # Hook SessionStart de Claude Code que carga AGENTS.md
│   ├── agent-reembolso.sh# Lanzador rápido de sesión (agy con gemini-3.8-flash-low, o claude con haiku)
│   ├── changelog.md      # Registro de cambios técnicos del flujo (sin datos personales)
│   ├── ocr.swift         # Código fuente de OCR nativo con Apple Vision
│   └── pendientes.py     # Motor determinista (0% hardcoding) de ingesta, cruce, auditoría e historiales
├── AGENTS.md             # Protocolo operativo y tabla de beneficiarios para el agente AI
└── INSTALL.md            # Este archivo
```

---

## 3. Instalación Paso a Paso

### Paso 1: Elegir directorio de operación
Puedes operar directamente en este directorio o copiar su contenido a tu carpeta de documentos médicos (por ejemplo `~/Documents/reembolsos-medicos`).

### Paso 2: Compilar el binario nativo de OCR (`tools/ocr`)
```bash
swiftc -O tools/ocr.swift -o tools/ocr
```
*(Nota: `tools/pendientes.py` también lo compila y repara automáticamente si detecta que no existe).*

### Paso 3: Instalar el lanzador rápido (`agent-reembolso.sh`)
Verifica que la ruta en [`tools/agent-reembolso.sh`](tools/agent-reembolso.sh) apunte a tu carpeta de reembolsos y cópialo a `~/.local/bin/`. Por defecto abre `agy`; para usar Claude Code define `REEMBOLSO_AGENTE=claude`:

```bash
mkdir -p ~/.local/bin
cp tools/agent-reembolso.sh ~/.local/bin/agent-reembolso.sh
chmod +x ~/.local/bin/agent-reembolso.sh

agent-reembolso.sh                         # con agy (por defecto)
REEMBOLSO_AGENTE=claude agent-reembolso.sh # con Claude Code
```

Equivalencias manuales dentro de la carpeta de reembolsos:

| | Antigravity | Claude Code |
| :--- | :--- | :--- |
| Sesión con prompt inicial | `agy -i "Revisa qué hay pendiente"` | `claude "Revisa qué hay pendiente"` |
| Modelo económico | `--model gemini-3.8-flash-low` | `--model haiku` |
| Saltar confirmaciones (riesgoso) | `--dangerously-skip-permissions` | `--dangerously-skip-permissions` |

> [!WARNING]
> `--dangerously-skip-permissions` desactiva todas las confirmaciones. El lanzador solo lo usa con `agy`; con `claude` se mantienen los permisos normales.

### Paso 3b (solo Claude Code): Cargar `AGENTS.md` con un hook `SessionStart`
```bash
mkdir -p ~/.claude/hooks
cp tools/claude-agents-md-hook.sh ~/.claude/hooks/agents-md.sh
chmod +x ~/.claude/hooks/agents-md.sh
```
Registra el hook en `~/.claude/settings.json`, **agregándolo** al arreglo `SessionStart` sin reemplazar los hooks que ya tengas:
```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/agents-md.sh",
            "timeout": 15,
            "statusMessage": "Cargando AGENTS.md"
          }
        ]
      }
    ]
  }
}
```
Verifica abriendo `claude` en la carpeta de reembolsos: debe aparecer el mensaje "Cargando AGENTS.md" y el agente debe conocer las reglas del protocolo.

### Paso 4: Inicializar las vistas y verificar salud del entorno
```bash
python3 tools/pendientes.py --update
python3 tools/pendientes.py --health
```
Esto creará `PENDIENTES_MEDICOS.md` y los archivos `HISTORIAL_<BENEFICIARIO>.md` iniciales, verificando que `pdftotext` y `tools/ocr` estén 100% operativos.

---

## 4. Personalización de Beneficiarios (Fuente Única en `AGENTS.md`)

`tools/pendientes.py` tiene **0% hardcoding**: no contiene nombres, RUTs, médicos ni medicamentos fijos. Lee dinámicamente los beneficiarios, RUTs, siglas y circuitos desde la tabla Markdown de la **Sección 3 de [`AGENTS.md`](AGENTS.md)**.

Para configurar tus propios beneficiarios, solo debes editar la tabla de la **Sección 3 (`Pacientes, RUTs y Circuitos`)** en **[`AGENTS.md`](AGENTS.md)**:
* `Paciente`: Nombre completo del beneficiario.
* `RUT`: RUT sin puntos y con guión (ej. `` `12345678-9` ``), usado por `--copy-rut` para copiarlo al portapapeles (`pbcopy`).
* `Rol`: `Titular` o `Carga`.
* `Consultas y Exámenes` / `Medicamentos`:
  * `ISAPRE_SURA`: Pasa primero por Isapre (`0 INBOX` -> `1 a isapre`) y luego el copago va al seguro complementario (`2 a SURA` -> `3 pagadas`).
  * `SOLO_SURA`: Va directo al seguro complementario sin pasar por Isapre (`0 INBOX` -> `2 a SURA` -> `3 pagadas`).
  * `SOLO_ISAPRE`: Solo tiene cobertura en Isapre; al subir la boleta y registrar el código de solicitud, pasa directo de `0 INBOX` a `3 pagadas`.
* `Historial Anual`: Enlace al archivo Markdown anual de esa persona (ej. `[HISTORIAL_TITULAR.md](HISTORIAL_TITULAR.md)`).

---

## 5. Instrucciones para el Agente AI durante la Instalación

Si el usuario te pide **"Instala este repositorio siguiendo `INSTALL.md`"**, sigue este protocolo interactivo:

1. **Solicitar configuración de beneficiarios:**
   * Pregúntale al usuario:
     1. ¿En qué ruta del disco vivirá la carpeta activa de reembolsos? (ej. la carpeta actual o `~/Documents/reembolsos-medicos`).
     2. ¿Cuáles son los beneficiarios a configurar? Pide para cada uno: **Nombre completo**, **RUT con guión**, **Rol** (`Titular` / `Carga`) y qué circuito de cobertura aplica en **Consultas/Exámenes** y en **Medicamentos** (`ISAPRE_SURA`, `SOLO_SURA`, `SOLO_ISAPRE` o `No cubierto`).
2. **Aplicar configuración:**
   * Actualiza la tabla de la Sección 3 en `AGENTS.md` con los beneficiarios del usuario y ajusta la ruta en `tools/agent-reembolso.sh`.
3. **Instalar dependencias y compilar:**
   * Verifica `pdftotext` (`which pdftotext`); si falta, ofrece ejecutar `brew install poppler`.
   * Compila `swiftc -O tools/ocr.swift -o tools/ocr`.
   * Copia `tools/agent-reembolso.sh` a `~/.local/bin/agent-reembolso.sh` con `chmod +x`. Si el usuario usa Claude Code, instala el hook del Paso 3b: copia `tools/claude-agents-md-hook.sh` a `~/.claude/hooks/agents-md.sh` y agrega la entrada a `~/.claude/settings.json` conservando los hooks existentes, pidiendo confirmación antes de editar ese archivo (nunca crees un `CLAUDE.md`).
   * Ejecuta `python3 tools/pendientes.py --update` y `python3 tools/pendientes.py --health` y confirma que `healthy: true`.
