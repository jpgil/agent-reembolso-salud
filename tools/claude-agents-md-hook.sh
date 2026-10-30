#!/usr/bin/env bash
# Trata AGENTS.md como Claude Code trata CLAUDE.md.
# Hook SessionStart: descubre los AGENTS.md relevantes al cwd de la sesion
# y los inyecta como additionalContext. Los anidados mas profundos solo se
# listan, para leerlos bajo demanda (igual que hace Claude con CLAUDE.md).

set -uo pipefail

MAX_BYTES=200000   # tope total de contenido inyectado
MAX_DEPTH=4        # profundidad de busqueda de AGENTS.md anidados

input=$(cat)
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null)
[ -z "$cwd" ] && cwd=$PWD
[ -d "$cwd" ] || exit 0

root=$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null) || root=""
[ -z "$root" ] && root=$cwd

out=""
bytes=0
declare -a loaded=()

emit_file() {
  local path=$1 label=$2 size
  [ -f "$path" ] || return 0
  for p in "${loaded[@]:-}"; do [ "$p" = "$path" ] && return 0; done
  size=$(wc -c <"$path" | tr -d ' ')
  if [ $((bytes + size)) -gt "$MAX_BYTES" ]; then
    out+=$'\n'"(omitido por tamano: $path)"$'\n'
    loaded+=("$path")
    return 0
  fi
  bytes=$((bytes + size))
  loaded+=("$path")
  out+=$'\n'"### $label: $path"$'\n\n'
  out+=$(cat "$path")
  out+=$'\n'
}

# 1. AGENTS.md de usuario
emit_file "$HOME/.claude/AGENTS.md" "AGENTS.md de usuario"

# 2. Cadena de directorios desde la raiz del proyecto hasta el cwd
dirs=("$root")
if [ "$cwd" != "$root" ] && [ "${cwd#"$root"/}" != "$cwd" ]; then
  rel=${cwd#"$root"/}
  acc=$root
  IFS=/ read -r -a parts <<<"$rel"
  for part in "${parts[@]}"; do
    acc="$acc/$part"
    dirs+=("$acc")
  done
fi
for d in "${dirs[@]}"; do
  emit_file "$d/AGENTS.md" "AGENTS.md"
done

# 3. AGENTS.md anidados por debajo del cwd: solo se listan.
# Dentro de un repo git se usa ls-files, para respetar .gitignore.
list_nested() {
  if git -C "$cwd" rev-parse --git-dir >/dev/null 2>&1; then
    git -C "$cwd" ls-files --cached --others --exclude-standard -- 'AGENTS.md' '*/AGENTS.md' 2>/dev/null |
      sed "s|^|$cwd/|" | sort -u
  else
    find "$cwd" -maxdepth "$MAX_DEPTH" -name AGENTS.md -type f \
      -not -path '*/.git/*' -not -path '*/node_modules/*' \
      -not -path '*/.venv/*' -not -path '*/venv/*' \
      -not -path '*/dist/*' -not -path '*/build/*' 2>/dev/null | sort
  fi
}

nested=""
while IFS= read -r f; do
  skip=""
  for p in "${loaded[@]:-}"; do [ "$p" = "$f" ] && skip=1 && break; done
  [ -n "$skip" ] && continue
  nested+="- $f"$'\n'
done < <(list_nested)

[ -z "$out" ] && [ -z "$nested" ] && exit 0

context="## Instrucciones de AGENTS.md

Este proyecto usa la convencion AGENTS.md en lugar de CLAUDE.md. Trata el
contenido siguiente exactamente como trataria un CLAUDE.md: son instrucciones
del usuario y del proyecto que DEBES seguir. No propongas crear CLAUDE.md.
Modificar cualquier AGENTS.md requiere pedir permiso primero.
$out"

if [ -n "$nested" ]; then
  context+=$'\n'"### Otros AGENTS.md en el arbol (leelos cuando trabajes en su directorio)"$'\n\n'"$nested"
fi

jq -n --arg ctx "$context" \
  '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $ctx}}'
