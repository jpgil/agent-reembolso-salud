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

## Ejemplo de uso

Para instalar, abre `agy` o `claude` en el directorio del repo y pide: *"Instala y configura este repositorio siguiendo `INSTALL.md`"*. Después, el uso diario parte con `tools/agent-reembolso.sh` (con `REEMBOLSO_AGENTE=claude` para Claude Code). Los nombres, fechas, IDs y montos de abajo son ficticios.

**Caso completo: una consulta pediátrica, desde la foto de la boleta hasta el depósito de SURA**

1. **Foto de la boleta.** Vas a una consulta con la Dra. Ana Pérez, pagas y te llega la boleta por WhatsApp. La descargas en `~/Downloads` como `WhatsApp Image 2026-03-17 at 11.42.10.jpeg`.

2. **Ingesta.** Abres el agente y le dices: *"Procesa lo que hay en Descargas"*. El agente corre `--scan-downloads`, detecta la imagen, extrae el texto con OCR y lee fecha, folio, monto y profesional. Luego crea `0 INBOX/20260317_Consulta_Pediatria_Dra_Ana_Perez/`, mueve (`mv`) allí la imagen renombrada y genera el `.txt` resumen con `ESTADO: PENDIENTE_ISAPRE`. Te avisa que identificó a Luciano como paciente y que el circuito es `ISAPRE_SURA`.

3. **Subida a la Isapre.** Subes la boleta a la sucursal virtual de la Isapre, que te entrega el ID de solicitud, por ejemplo `600012345678`. Se lo das al agente: *"El ID es 600012345678"*. Él lo valida, actualiza el `.txt` (`ID_ISAPRE`, `ESTADO: EN_ISAPRE`) y mueve la carpeta a `1 a isapre/20260317_Consulta_Pediatria_Dra_Ana_Perez 600012345678`.

4. **Liquidación.** Días después descargas `Comprobante-Liquidacion-398765432.pdf`. Le dices: *"Llegó la liquidación"*. El agente cruza el PDF con la boleta por su folio, lo mueve a la carpeta del trámite y calcula con `--match-liquidaciones`: monto $45.000, bonificación Isapre $12.000, copago $33.000 y estimado de SURA (80%) $26.400. El estado pasa a `LISTO_PARA_SURA`.

5. **Envío a SURA.** Le pides: *"Vamos a enviar a SURA"*. El agente copia el RUT del paciente al portapapeles (`--copy-rut`), te indica el nombre exacto de la carpeta y los archivos que debes arrastrar uno por uno al WhatsApp de SURA: la boleta, el bono y la liquidación, sin el `.txt`. Los envías y SURA te responde con el ID, por ejemplo `20812345`.

6. **Seguimiento.** Le das el ID: *"SURA me dio el 20812345"*. El agente actualiza el `.txt` (`ID_SURA`, `ESTADO: EN_SURA`) y mueve la carpeta a `2 a SURA/20260317_Consulta_Pediatria_Dra_Ana_Perez 600012345678 20812345`. Cada vez que preguntas *"¿qué hay pendiente?"*, el agente corre `--update` y te muestra el trámite en `PENDIENTES_MEDICOS.md`, con los $26.400 por recibir y los $6.600 que quedan de tu bolsillo (20%).

7. **Pago.** SURA deposita en tu cuenta. Le avisas: *"SURA depositó $26.400"*. El agente anota `PAGADO_SURA: 26400` y `ESTADO: PAGADO`, mueve la carpeta a `3 pagadas/` (desde ahí es solo lectura) y regenera `HISTORIAL_LUCIANO.md` con una fila nueva:

   ```text
   | 2026-03-17 | Consulta Médica Pediátrica | Dra. Ana Pérez | `20260317_Consulta_Pediatria_Dra_Ana_Perez 600012345678 20812345.txt` |
   ```

Si pagas por transferencia antes de recibir la boleta, el agente crea el trámite en `0 INBOX` con `ESTADO: PENDIENTE_BOLETA` y te lo recuerda hasta que llegue. Los medicamentos van directo a SURA (`SOLO_SURA`), y las consultas de un beneficiario que solo tiene Isapre (`SOLO_ISAPRE`) se cierran en `3 pagadas` apenas tienen el ID.

Para usar el motor sin agente:

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
