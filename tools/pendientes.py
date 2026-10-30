#!/usr/bin/env python3
"""
tools/pendientes.py - Motor determinista de reembolsos médicos, extracción híbrida,
cruce de liquidaciones desde ~/Downloads y auditoría de salud (0% hardcoding).

Toda la información de pacientes/circuitos proviene dinámicamente de la tabla en AGENTS.md,
y toda la información de documentos proviene de sus archivos .txt (incluyendo soporte para LEGACY: true)
y de los archivos originales en RECETAS/.

Uso (ejecutado internamente por el agente):
  python3 tools/pendientes.py                      # Reporte completo + auditoría de proceso y salud
  python3 tools/pendientes.py --update             # Actualiza PENDIENTES_MEDICOS.md
  python3 tools/pendientes.py --historiales        # Regenera los HISTORIAL_<PERSONA>.md desde los .txt
  python3 tools/pendientes.py --scan-downloads     # Escanea archivos recientes en ~/Downloads (ventana 60 min)
  python3 tools/pendientes.py --match-liquidaciones# Cruza y MUEVE (mv) Comprobante-Liquidacion-*.pdf desde ~/Downloads a '1 a isapre'
  python3 tools/pendientes.py --extract "<ruta>"   # Extracción híbrida: pdftotext -layout (PDF) -> fallback tools/ocr
  python3 tools/pendientes.py --copy-rut <query>   # Copia el RUT sin puntos y con guión al portapapeles (pbcopy)
  python3 tools/pendientes.py --health             # Verifica estado de binarios, scripts, .txt en RECETAS y reglas
  python3 tools/pendientes.py --json               # Salida estructurada en JSON
"""

import re
import sys
import json
import time
import shutil
import unicodedata
import argparse
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple


def find_repo_root(start_path: Optional[Path] = None) -> Path:
    """Determina la raíz del repositorio de forma relativa a la ubicación del script."""
    script_root = Path(__file__).resolve().parent.parent
    if (script_root / "0 INBOX").is_dir() or (script_root / "AGENTS.md").exists():
        return script_root
    cur = (start_path or Path.cwd()).resolve()
    for _ in range(5):
        if (cur / "0 INBOX").is_dir() and (cur / "1 a isapre").is_dir():
            return cur
        cur = cur.parent
    return script_root


def strip_accents(s: str) -> str:
    """Elimina tildes para comparaciones insensibles a acentos."""
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")


def clean_amount(val_str: str) -> int:
    """Convierte cadenas numéricas o con formato moneda en entero puro."""
    if not val_str:
        return 0
    val_str = str(val_str).strip()
    if val_str.upper() in ("PENDIENTE", "N/A", "NONE", "-"):
        return 0
    if "(" in val_str:
        val_str = val_str.split("(")[0]
    m = re.search(r"\$\s*([\d\.,]+)", val_str)
    if m:
        digits = re.sub(r"[^\d]", "", m.group(1))
        return int(digits) if digits else 0
    digits = re.sub(r"[^\d]", "", val_str)
    return int(digits) if digits else 0


def format_currency(val: int) -> str:
    """Formatea un entero como moneda chilena ($XX.XXX)."""
    return f"${val:,}".replace(",", ".")


def normalize_date(date_str: str, fallback_folder_name: str = "") -> str:
    """Normaliza fechas a YYYY-MM-DD."""
    date_str = (date_str or "").strip()
    m_iso = re.search(r"(\d{4})-(\d{2})-(\d{2})", date_str)
    if m_iso:
        return f"{m_iso.group(1)}-{m_iso.group(2)}-{m_iso.group(3)}"
    m_cl = re.search(r"(\d{2})[/\-](\d{2})[/\-](\d{4})", date_str)
    if m_cl:
        return f"{m_cl.group(3)}-{m_cl.group(2)}-{m_cl.group(1)}"
    m_8 = re.match(r"^(\d{4})(\d{2})(\d{2})", date_str)
    if m_8:
        return f"{m_8.group(1)}-{m_8.group(2)}-{m_8.group(3)}"
    m_f = re.match(r"^(\d{4})(\d{2})(\d{2})", fallback_folder_name)
    if m_f:
        return f"{m_f.group(1)}-{m_f.group(2)}-{m_f.group(3)}"
    return date_str or "Sin fecha"


# ==============================================================================
# CARGA DINÁMICA DE PACIENTES Y CIRCUITOS DESDE AGENTS.md (0% HARDCODING)
# ==============================================================================
def load_patients_from_agents_md(root: Path) -> List[Dict[str, Any]]:
    """Parsea dinámicamente la tabla de pacientes de AGENTS.md."""
    agents_file = root / "AGENTS.md"
    patients: List[Dict[str, Any]] = []
    if not agents_file.exists():
        return patients

    content = agents_file.read_text(encoding="utf-8", errors="replace")
    for line in content.splitlines():
        line_s = line.strip()
        if not line_s.startswith("|"):
            continue
        cols = [c.strip() for c in line_s.strip("|").split("|")]
        if len(cols) < 6:
            continue
        # Ignorar encabezados y separadores Markdown
        if "paciente" in cols[0].lower() or set(cols[0]).issubset({"-", ":", " "}):
            continue

        raw_name = re.sub(r"\*+", "", cols[0]).strip()
        rut = re.sub(r"[`\s\*]", "", cols[1]).strip()
        rol = re.sub(r"\*+", "", cols[2]).strip()
        circ_cons = re.sub(r"[`\*]", "", cols[3]).strip().split()[0]
        circ_med = re.sub(r"[`\*]", "", cols[4]).strip().split()[0]

        m_link = re.search(r"\(([^)]+\.md)\)", cols[5])
        hist_file = m_link.group(1) if m_link else re.sub(r"[`\*]", "", cols[5]).strip()

        # Generar tokens dinámicos de búsqueda (palabras, iniciales y RUT) a partir del nombre y RUT en AGENTS.md
        norm_name = strip_accents(raw_name.lower())
        all_words = [t for t in re.split(r"\s+", norm_name) if t]
        name_tokens = [t for t in all_words if len(t) >= 3]
        initials_2 = "".join(w[0] for w in all_words[:2]) if len(all_words) >= 2 else ""
        initials_3 = "".join(w[0] for w in all_words[:3]) if len(all_words) >= 3 else ""
        initials_all = "".join(w[0] for w in all_words) if len(all_words) >= 2 else ""
        rut_digits = re.sub(r"[^\dkK]", "", rut).lower()
        rut_base = rut.split("-")[0] if "-" in rut else rut_digits

        dynamic_tokens = [t for t in (name_tokens + [initials_2, initials_3, initials_all, rut.lower(), rut_base.lower(), rut_digits]) if t]

        patients.append({
            "canonical": raw_name,
            "rut": rut,
            "rol": rol,
            "circuito_consulta": circ_cons,
            "circuito_medicamento": circ_med,
            "historial_file": hist_file,
            "tokens": dynamic_tokens,
        })
    return patients


def match_patient(query_text: str, patients: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Empareja un texto (PACIENTE, RUT_PACIENTE o consulta) contra la lista dinámica de AGENTS.md."""
    if not patients:
        return None
    q_norm = strip_accents((query_text or "").lower())
    q_digits = re.sub(r"[^\d]", "", q_norm)

    # 1. Match exacto por RUT numérico
    for p in patients:
        p_rut_base = p["rut"].split("-")[0]
        if p_rut_base and p_rut_base in q_digits:
            return p

    # 2. Match por primer nombre o nombre completo
    for p in patients:
        first_token = p["tokens"][0] if p["tokens"] else ""
        full_norm = strip_accents(p["canonical"].lower())
        if full_norm in q_norm or (first_token and re.search(rf"\b{re.escape(first_token)}\b", q_norm)):
            return p

    # 3. Match parcial por cualquier token único
    for p in patients:
        for tok in p["tokens"]:
            if tok and tok in q_norm:
                return p

    return None


def verify_banmedica_id(id_str: str) -> Dict[str, Any]:
    """Verificación blanda para ID Isapre Banmédica (12 dígitos, inicia con 6000)."""
    if not id_str or id_str.upper() in ("EN TRÁMITE", "PENDIENTE", "N/A"):
        return {"valid": False, "warning": "Sin ID asignado"}
    if re.fullmatch(r"6000\d{8}", id_str):
        return {"valid": True, "warning": None}
    if re.fullmatch(r"\d{12}", id_str):
        return {"valid": True, "warning": f"ID de 12 dígitos pero prefijo no estándar (esperado '6000...'): {id_str}"}
    return {"valid": False, "warning": f"Sintaxis inusual ID Banmédica: esperado 12 dígitos (ej. 600034478422), obtenido '{id_str}'"}


def verify_sura_id(id_str: str) -> Dict[str, Any]:
    """Verificación blanda para ID Siniestro SURA (8 dígitos)."""
    if not id_str or id_str.upper() in ("EN TRÁMITE", "PENDIENTE", "N/A"):
        return {"valid": False, "warning": "Sin ID asignado"}
    if re.fullmatch(r"\d{8}", id_str):
        return {"valid": True, "warning": None}
    return {"valid": False, "warning": f"Sintaxis inusual ID SURA: esperado 8 dígitos (ej. 20703737), obtenido '{id_str}'"}


# ==============================================================================
# MOTOR DE EXTRACCIÓN HÍBRIDO (pdftotext -layout + binario tools/ocr)
# ==============================================================================
def ensure_ocr_binary(root: Path) -> Tuple[bool, str]:
    """Verifica que el binario compilado tools/ocr exista y esté actualizado respecto a tools/ocr.swift."""
    swift_src = root / "tools" / "ocr.swift"
    ocr_bin = root / "tools" / "ocr"
    if not swift_src.exists():
        return False, "No se encontró tools/ocr.swift"
    needs_compile = (not ocr_bin.exists()) or (swift_src.stat().st_mtime > ocr_bin.stat().st_mtime)
    if needs_compile:
        try:
            res = subprocess.run(
                ["swiftc", "-O", str(swift_src), "-o", str(ocr_bin)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if res.returncode != 0:
                return False, f"Error compilando tools/ocr: {res.stderr.strip()}"
            return True, "Binario tools/ocr compilado automáticamente"
        except Exception as e:
            return False, f"Excepción compilando tools/ocr: {e}"
    return True, "OK"


def extract_text_hybrid(file_path: Path, root: Path) -> Dict[str, Any]:
    """Extrae texto de un archivo usando pdftotext -layout para PDFs y tools/ocr como fallback o para imágenes."""
    if not file_path.exists():
        return {"ok": False, "engine": "none", "text": "", "error": f"Archivo no existe: {file_path}"}

    ext = file_path.suffix.lower()
    if ext == ".pdf":
        pdftotext_bin = shutil.which("pdftotext") or "/opt/homebrew/bin/pdftotext"
        if Path(pdftotext_bin).exists():
            try:
                res = subprocess.run(
                    [pdftotext_bin, "-layout", str(file_path), "-"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                txt = res.stdout.strip()
                if res.returncode == 0 and len(txt) >= 20:
                    return {"ok": True, "engine": "pdftotext -layout", "text": txt}
            except Exception:
                pass

    ok_bin, _ = ensure_ocr_binary(root)
    ocr_bin = root / "tools" / "ocr"
    cmd = [str(ocr_bin), str(file_path)] if ok_bin and ocr_bin.exists() else ["swift", str(root / "tools" / "ocr.swift"), str(file_path)]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        txt = res.stdout.strip()
        return {
            "ok": res.returncode == 0 and len(txt) > 0,
            "engine": "tools/ocr (Vision)" if ok_bin else "swift tools/ocr.swift",
            "text": txt,
            "error": res.stderr.strip() if res.returncode != 0 else None,
        }
    except Exception as e:
        return {"ok": False, "engine": "tools/ocr", "text": "", "error": str(e)}


# ==============================================================================
# PARSER DE ARCHIVOS .TXT (SOPORTE CLAVE: VALOR + LEGACY: true TEXTO LIBRE)
# ==============================================================================
def parse_metadata_txt(txt_path: Path) -> Dict[str, Any]:
    """
    Lee el archivo .txt que resume un directorio o receta.
    - Si contiene 'LEGACY: true', marca 'legacy': True e incluye todo el contenido en 'full_text'
      para que el agente lea el texto completo al tomar decisiones, además de extraer los campos que existan.
    - Si está en formato 'CLAVE: VALOR', extrae directamente todas las claves estandarizadas.
    """
    content = txt_path.read_text(encoding="utf-8", errors="replace")
    kv_matches = dict(re.findall(r"^([A-Z0-9_]+):\s*(.*)$", content, re.MULTILINE))

    is_legacy_flag = kv_matches.get("LEGACY", "").strip().lower() == "true" or bool(
        re.search(r"^LEGACY:\s*true\b", content, re.I | re.M)
    )
    has_kv_keys = any(k in kv_matches for k in ("PACIENTE", "MONTO_TOTAL", "CIRCUITO", "PRESTACION"))

    data: Dict[str, Any] = {
        "txt_path": str(txt_path),
        "format": "legacy" if (is_legacy_flag or not has_kv_keys) else "kv",
        "legacy": is_legacy_flag or not has_kv_keys,
        "full_text": content if (is_legacy_flag or not has_kv_keys) else "",
        "paciente": "",
        "rut_paciente": "",
        "prestacion": "",
        "proveedor": "",
        "fecha": "",
        "documento": "",
        "folio_boleta": "",
        "circuito": "",
        "estado_txt": "",
        "id_isapre": "",
        "liquidacion_isapre": "",
        "id_sura": "",
        "monto_total": 0,
        "bonif_isapre": 0,
        "copago_isapre": 0,
        "monto_sura_estimado": 0,
        "pagado_sura": "",
        "copago_bolsillo": 0,
        "monto": 0,
    }

    if has_kv_keys:
        data["paciente"] = kv_matches.get("PACIENTE", "").strip()
        data["rut_paciente"] = kv_matches.get("RUT_PACIENTE", "").strip()
        data["prestacion"] = kv_matches.get("PRESTACION", "").strip()
        data["proveedor"] = kv_matches.get("PROVEEDOR", "").strip()
        data["fecha"] = kv_matches.get("FECHA", "").strip()
        data["folio_boleta"] = kv_matches.get("FOLIO_BOLETA", "").strip()
        data["documento"] = data["folio_boleta"]
        data["circuito"] = kv_matches.get("CIRCUITO", "").strip()
        data["estado_txt"] = kv_matches.get("ESTADO", "").strip()
        data["id_isapre"] = kv_matches.get("ID_ISAPRE", "").strip()
        data["liquidacion_isapre"] = kv_matches.get("LIQUIDACION_ISAPRE", "").strip()
        data["id_sura"] = kv_matches.get("ID_SURA", "").strip()
        data["monto_total"] = clean_amount(kv_matches.get("MONTO_TOTAL", "0"))
        data["bonif_isapre"] = clean_amount(kv_matches.get("BONIFICACION_ISAPRE", "0"))
        data["copago_isapre"] = clean_amount(kv_matches.get("COPAGO_ISAPRE", "0"))
        data["monto_sura_estimado"] = clean_amount(kv_matches.get("ESTIMADO_SURA_80", "0"))
        data["pagado_sura"] = kv_matches.get("PAGADO_SURA", "").strip()

    # Si es LEGACY: true o texto libre antiguo, complementar extrayendo del texto libre lo que esté disponible
    if data["legacy"]:
        if not data["paciente"]:
            m = re.search(r"(?:Paciente|Beneficiario):\s*([^\n\r]+)", content, re.I)
            if m:
                data["paciente"] = re.sub(r"\(?\s*RUT:?.*", "", m.group(1), flags=re.I).strip()
        if not data["rut_paciente"]:
            m = re.search(r"RUT(?:\s*Paciente)?:\s*([\d\.]+\-[\dkK])", content, re.I)
            if m:
                data["rut_paciente"] = m.group(1).replace(".", "").strip()
        if not data["prestacion"]:
            m = re.search(r"(?:Prestaci[oó]n|Especialidad):\s*([^\n\r]+)", content, re.I)
            if m:
                data["prestacion"] = m.group(1).strip()
        if not data["proveedor"]:
            m = re.search(r"(?:Profesional(?:\s*Tratante)?|Emisor|Proveedor|M[eé]dico):\s*([^\n\r]+)", content, re.I)
            if m:
                data["proveedor"] = m.group(1).strip()
        if not data["fecha"]:
            m = re.search(r"Fecha(?:\s*Documento|\s*Emisi[oó]n)?:\s*([^\n\r]+)", content, re.I)
            if m:
                data["fecha"] = m.group(1).strip()
        if not data["folio_boleta"]:
            m = re.search(r"(?:Folio|N[°o]\s*Boleta|Documento):\s*([^\n\r]+)", content, re.I)
            if m:
                data["documento"] = m.group(1).strip()
                m_num = re.search(r"(\d+)", data["documento"])
                if m_num:
                    data["folio_boleta"] = m_num.group(1)
        if data["monto_total"] == 0:
            m = re.search(
                r"(?:Monto\s*Total\s*Prestaci[oó]n|Total\s*Gasto\s*Farmacia\s*Medicamentos\s*\(Reembolsable\)|Total\s*Boleta\s*/\s*Factura|Monto(?:\s*Reembolsable)?):\s*([^\n\r]+)",
                content,
                re.I,
            )
            if m:
                data["monto_total"] = clean_amount(m.group(1))
        if data["bonif_isapre"] == 0:
            m = re.search(r"Bonificaci[oó]n\s*Isapre(?:\s*\(Pagada\))?:\s*([^\n\r]+)", content, re.I)
            if m:
                data["bonif_isapre"] = clean_amount(m.group(1))
        if data["copago_isapre"] == 0:
            m = re.search(r"(?:Copago\s*Isapre\s*Presentado|Copago\s*Afiliado\s*Remanente|Total\s*Copago):\s*([^\n\r]+)", content, re.I)
            if m:
                data["copago_isapre"] = clean_amount(m.group(1))
        if data["monto_sura_estimado"] == 0:
            m = re.search(r"(?:Reembolso\s*Estimado\s*SURA|Monto\s*Reembolsable\s*Estimado):\s*([^\n\r]+)", content, re.I)
            if m:
                data["monto_sura_estimado"] = clean_amount(m.group(1))

    if data["monto_sura_estimado"] == 0:
        base_sura = data["copago_isapre"] if data["copago_isapre"] > 0 else data["monto_total"]
        if data["circuito"] != "SOLO_ISAPRE" and base_sura > 0:
            data["monto_sura_estimado"] = int(round(0.80 * base_sura))
    base_copago = data["copago_isapre"] if data["copago_isapre"] > 0 else data["monto_total"]
    data["copago_bolsillo"] = max(0, base_copago - data["monto_sura_estimado"])
    data["monto"] = data["monto_total"] if data["monto_total"] > 0 else data["copago_isapre"]

    return data


# ==============================================================================
# ESCANEO DE ~/Downloads Y CRUCE AUTOMÁTICO DE LIQUIDACIONES BANMÉDICA (mv)
# ==============================================================================
def scan_downloads(minutes_window: int = 60) -> List[Dict[str, Any]]:
    """Escanea ~/Downloads buscando archivos médicos recientes dentro de la ventana de minutos indicada."""
    dl_dir = Path.home() / "Downloads"
    if not dl_dir.is_dir():
        return []

    now = time.time()
    cutoff = now - (minutes_window * 60)
    results = []

    for f in sorted(dl_dir.iterdir(), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True):
        if f.name.startswith(".") or f.is_dir():
            continue
        try:
            mtime = f.stat().st_mtime
        except OSError:
            continue

        is_recent = mtime >= cutoff
        age_min = round((now - mtime) / 60, 1)
        fn = f.name

        is_whatsapp = bool(re.match(r"^WhatsApp Image \d{4}-\d{2}-\d{2} at \d{1,2}\.\d{2}\.\d{2}.*\.(?:jpe?g|png)$", fn, re.I))
        is_liquidacion = bool(re.match(r"^Comprobante-Liquidacion-\d+.*\.pdf$", fn, re.I))
        is_pdf_doc = f.suffix.lower() == ".pdf" and is_recent

        if is_recent and (is_whatsapp or is_liquidacion or is_pdf_doc):
            kind = "LIQUIDACION_BANMEDICA" if is_liquidacion else ("WHATSAPP_IMAGE" if is_whatsapp else "PDF_RECIENTE")
            results.append({
                "name": fn,
                "path": str(f),
                "kind": kind,
                "age_minutes": age_min,
                "size_bytes": f.stat().st_size,
            })
    return results


def parse_liquidacion_pdf(pdf_path: Path, root: Path) -> Dict[str, Any]:
    """Extrae de un Comprobante-Liquidacion-XXXXXXXXX.pdf: N° Liquidación, Fecha, Boleta/Folio, Monto Total, Bonificación y Copago."""
    ext = extract_text_hybrid(pdf_path, root)
    txt = ext.get("text", "")
    info: Dict[str, Any] = {
        "liquidacion_num": "",
        "folio_boleta": "",
        "fecha_atencion": "",
        "monto_total": 0,
        "bonificacion": 0,
        "copago": 0,
    }
    m_liq = re.search(r"Comprobante-Liquidacion-(\d+)", pdf_path.name, re.I)
    if m_liq:
        info["liquidacion_num"] = m_liq.group(1)

    # 1. Fila de detalle Banmédica:
    # Número de boleta | Fecha de Atención (DD-MM-YYYY o DD/MM/YYYY) | Código | ... | Cant | $Valor | $Bonificación | $Copago
    for line in txt.splitlines():
        m_row = re.search(
            r"^\s*(\d+)\s+(\d{2}[/\-]\d{2}[/\-]\d{4})\s+\d+.*?\$?\s*([\d\.]+)\s+\$?\s*([\d\.]+)\s+\$?\s*([\d\.]+)\s*$",
            line,
        )
        if m_row:
            info["folio_boleta"] = m_row.group(1).strip()
            info["fecha_atencion"] = normalize_date(m_row.group(2))
            info["monto_total"] += clean_amount(m_row.group(3))
            info["bonificacion"] += clean_amount(m_row.group(4))
            info["copago"] += clean_amount(m_row.group(5))

    # 2. Fila de Total (3 columnas de montos: Valor Prestación | Bonificación Isapre | Copago Afiliado)
    m_tot_row = re.search(
        r"^\s*Total(?:es)?\s+\$?\s*([\d\.]+)\s+\$?\s*([\d\.]+)\s+\$?\s*([\d\.]+)\s*$",
        txt,
        re.I | re.M,
    )
    if m_tot_row:
        info["monto_total"] = clean_amount(m_tot_row.group(1))
        info["bonificacion"] = clean_amount(m_tot_row.group(2))
        info["copago"] = clean_amount(m_tot_row.group(3))

    return info


def match_and_move_liquidaciones(root: Path, minutes_window: int = 120) -> List[Dict[str, Any]]:
    """Busca Comprobante-Liquidacion-*.pdf en ~/Downloads, hace match con '1 a isapre', MUEVE (mv) el PDF y actualiza el .txt."""
    dl_items = scan_downloads(minutes_window=minutes_window)
    liq_items = [it for it in dl_items if it["kind"] == "LIQUIDACION_BANMEDICA"]
    isapre_dir = root / "1 a isapre"
    moved_actions = []

    if not liq_items or not isapre_dir.is_dir():
        return moved_actions

    for item in liq_items:
        pdf_path = Path(item["path"])
        if not pdf_path.exists():
            continue
        liq_info = parse_liquidacion_pdf(pdf_path, root)
        folio = liq_info.get("folio_boleta", "")
        liq_num = liq_info.get("liquidacion_num", "")

        matched_folder: Optional[Path] = None
        matched_txt: Optional[Path] = None

        for folder in sorted(isapre_dir.iterdir()):
            if not folder.is_dir() or folder.name.startswith("."):
                continue
            txts = [f for f in folder.iterdir() if f.suffix == ".txt"]
            if not txts:
                continue
            meta = parse_metadata_txt(txts[0])
            meta_folio = str(meta.get("folio_boleta") or meta.get("documento") or "")
            if folio and (folio == meta_folio or re.search(rf"\b{re.escape(folio)}\b", meta_folio)):
                matched_folder = folder
                matched_txt = txts[0]
                break
            if liq_info["monto_total"] > 0 and meta.get("monto_total") == liq_info["monto_total"]:
                matched_folder = folder
                matched_txt = txts[0]
                break

        if matched_folder:
            dest_name = f"Comprobante-Liquidacion-{liq_num}.pdf" if liq_num else pdf_path.name
            dest_path = matched_folder / dest_name
            shutil.move(str(pdf_path), str(dest_path))

            if matched_txt and matched_txt.exists():
                content = matched_txt.read_text(encoding="utf-8", errors="replace")
                est_sura = int(round(0.80 * liq_info["copago"]))
                if "BONIFICACION_ISAPRE:" in content:
                    content = re.sub(r"^LIQUIDACION_ISAPRE:.*$", f"LIQUIDACION_ISAPRE: {liq_num}", content, flags=re.M)
                    content = re.sub(r"^BONIFICACION_ISAPRE:.*$", f"BONIFICACION_ISAPRE: {liq_info['bonificacion']}", content, flags=re.M)
                    content = re.sub(r"^COPAGO_ISAPRE:.*$", f"COPAGO_ISAPRE: {liq_info['copago']}", content, flags=re.M)
                    content = re.sub(r"^ESTIMADO_SURA_80:.*$", f"ESTIMADO_SURA_80: {est_sura}", content, flags=re.M)
                    content = re.sub(r"^ESTADO:.*$", "ESTADO: LISTO_PARA_SURA", content, flags=re.M)
                    matched_txt.write_text(content, encoding="utf-8")

            moved_actions.append({
                "source_removed_from_downloads": item["name"],
                "moved_to_folder": f"1 a isapre/{matched_folder.name}",
                "liquidacion_num": liq_num,
                "folio_boleta": folio,
                "monto_total": liq_info["monto_total"],
                "bonificacion_isapre": liq_info["bonificacion"],
                "copago_isapre": liq_info["copago"],
                "estimado_sura_80": int(round(0.80 * liq_info["copago"])),
            })

    return moved_actions


# ==============================================================================
# ESCANEO DE NIVELES 0, 1, 2 Y 3 DE REEMBOLSOS ACTIVOS (DESDE .TXT)
# ==============================================================================
def scan_level0(root: Path, patients: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Escanea 0 INBOX buscando pagos/transferencias realizadas pendientes de que el médico envíe la boleta (ESTADO: PENDIENTE_BOLETA)."""
    inbox = root / "0 INBOX"
    items = []
    if not inbox.is_dir():
        return items

    for folder in sorted(inbox.iterdir()):
        if not folder.is_dir() or folder.name.startswith(".") or folder.name in ("tools", "Duplicados"):
            continue

        files = [f for f in folder.iterdir() if not f.name.startswith(".")]
        txt_files = [f for f in files if f.suffix == ".txt"]
        if not txt_files:
            continue
        meta = parse_metadata_txt(txt_files[0])
        if meta.get("estado_txt") != "PENDIENTE_BOLETA":
            continue

        p_match = match_patient(f"{meta.get('paciente', '')} {meta.get('rut_paciente', '')}", patients)
        circuito = meta.get("circuito") or (p_match["circuito_consulta"] if p_match else "ISAPRE_SURA")
        fecha = normalize_date(meta.get("fecha", ""), folder.name)
        dias_espera = 0
        if re.match(r"^\d{4}-\d{2}-\d{2}$", fecha):
            try:
                dt_f = datetime.strptime(fecha, "%Y-%m-%d").date()
                dias_espera = max(0, (datetime.now().date() - dt_f).days)
            except ValueError:
                dias_espera = 0

        proveedor = meta.get("proveedor") or "prestador médico"
        items.append({
            "nivel": 0,
            "carpeta": folder.name,
            "directorio_relativo": f"0 INBOX/{folder.name}",
            "path": str(folder),
            "paciente": meta.get("paciente") or (p_match["canonical"] if p_match else "Por definir en boleta"),
            "rut_paciente": meta.get("rut_paciente") or (p_match["rut"] if p_match else "PENDIENTE"),
            "prestacion": meta.get("prestacion") or folder.name,
            "proveedor": proveedor,
            "fecha": fecha,
            "dias_espera": dias_espera,
            "circuito": circuito,
            "monto": meta.get("monto", 0),
            "legacy": meta.get("legacy", False),
            "full_text": meta.get("full_text", ""),
            "estado": f"Pedir boleta a {proveedor} (pagado hace {dias_espera} día(s))",
        })
    return items


def scan_level1(root: Path, patients: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Escanea 0 INBOX buscando documentos con boleta/factura pagada pendientes de enviar."""
    inbox = root / "0 INBOX"
    items = []
    if not inbox.is_dir():
        return items

    for folder in sorted(inbox.iterdir()):
        if not folder.is_dir() or folder.name.startswith(".") or folder.name in ("tools", "Duplicados"):
            continue

        files = [f for f in folder.iterdir() if not f.name.startswith(".")]
        txt_files = [f for f in files if f.suffix == ".txt"]
        meta = parse_metadata_txt(txt_files[0]) if txt_files else {}

        # Descartar órdenes médicas vigentes o pagos que aún esperan la emisión de la boleta (Nivel 0)
        if meta.get("estado_txt") in ("ORDEN_VIGENTE", "PENDIENTE_BOLETA"):
            continue

        has_payment_file = any(
            any(k in f.name.lower() for k in ("boleta", "factura", "voucher", "bono", "cuenta"))
            and f.suffix.lower() != ".txt"
            for f in files
        )
        if meta.get("monto", 0) == 0 and not has_payment_file:
            continue

        p_match = match_patient(f"{meta.get('paciente', '')} {meta.get('rut_paciente', '')}", patients)
        circuito = meta.get("circuito") or (p_match["circuito_consulta"] if p_match else "ISAPRE_SURA")
        next_step = "Enviar directo a SURA (80%)" if circuito == "SOLO_SURA" else (
            "Enviar a Banmédica y pasar directo a '3 pagadas'" if circuito == "SOLO_ISAPRE" else "Enviar a Banmédica"
        )

        items.append({
            "nivel": 1,
            "carpeta": folder.name,
            "directorio_relativo": f"0 INBOX/{folder.name}",
            "path": str(folder),
            "paciente": meta.get("paciente") or (p_match["canonical"] if p_match else "Sin especificar"),
            "rut_paciente": meta.get("rut_paciente") or (p_match["rut"] if p_match else ""),
            "prestacion": meta.get("prestacion") or folder.name,
            "fecha": normalize_date(meta.get("fecha", ""), folder.name),
            "documento": meta.get("documento") or "",
            "circuito": circuito,
            "monto": meta.get("monto", 0),
            "legacy": meta.get("legacy", False),
            "full_text": meta.get("full_text", ""),
            "archivos_enviar": [f.name for f in sorted(files) if f.suffix.lower() != ".txt"],
            "estado": next_step,
        })
    return items


def scan_level2(root: Path, patients: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Escanea '1 a isapre' buscando trámites en espera de liquidación o listos para enviar a SURA."""
    isapre_dir = root / "1 a isapre"
    items = []
    if not isapre_dir.is_dir():
        return items

    for folder in sorted(isapre_dir.iterdir()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue

        files = [f for f in folder.iterdir() if not f.name.startswith(".")]
        file_names = [f.name.lower() for f in files]
        has_settlement = any("comprobante-liquidacion" in fn for fn in file_names)

        txt_files = [f for f in files if f.suffix == ".txt"]
        meta = parse_metadata_txt(txt_files[0]) if txt_files else {}
        p_match = match_patient(f"{meta.get('paciente', '')} {meta.get('rut_paciente', '')}", patients)

        m_id = re.search(r"\b(\d{10,14})\b", folder.name)
        folder_id = m_id.group(1) if m_id else None
        isapre_id = folder_id or meta.get("id_isapre") or "En trámite"
        id_check = verify_banmedica_id(isapre_id)

        estado = "Liquidada por Banmédica (LISTA PARA ENVIAR A SURA UNO POR UNO)" if has_settlement else "En espera de liquidación Banmédica"

        items.append({
            "nivel": 2,
            "carpeta": folder.name,
            "directorio_relativo": f"1 a isapre/{folder.name}",
            "path": str(folder),
            "paciente": meta.get("paciente") or (p_match["canonical"] if p_match else "Sin especificar"),
            "rut_paciente": meta.get("rut_paciente") or (p_match["rut"] if p_match else ""),
            "prestacion": meta.get("prestacion") or folder.name,
            "fecha": normalize_date(meta.get("fecha", ""), folder.name),
            "isapre_id": isapre_id,
            "id_warning": id_check.get("warning"),
            "has_settlement": has_settlement,
            "monto": meta.get("monto", 0),
            "copago_isapre": meta.get("copago_isapre", 0),
            "estimado_sura_80": meta.get("monto_sura_estimado", 0),
            "legacy": meta.get("legacy", False),
            "full_text": meta.get("full_text", ""),
            "archivos_enviar_sura": [f.name for f in sorted(files) if f.suffix.lower() != ".txt"],
            "estado": estado,
        })
    return items


def scan_level3(root: Path, patients: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Escanea '2 a SURA' buscando trámites enviados a la espera de depósito bancario."""
    sura_dir = root / "2 a SURA"
    items = []
    if not sura_dir.is_dir():
        return items

    for folder in sorted(sura_dir.iterdir()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue

        txt_files = [f for f in folder.iterdir() if f.suffix == ".txt"]
        meta = parse_metadata_txt(txt_files[0]) if txt_files else {}
        p_match = match_patient(f"{meta.get('paciente', '')} {meta.get('rut_paciente', '')}", patients)

        m_id = re.search(r"\b(\d{7,9})\b", folder.name)
        folder_id = m_id.group(1) if m_id else None
        sura_id = folder_id or meta.get("id_sura") or "En trámite"
        id_check = verify_sura_id(sura_id)

        copago_presentado = meta.get("copago_isapre") or meta.get("monto", 0)
        monto_estimado = meta.get("monto_sura_estimado") or int(round(0.80 * copago_presentado))
        copago_bolsillo = meta.get("copago_bolsillo") or max(0, copago_presentado - monto_estimado)

        items.append({
            "nivel": 3,
            "carpeta": folder.name,
            "directorio_relativo": f"2 a SURA/{folder.name}",
            "path": str(folder),
            "paciente": meta.get("paciente") or (p_match["canonical"] if p_match else "Sin especificar"),
            "rut_paciente": meta.get("rut_paciente") or (p_match["rut"] if p_match else ""),
            "prestacion": meta.get("prestacion") or folder.name,
            "fecha": normalize_date(meta.get("fecha", ""), folder.name),
            "sura_id": sura_id,
            "id_warning": id_check.get("warning"),
            "monto_total": meta.get("monto_total", 0),
            "bonif_isapre": meta.get("bonif_isapre", 0),
            "copago_presentado": copago_presentado,
            "monto_estimado": monto_estimado,
            "copago_bolsillo": copago_bolsillo,
            "monto": monto_estimado,
            "legacy": meta.get("legacy", False),
            "full_text": meta.get("full_text", ""),
            "estado": "En espera de depósito SURA",
        })
    return items


# ==============================================================================
# AUTOEVALUACIÓN DEL PROCESO, DETECCIÓN DE DESVÍOS Y SALUD DE SCRIPTS
# ==============================================================================
def audit_health_and_deviations(root: Path, patients: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Verifica el estado de herramientas, que cada directorio y receta en RECETAS tenga su .txt, y audita reglas."""
    tool_alerts: List[str] = []
    process_alerts: List[str] = []

    # 1. Salud de pdftotext
    pdftotext_bin = shutil.which("pdftotext") or "/opt/homebrew/bin/pdftotext"
    if not Path(pdftotext_bin).exists():
        tool_alerts.append("CRÍTICO: No se encontró 'pdftotext' (poppler). Ofrecer instalar con 'brew install poppler'.")

    # 2. Salud de binario compilado tools/ocr
    ok_ocr, msg_ocr = ensure_ocr_binary(root)
    if not ok_ocr:
        tool_alerts.append(f"CRÍTICO: Fallo en binario 'tools/ocr': {msg_ocr}. Ofrecer recompilar 'swiftc -O tools/ocr.swift -o tools/ocr'.")

    # 3. Verificar carpetas ocultas prohibidas o AGENTS.md duplicado en 0 INBOX
    for forbidden in (".agents", ".claude", "AGENTS.md"):
        if (root / "0 INBOX" / forbidden).exists():
            process_alerts.append(f"DESVÍO DE ARQUITECTURA: Existe '0 INBOX/{forbidden}'. Debe eliminarse.")

    # 3b. Verificar que tools/changelog.md no contenga nombres ni RUTs de beneficiarios
    changelog_path = root / "tools" / "changelog.md"
    if changelog_path.exists() and patients:
        cl_norm = strip_accents(changelog_path.read_text(encoding="utf-8", errors="replace").lower())
        for p in patients:
            full_p = strip_accents(p["canonical"].lower())
            rut_p = p["rut"].lower()
            if (full_p and full_p in cl_norm) or (rut_p and rut_p in cl_norm):
                process_alerts.append(
                    f"DATOS PERSONALES EN CHANGELOG: 'tools/changelog.md' contiene datos del beneficiario '{p['canonical']}'. "
                    "El changelog solo debe registrar cambios técnicos del flujo."
                )

    # 4. Verificar que todo archivo en RECETAS/ (y RECETAS/archivadas/) tenga su .txt homónimo obligatorio
    recetas_dir = root / "RECETAS"
    if recetas_dir.is_dir():
        for sub in (recetas_dir, recetas_dir / "archivadas"):
            if not sub.is_dir():
                continue
            for rf in sorted(sub.iterdir()):
                if rf.is_dir() or rf.name.startswith(".") or rf.name.lower() in ("readme.md", ".gitkeep"):
                    continue
                if rf.suffix.lower() in (".jpg", ".jpeg", ".png", ".pdf"):
                    expected_txt = rf.with_suffix(".txt")
                    if not expected_txt.exists():
                        rel_rf = rf.relative_to(root)
                        process_alerts.append(
                            f"FALTA .TXT EN RECETAS: El documento '{rel_rf}' no tiene su archivo '{expected_txt.name}' obligatorio. "
                            f"El agente debe extraer su texto (--extract) y generar '{expected_txt.relative_to(root)}'."
                        )

    # 5. Verificar que toda subcarpeta activa en 0 INBOX, 1 a isapre y 2 a SURA tenga su .txt y cumpla su circuito
    for stage_name in ("0 INBOX", "1 a isapre", "2 a SURA"):
        stage_dir = root / stage_name
        if not stage_dir.is_dir():
            continue
        for folder in sorted(stage_dir.iterdir()):
            if not folder.is_dir() or folder.name.startswith(".") or folder.name in ("Duplicados", "tools"):
                continue
            txts = [f for f in folder.iterdir() if f.suffix == ".txt"]
            if not txts:
                process_alerts.append(
                    f"FALTA .TXT EN DIRECTORIO: La carpeta '{stage_name}/{folder.name}' no tiene archivo .txt que la resuma."
                )
                continue

            meta = parse_metadata_txt(txts[0])
            p_match = match_patient(f"{meta.get('paciente', '')} {meta.get('rut_paciente', '')}", patients)
            circuito = meta.get("circuito") or (p_match["circuito_consulta"] if p_match else "")

            if circuito == "SOLO_ISAPRE" and stage_name in ("1 a isapre", "2 a SURA"):
                process_alerts.append(
                    f"DESVÍO DE CIRCUITO (SOLO_ISAPRE): '{stage_name}/{folder.name}' está en '{stage_name}', "
                    "pero el circuito SOLO_ISAPRE pasa directo de '0 INBOX' a '3 pagadas'."
                )

            if circuito == "SOLO_SURA" and stage_name == "1 a isapre":
                process_alerts.append(
                    f"DESVÍO DE CIRCUITO (SOLO_SURA): '{stage_name}/{folder.name}' está en '1 a isapre', "
                    "pero el circuito SOLO_SURA va directo de '0 INBOX' a '2 a SURA'."
                )

            mt = meta.get("monto_total", 0)
            bi = meta.get("bonif_isapre", 0)
            ci = meta.get("copago_isapre", 0)
            if mt > 0 and bi > 0 and ci > 0 and (mt - bi != ci):
                process_alerts.append(
                    f"DESCUADRE MATEMÁTICO en '{stage_name}/{folder.name}': "
                    f"MONTO_TOTAL ({mt}) - BONIFICACION_ISAPRE ({bi}) != COPAGO_ISAPRE ({ci})."
                )

    # 6. Archivos recientes en ~/Downloads pendientes de mover (mv)
    recent_dl = scan_downloads(minutes_window=60)
    if recent_dl:
        names = ", ".join(f"{d['name']} (hace {d['age_minutes']} min)" for d in recent_dl)
        process_alerts.append(f"ARCHIVOS RECIENTES EN ~/Downloads POR MOVER (mv): {names}")

    return {
        "healthy": len(tool_alerts) == 0 and len(process_alerts) == 0,
        "tool_alerts": tool_alerts,
        "process_alerts": process_alerts,
        "recent_downloads": recent_dl,
    }


# ==============================================================================
# GENERADOR DE HISTORIALES DESDE ARCHIVOS .TXT (SIN HARDCODING, OPCIONAL CON --historiales)
# ==============================================================================
def classify_category_from_meta(meta: Dict[str, Any], folder_name: str) -> str:
    """Clasifica un registro en MEDICAMENTO, EXAMEN o CONSULTA a partir de su .txt."""
    text = f"{meta.get('prestacion', '')} {meta.get('circuito', '')} {folder_name}".lower()
    if meta.get("circuito") == "SOLO_SURA" or any(k in text for k in ("medicamento", "farmacia", "receta")):
        return "MEDICAMENTO"
    if any(k in text for k in ("examen", "exámenes", "derivacion", "derivación", "interconsulta", "laboratorio", "biopsia", "histopatologico", "bioimpedanciometria", "hba1c")):
        return "EXAMEN"
    return "CONSULTA"


def generate_patient_histories(root: Path, patients: List[Dict[str, Any]]) -> List[str]:
    """Genera los archivos HISTORIAL_<PERSONA>.md leyendo exclusivamente los archivos .txt de cada carpeta y de RECETAS/."""
    if not patients:
        return []

    records_by_rut: Dict[str, List[Dict[str, Any]]] = {p["rut"]: [] for p in patients}
    cutoff_date = (datetime.now() - timedelta(days=366)).strftime("%Y-%m-%d")

    for stage_dir_name in ("0 INBOX", "1 a isapre", "2 a SURA", "3 pagadas"):
        sdir = root / stage_dir_name
        if not sdir.is_dir():
            continue
        for folder in sorted(sdir.iterdir()):
            if not folder.is_dir() or folder.name.startswith(".") or folder.name in ("Duplicados", "tools"):
                continue
            txts = sorted([f for f in folder.iterdir() if f.suffix == ".txt"])
            if not txts:
                continue
            meta = parse_metadata_txt(txts[0])
            fecha = normalize_date(meta.get("fecha", ""), folder.name)
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", fecha) or fecha < cutoff_date:
                continue

            p_match = match_patient(f"{meta.get('paciente', '')} {meta.get('rut_paciente', '')} {meta.get('full_text', '')}", patients)
            if not p_match:
                continue

            cat = classify_category_from_meta(meta, folder.name)
            prest = meta.get("prestacion") or folder.name
            prov = meta.get("proveedor") or "—"

            records_by_rut[p_match["rut"]].append({
                "fecha": fecha,
                "categoria": cat,
                "prestacion": prest,
                "proveedor": prov,
                "legacy": meta.get("legacy", False),
            })

    # Recetas vigentes desde RECETAS/*.txt
    recetas_by_rut: Dict[str, List[Dict[str, Any]]] = {p["rut"]: [] for p in patients}
    recetas_dir = root / "RECETAS"
    if recetas_dir.is_dir():
        for txt_f in sorted(recetas_dir.glob("*.txt")):
            rmeta = parse_metadata_txt(txt_f)
            p_match = match_patient(f"{rmeta.get('paciente', '')} {rmeta.get('rut_paciente', '')} {rmeta.get('full_text', '')}", patients)
            if not p_match:
                continue
            fec_em = normalize_date(rmeta.get("fecha", ""), txt_f.name)
            vence_str = "—"
            if re.match(r"^\d{4}-\d{2}-\d{2}$", fec_em):
                dt_em = datetime.strptime(fec_em, "%Y-%m-%d")
                dt_exp = dt_em + timedelta(days=180)
                days_left = (dt_exp.date() - datetime.now().date()).days
                vence_str = f"`{dt_exp.strftime('%Y-%m-%d')}` ({days_left} días)"
            recetas_by_rut[p_match["rut"]].append({
                "fecha": fec_em,
                "prestacion": rmeta.get("prestacion") or txt_f.stem,
                "proveedor": rmeta.get("proveedor") or "—",
                "vence": vence_str,
            })

    generated_files = []
    for p in patients:
        rut = p["rut"]
        recs = sorted(records_by_rut.get(rut, []), key=lambda r: r["fecha"], reverse=True)
        consultas = [r for r in recs if r["categoria"] == "CONSULTA"]
        examenes = [r for r in recs if r["categoria"] == "EXAMEN"]
        medicamentos = [r for r in recs if r["categoria"] == "MEDICAMENTO"]
        recetas_vig = recetas_by_rut.get(rut, [])

        lines = [
            f"# Historial Médico Anual — {p['canonical']}",
            "",
            f"* **Paciente:** {p['canonical']} (`{p['rut']}`)",
            f"* **Período:** Últimos 12 meses (desde `{cutoff_date}`)",
            "",
            "---",
            "",
            "## 1. Consultas Médicas, Procedimientos y Hospitalizaciones",
            "| Fecha | Especialidad / Atención | Médico / Centro |",
            "| :--- | :--- | :--- |",
        ]
        if consultas:
            for r in consultas:
                lines.append(f"| `{r['fecha']}` | {r['prestacion']} | {r['proveedor']} |")
        else:
            lines.append("| — | *Sin consultas registradas en el último año* | — |")

        lines.extend([
            "",
            "---",
            "",
            "## 2. Exámenes de Laboratorio y Derivaciones",
            "| Fecha | Examen / Derivación | Médico / Centro |",
            "| :--- | :--- | :--- |",
        ])
        if examenes:
            for r in examenes:
                lines.append(f"| `{r['fecha']}` | {r['prestacion']} | {r['proveedor']} |")
        else:
            lines.append("| — | *Sin exámenes ni derivaciones registradas en el último año* | — |")

        lines.extend([
            "",
            "---",
            "",
            "## 3. Medicamentos",
            "| Fecha | Medicamento(s) | Médico / Proveedor |",
            "| :--- | :--- | :--- |",
        ])
        if medicamentos:
            for r in medicamentos:
                lines.append(f"| `{r['fecha']}` | {r['prestacion']} | {r['proveedor']} |")
        else:
            lines.append("| — | *Sin compras de medicamentos registradas en el último año* | — |")

        if recetas_vig:
            lines.extend([
                "",
                "---",
                "",
                "## 4. Recetas Permanentes Vigentes (180 días)",
                "| Fecha Emisión | Medicamentos Recetados | Médico | Vence |",
                "| :--- | :--- | :--- | :--- |",
            ])
            for rv in recetas_vig:
                lines.append(f"| `{rv['fecha']}` | {rv['prestacion']} | {rv['proveedor']} | {rv['vence']} |")

        out_file = root / p["historial_file"]
        out_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        generated_files.append(p["historial_file"])

    return generated_files


# ==============================================================================
# CONSOLIDACIÓN DE AUDITORÍA Y RENDERIZADO
# ==============================================================================
def audit_reimbursements(root: Path) -> Dict[str, Any]:
    """Ejecuta la auditoría completa determinista sobre el repositorio."""
    patients = load_patients_from_agents_md(root)
    l0 = scan_level0(root, patients)
    l1 = scan_level1(root, patients)
    l2 = scan_level2(root, patients)
    l3 = scan_level3(root, patients)
    health = audit_health_and_deviations(root, patients)

    t0 = sum(i["monto"] for i in l0)
    t1 = sum(i["monto"] for i in l1)
    t2 = sum(i["monto"] for i in l2)
    t3_copago = sum(i["copago_presentado"] for i in l3)
    t3_estimado = sum(i["monto_estimado"] for i in l3)
    t3_bolsillo = sum(i["copago_bolsillo"] for i in l3)

    return {
        "root": str(root),
        "patients": patients,
        "nivel_0": {"items": l0, "total": t0},
        "nivel_1": {"items": l1, "total": t1},
        "nivel_2": {"items": l2, "total": t2},
        "nivel_3": {
            "items": l3,
            "total_copago": t3_copago,
            "total_estimado": t3_estimado,
            "total_bolsillo": t3_bolsillo,
            "total": t3_estimado,
        },
        "total_global": t0 + t1 + t2 + t3_estimado,
        "health_and_audit": health,
    }


def render_markdown(data: Dict[str, Any]) -> str:
    """Genera la representación en Markdown de PENDIENTES_MEDICOS.md."""
    lines = [
        "# Estado de Reembolsos Médicos Pendientes (PENDIENTES_MEDICOS.md)",
        "",
        "Este documento consolida el estado en tiempo real de los reembolsos calculado por `tools/pendientes.py`.",
        "",
        "## Historiales Clínicos Anuales por Persona",
    ]
    for p in data.get("patients", []):
        lines.append(f"* [{p['historial_file']}]({p['historial_file']}) — {p['canonical']} (`{p['rut']}`)")

    n0 = data.get("nivel_0", {"items": [], "total": 0})
    lines.extend([
        "",
        "---",
        "",
        "## 0. Nivel 0: Pagos Realizados Sin Boleta (Reclamar Boleta al Médico en `0 INBOX`)",
        "| Directorio | Paciente | Médico / Proveedor | Fecha Pago | Días Espera | Monto Transferido | Siguiente Paso |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ])
    for it in n0["items"]:
        lines.append(
            f"| `0 INBOX/{it['carpeta']}` | {it['paciente']} | **{it['proveedor']}** | `{it['fecha']}` | **{it['dias_espera']} día(s)** | {format_currency(it['monto'])} | ⚠️ {it['estado']} |"
        )
    lines.append(f"\n* **Total Nivel 0 (Sin Boleta):** **{format_currency(n0['total'])}**\n")

    lines.extend([
        "---",
        "",
        "## 1. Nivel 1: Pendientes en `0 INBOX` (Con Boleta — Por enviar a Isapre o directo a SURA)",
        "| Directorio | Paciente | RUT | Prestación | Fecha | Circuito | Monto | Siguiente Paso |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ])
    for it in data["nivel_1"]["items"]:
        lines.append(
            f"| `0 INBOX/{it['carpeta']}` | {it['paciente']} | `{it['rut_paciente']}` | {it['prestacion']} | `{it['fecha']}` | `{it['circuito']}` | {format_currency(it['monto'])} | {it['estado']} |"
        )
    lines.append(f"\n* **Total Nivel 1:** **{format_currency(data['nivel_1']['total'])}**\n")

    lines.append("---")
    lines.append("\n## 2. Nivel 2: Pendientes en `1 a isapre` (Esperando liquidación Banmédica o paso a SURA)")
    lines.append("| Directorio | Paciente | RUT | Prestación | ID Banmédica | Monto | Siguiente Paso |")
    lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    for it in data["nivel_2"]["items"]:
        warn_note = f" ⚠️ *({it['id_warning']})*" if it.get("id_warning") else ""
        next_step = "Enviar archivos uno por uno a WhatsApp SURA" if it.get("has_settlement") else "Esperar Comprobante-Liquidacion en ~/Downloads"
        lines.append(
            f"| `1 a isapre/{it['carpeta']}` | {it['paciente']} | `{it['rut_paciente']}` | {it['prestacion']} | `{it['isapre_id']}`{warn_note} | {format_currency(it['monto'])} | {next_step} |"
        )
    lines.append(f"\n* **Total Nivel 2:** **{format_currency(data['nivel_2']['total'])}**\n")

    lines.append("---")
    lines.append("\n## 3. Nivel 3: Pendientes en `2 a SURA` (Esperando depósito bancario SURA)")
    lines.append("| Directorio | Paciente | Detalle | ID SURA | Copago Presentado | Estimado SURA (80%) | Copago Final Bolsillo (20%) | Siguiente Paso |")
    lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    for it in data["nivel_3"]["items"]:
        warn_note = f" ⚠️ *({it['id_warning']})*" if it.get("id_warning") else ""
        lines.append(
            f"| `2 a SURA/{it['carpeta']}` | {it['paciente']} | {it['prestacion']} | `{it['sura_id']}`{warn_note} | {format_currency(it['copago_presentado'])} | **{format_currency(it['monto_estimado'])}** | {format_currency(it['copago_bolsillo'])} | Esperar depósito en cuenta bancaria |"
        )

    n3 = data["nivel_3"]
    lines.append(f"\n* **Total Copago Presentado a SURA:** {format_currency(n3['total_copago'])}")
    lines.append(f"* **Total Estimado a Depositar por SURA (80% Cobertura):** **{format_currency(n3['total_estimado'])}**")
    lines.append(f"* **Total Copago Final Estimado (20% Bolsillo):** {format_currency(n3['total_bolsillo'])}\n")

    lines.append("---")
    lines.append("\n## Resumen Consolidado")
    lines.append(f"* **Total Pagos Sin Boleta en `0 INBOX` (Nivel 0):** {format_currency(n0['total'])}")
    lines.append(f"* **Total Con Boleta en `0 INBOX` (Nivel 1):** {format_currency(data['nivel_1']['total'])}")
    lines.append(f"* **Total En Trámite Isapre (Nivel 2):** {format_currency(data['nivel_2']['total'])}")
    lines.append(f"* **Total En Trámite SURA - Copago Ingresado:** {format_currency(data['nivel_3']['total_copago'])}")
    lines.append(f"* **Total Estimado a Recibir de SURA (80%):** **{format_currency(data['nivel_3']['total_estimado'])}**")
    lines.append(f"* **Monto Global en Curso / por Recuperar:** **{format_currency(data['total_global'])}**")

    return "\n".join(lines) + "\n"


def render_terminal(data: Dict[str, Any]) -> str:
    """Genera una salida amigable y estructurada para terminal con auditoría de salud."""
    out = []
    out.append("================================================================================")
    out.append("               AUDITORÍA EN TIEMPO REAL: REEMBOLSOS PENDIENTES                  ")
    out.append("================================================================================")

    n0 = data.get("nivel_0", {"items": [], "total": 0})
    out.append(f"\n[NIVEL 0] PAGOS SIN BOLETA — RECLAMAR AL MÉDICO (en '0 INBOX'): {len(n0['items'])} ítem(s)")
    out.append("-" * 80)
    for it in n0["items"]:
        out.append(f" ⚠️ Directorio: {it['directorio_relativo']}")
        out.append(f"    Médico / Proveedor: {it['proveedor']} | Paciente: {it['paciente']}")
        out.append(f"    Fecha Pago: {it['fecha']} (hace {it['dias_espera']} día(s)) | Monto Transferido: {format_currency(it['monto'])}")
        out.append(f"    Acción: {it['estado']}")
    out.append(f"   >>> SUBTOTAL NIVEL 0 (SIN BOLETA): {format_currency(n0['total'])}")

    out.append(f"\n[NIVEL 1] PENDIENTES CON BOLETA EN '0 INBOX': {len(data['nivel_1']['items'])} ítem(s)")
    out.append("-" * 80)
    for it in data["nivel_1"]["items"]:
        out.append(f" • Directorio: {it['directorio_relativo']}")
        out.append(f"   Paciente: {it['paciente']} (RUT: {it['rut_paciente']}) | Circuito: {it['circuito']}")
        out.append(f"   Prestación: {it['prestacion']} | Monto: {format_currency(it['monto'])}")
        out.append(f"   Archivos individuales: {', '.join(it['archivos_enviar'])}")
        if it.get("legacy"):
            out.append("   [LEGACY: true — Revisar texto libre completo del .txt para decisiones]")
    out.append(f"   >>> SUBTOTAL NIVEL 1: {format_currency(data['nivel_1']['total'])}")

    out.append(f"\n[NIVEL 2] EN TRÁMITE ISAPRE ('1 a isapre'): {len(data['nivel_2']['items'])} ítem(s)")
    out.append("-" * 80)
    for it in data["nivel_2"]["items"]:
        warn_str = f" ⚠️ [{it['id_warning']}]" if it.get("id_warning") else ""
        out.append(f" • Directorio: {it['directorio_relativo']}")
        out.append(f"   Paciente: {it['paciente']} (RUT: {it['rut_paciente']}) | ID Isapre: {it['isapre_id']}{warn_str}")
        out.append(f"   Monto: {format_currency(it['monto'])} | Estado: {it['estado']}")
        if it.get("has_settlement"):
            out.append(f"   Archivos individuales para arrastrar a SURA: {', '.join(it['archivos_enviar_sura'])}")
        if it.get("legacy"):
            out.append("   [LEGACY: true — Revisar texto libre completo del .txt para decisiones]")
    out.append(f"   >>> SUBTOTAL NIVEL 2: {format_currency(data['nivel_2']['total'])}")

    out.append(f"\n[NIVEL 3] EN TRÁMITE SEGURO SURA ('2 a SURA'): {len(data['nivel_3']['items'])} ítem(s)")
    out.append("-" * 80)
    for it in data["nivel_3"]["items"]:
        warn_str = f" ⚠️ [{it['id_warning']}]" if it.get("id_warning") else ""
        out.append(f" • Directorio: {it['directorio_relativo']}")
        out.append(f"   Paciente: {it['paciente']} (RUT: {it['rut_paciente']}) | ID Siniestro SURA: {it['sura_id']}{warn_str}")
        out.append(
            f"   Copago Presentado: {format_currency(it['copago_presentado'])} | "
            f"Estimado SURA (80%): {format_currency(it['monto_estimado'])} | "
            f"Copago Bolsillo (20%): {format_currency(it['copago_bolsillo'])}"
        )
        if it.get("legacy"):
            out.append("   [LEGACY: true — Revisar texto libre completo del .txt para decisiones]")
    out.append(f"   >>> TOTAL COPAGO PRESENTADO SURA: {format_currency(data['nivel_3']['total_copago'])}")
    out.append(f"   >>> TOTAL ESTIMADO A RECIBIR SURA (80%): {format_currency(data['nivel_3']['total_estimado'])}")
    out.append(f"   >>> TOTAL COPAGO FINAL BOLSILLO (20%): {format_currency(data['nivel_3']['total_bolsillo'])}")

    h = data.get("health_and_audit", {})
    out.append("\n[SALUD DE HERRAMIENTAS Y AUDITORÍA DE PROCESO]")
    out.append("-" * 80)
    if h.get("healthy"):
        out.append(" ✓ Herramientas ('pdftotext', binario 'tools/ocr'), archivos .txt en RECETAS/directorios y reglas 100% OK.")
    else:
        for ta in h.get("tool_alerts", []):
            out.append(f" ❌ [HERRAMIENTA] {ta}")
        for pa in h.get("process_alerts", []):
            out.append(f" ⚠️ [PROCESO/REGLA] {pa}")

    out.append("================================================================================")
    out.append(f" TOTAL ESTIMADO A RECUPERAR (GLOBAL): {format_currency(data['total_global'])}")
    out.append("================================================================================")
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(description="Motor determinista de reembolsos médicos y auditoría (0% hardcoding)")
    parser.add_argument("--json", action="store_true", help="Salida en formato JSON")
    parser.add_argument("--markdown", action="store_true", help="Salida en formato Markdown")
    parser.add_argument("--update", action="store_true", help="Actualiza PENDIENTES_MEDICOS.md")
    parser.add_argument("--historiales", action="store_true", help="Regenera los archivos HISTORIAL_<PERSONA>.md desde los .txt")
    parser.add_argument("--scan-downloads", action="store_true", help="Lista archivos médicos recientes en ~/Downloads")
    parser.add_argument("--match-liquidaciones", action="store_true", help="Cruza y mueve (mv) Comprobante-Liquidacion-*.pdf desde ~/Downloads a '1 a isapre'")
    parser.add_argument("--minutes", type=int, default=60, help="Ventana en minutos para escanear ~/Downloads (default: 60)")
    parser.add_argument("--extract", type=str, help="Extrae texto de un archivo con motor híbrido (pdftotext -layout -> tools/ocr)")
    parser.add_argument("--copy-rut", type=str, help="Copia el RUT del paciente indicado (leído desde AGENTS.md) a pbcopy")
    parser.add_argument("--health", action="store_true", help="Ejecuta autoevaluación de salud de scripts, binarios y reglas")
    parser.add_argument("--verify-id", type=str, help="Verifica la sintaxis de un ID Banmédica o SURA")
    args = parser.parse_args()

    root = find_repo_root()
    patients = load_patients_from_agents_md(root)

    if args.extract:
        res = extract_text_hybrid(Path(args.extract), root)
        print(f"[ENGINE: {res.get('engine')}]")
        if res.get("error"):
            print(f"[ERROR: {res.get('error')}]", file=sys.stderr)
        print(res.get("text", ""))
        return

    if args.copy_rut:
        p_match = match_patient(args.copy_rut, patients)
        if not p_match:
            print(f"Error: No se encontró paciente '{args.copy_rut}' en la tabla de AGENTS.md.", file=sys.stderr)
            sys.exit(1)
        subprocess.run(["pbcopy"], input=p_match["rut"], text=True, check=False)
        print(f"✓ RUT de {p_match['canonical']} ({p_match['rut']}) copiado al portapapeles (pbcopy).")
        return

    if args.scan_downloads:
        items = scan_downloads(minutes_window=args.minutes)
        print(json.dumps(items, indent=2, ensure_ascii=False))
        return

    if args.match_liquidaciones:
        moved = match_and_move_liquidaciones(root, minutes_window=args.minutes)
        print(json.dumps(moved, indent=2, ensure_ascii=False))
        return

    if args.health:
        h = audit_health_and_deviations(root, patients)
        print(json.dumps(h, indent=2, ensure_ascii=False))
        return

    if args.verify_id:
        val = args.verify_id.strip()
        chk_ban = verify_banmedica_id(val)
        chk_sura = verify_sura_id(val)
        print(f"Verificación de sintaxis para ID '{val}':")
        if chk_ban["valid"]:
            print("  ✓ Formato válido para ID Isapre Banmédica (12 dígitos, prefijo '6000')")
        elif chk_sura["valid"]:
            print("  ✓ Formato válido para ID Siniestro SURA (8 dígitos)")
        else:
            print("  ⚠️ Advertencias de formato:")
            print(f"    - Banmédica: {chk_ban['warning']}")
            print(f"    - SURA: {chk_sura['warning']}")
        return

    if args.historiales:
        gen = generate_patient_histories(root, patients)
        print(f"✓ Historiales generados exitosamente desde los archivos .txt: {', '.join(gen)}")
        return

    data = audit_reimbursements(root)

    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    elif args.markdown:
        print(render_markdown(data))
    elif args.update:
        md_text = render_markdown(data)
        doc_path = root / "PENDIENTES_MEDICOS.md"
        doc_path.write_text(md_text, encoding="utf-8")
        print(f"✓ PENDIENTES_MEDICOS.md actualizado exitosamente.")
        print(f"✓ Total global estimado a recuperar: {format_currency(data['total_global'])}")
        h = data.get("health_and_audit", {})
        if not h.get("healthy"):
            for ta in h.get("tool_alerts", []):
                print(f"  ❌ [HERRAMIENTA] {ta}")
            for pa in h.get("process_alerts", []):
                print(f"  ⚠️ [PROCESO/REGLA] {pa}")
    else:
        print(render_terminal(data))


if __name__ == "__main__":
    main()
