"""
tests/test_ortografia_ui_text.py — os textos PT do backoffice (`ui_text/pt-PT.json`,
os que o cliente lê no GAIBO) não usam formas anteriores ao Acordo Ortográfico
em vigor (30 Set 2026, decisão do Bruno). Só os VALORES contam — as chaves são
caminhos do schema (`compliance.sector` é o nome do campo e fica).

Lista fechada, revista palavra a palavra; ficam de fora as palavras cuja
consoante se pronuncia em PT-PT (facto, contacto, secção, intacto…). A mesma
lista do guarda do Studio (`backend/tests/test_ortografia_pt.py`), copiada por
inteiro (o schema não depende do Studio): palavra nova lá → nova aqui. Caminhos
com pontos (`compliance.sector`) são nomes de campo e ficam de fora.
"""

import json
import re
from pathlib import Path

FORMAS_ANTIGAS = {
    "acciona", "accionado", "accionados", "accionar", "accionável", "acta", "actas", "activa", "activada",
    "activado", "activar", "activaram", "activas", "activação", "actividade", "activo", "activos", "acto",
    "actos", "actuais", "actual", "actualiza", "actualizada", "actualizadas", "actualizado", "actualizados",
    "actualizar", "actualização", "actualizações", "actualizável", "actualmente", "actuação", "acção", "acções",
    "adoptado", "adoptar", "adoptou", "afecta", "afectada", "afectadas", "afectado", "afectados", "afectar",
    "aspecto", "aspectos", "correcta", "correctamente", "correctas", "correcto", "correctos", "correcção",
    "correcções", "crêem", "desactivada", "desactivadas", "desactivado", "desactivados", "desactivar",
    "desactualizada", "desactualizado", "detecta", "detectada", "detectadas", "detectado", "detectados",
    "detectar", "detector", "detecção", "directa", "directamente", "directas", "directo", "directos",
    "directório", "direcção", "dêem", "efectiva", "efectivamente", "efectivo", "electricidade", "exacta",
    "exactamente", "exactas", "exacto", "exactos", "excepto", "excepção", "excepções", "extractivo", "extracto",
    "extractor", "extracção", "extracções", "factura", "facturada", "facturas", "facturação", "fracção",
    "inactividade", "incorrecta", "incorrectas", "incorrecto", "incorrectos", "injecta", "injectada",
    "injectadas", "injectado", "injectar", "injecção", "interactivo", "interactivos", "lêem", "nocturna",
    "objectivo", "objectivos", "objecto", "objectos", "optimizado", "optimizar", "optimização",
    "proactivamente", "projecto", "projectos", "protecção", "pára", "reactiva", "reactivar", "redacção",
    "redireccionamento", "redireccionamentos", "redireccionar", "reflecte", "reflectir", "respectiva",
    "respectivas", "respectivo", "respectivos", "retroactivas", "retroactivo", "sector", "sectores",
    "selecciona", "seleccionada", "seleccionadas", "seleccionado", "seleccionados", "seleccionar", "seleccione",
    "seleccionou", "selectiva", "selectivo", "selector", "selecção", "tecto", "tectos", "vector", "vectores",
    "vectorial", "vêem", "óptimo",
}
_TICK = re.compile(r"`[^`\n]*`")
_CAMINHO = re.compile(r"\b[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+\b")   # compliance.sector: nome de campo


def _valores(no, caminho=""):
    if isinstance(no, dict):
        for k, v in no.items():
            yield from _valores(v, f"{caminho}.{k}" if caminho else k)
    elif isinstance(no, list):
        for i, v in enumerate(no):
            yield from _valores(v, f"{caminho}[{i}]")
    elif isinstance(no, str):
        yield caminho, no


def test_textos_pt_do_backoffice_sem_formas_antigas():
    p = Path(__file__).resolve().parents[1] / "genesis_profile_schema" / "ui_text" / "pt-PT.json"
    erros = []
    for caminho, texto in _valores(json.loads(p.read_text(encoding="utf-8"))):
        limpo = _CAMINHO.sub(" ", _TICK.sub(" ", texto))
        achadas = [w for w in re.findall(r"[A-Za-zÀ-ÿ]+", limpo) if w.lower() in FORMAS_ANTIGAS]
        if achadas:
            erros.append(f"{caminho}: {', '.join(achadas)}")
    assert erros == [], "Formas anteriores ao Acordo Ortográfico em pt-PT.json:\n" + "\n".join(erros[:40])
