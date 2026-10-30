#!/usr/bin/env bash
# Lanzador de sesión del agente. Elegir agente con REEMBOLSO_AGENTE=agy (por defecto) o claude.
export PATH="$HOME/.local/bin:$PATH"
cd "${REEMBOLSO_DIR:-$HOME/Documents/reembolsos-medicos}" || exit 1
PROMPT="Revisa qué hay pendiente"

case "${REEMBOLSO_AGENTE:-agy}" in
  agy)
    # --dangerously-skip-permissions omite TODAS las confirmaciones: úsalo solo en este directorio.
    exec agy --model gemini-3.8-flash-low --effort low --dangerously-skip-permissions -i "$PROMPT"
    ;;
  claude)
    # Equivalente en Claude Code: modelo económico y confirmaciones normales (ver INSTALL.md §1, §3 y Paso 3b).
    exec claude --model haiku "$PROMPT"
    ;;
  *)
    echo "REEMBOLSO_AGENTE debe ser 'agy' o 'claude'" >&2
    exit 1
    ;;
esac
