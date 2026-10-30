# Guía de Instalación y Personalización (`agent-reembolso`)

Sistema agéntico de gestión de reembolsos médicos (Isapre + Seguro Complementario SURA), seguimiento de transferencias pendientes de boleta (Nivel 0), cruce automático de liquidaciones desde `~/Downloads`, extracción híbrida de texto (`pdftotext -layout` + Apple Vision OCR nativo) e historiales médicos anuales en Markdown por beneficiario.

> [!TIP]
> **Instalación asistida por IA:** Puedes abrir `agy` en este directorio y pedirle simplemente:
> *"Instala y configura este repositorio siguiendo `INSTALL.md`"*. El agente verificará las dependencias, te pedirá los datos de tus beneficiarios y dejará todo compilado y listo.

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
4. **Antigravity CLI (`agy`)** instalado en `~/.local/bin/agy`.

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
│   ├── agent-reembolso.sh# Lanzador rápido de sesión con gemini-3.8-flash-low
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
Verifica que la ruta en [`tools/agent-reembolso.sh`](tools/agent-reembolso.sh) apunte a tu carpeta de reembolsos y cópialo a `~/.local/bin/`:

```bash
mkdir -p ~/.local/bin
cp tools/agent-reembolso.sh ~/.local/bin/agent-reembolso.sh
chmod +x ~/.local/bin/agent-reembolso.sh
```

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
   * Copia `tools/agent-reembolso.sh` a `~/.local/bin/agent-reembolso.sh` con `chmod +x`.
   * Ejecuta `python3 tools/pendientes.py --update` y `python3 tools/pendientes.py --health` y confirma que `healthy: true`.
