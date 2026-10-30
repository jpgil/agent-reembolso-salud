#!/usr/bin/env bash
cd "${REEMBOLSO_DIR:-$HOME/Documents/reembolsos-medicos}" || exit 1
agy --model gemini-3.8-flash-low --effort low --dangerously-skip-permissions -i "Revisa qué hay pendiente"
