"""
Gate do registo de regras da casa (`house_rules.py` + `house_rules/*.json`).

A promessa é de COERÊNCIA, não de prosa: um id sem texto numa das línguas, uma
classe fora do conjunto, um lever que aponta para um caminho que o schema não
tem, ou uma regra de classe LEVER cujo lever o cliente não pode escrever —
tudo isto chegaria a um editor como um aviso que aponta para o vazio. O
`exposure_of` cai em `internal` para caminhos desconhecidos sem se queixar, e
é exactamente por isso que aqui se verifica contra as FOLHAS do schema.
"""

import pytest

from genesis_profile_schema import exposure as exp
from genesis_profile_schema import house_rules as hr


def _known_path(path: str) -> bool:
    leaves = exp.leaf_paths()
    return path in leaves or any(l.startswith(path + ".") for l in leaves)


# ── forma do registo ─────────────────────────────────────────────────────────

def test_ha_regras_e_ids_unicos():
    ids = hr.rule_ids()
    assert len(ids) >= 16
    assert len(set(ids)) == len(ids)


@pytest.mark.parametrize("rule_id", hr.rule_ids())
def test_cada_regra_tem_a_forma_esperada(rule_id):
    entry = hr.rule(rule_id)
    assert entry is not None
    assert entry["class"] in hr.CLASSES, f"'{rule_id}' com classe fora de CLASSES"
    assert entry["enforcement"] in hr.ENFORCEMENT_KINDS
    assert isinstance(entry["enforcement_note"], str) and entry["enforcement_note"].strip()
    assert isinstance(entry["lever_paths"], tuple)
    anchor = entry["anchor"]
    assert anchor is None or (isinstance(anchor, str) and len(anchor) >= 12), (
        f"'{rule_id}': a âncora tem de ser uma frase literal do prompt_builder "
        "(>= 12 chars) ou None quando o portão é só código/config"
    )


@pytest.mark.parametrize("rule_id", hr.rule_ids())
def test_regras_so_prompt_tem_ancora(rule_id):
    """Uma regra cuja garantia é SÓ o prompt não pode ficar sem frase a vigiar —
    seria um registo a descrever um prompt que ninguém confirma."""
    entry = hr.rule(rule_id)
    if entry["enforcement"] == "prompt":
        assert entry["anchor"], f"'{rule_id}' é só prompt e não tem anchor"


@pytest.mark.parametrize("rule_id", hr.rule_ids())
def test_lever_paths_existem_no_schema(rule_id):
    for path in hr.rule(rule_id)["lever_paths"]:
        assert _known_path(path), (
            f"'{rule_id}' aponta para '{path}', que não é folha nem ramo do schema. "
            "Um aviso que manda o cliente para um campo inexistente é pior do que "
            "nenhum aviso."
        )


@pytest.mark.parametrize("rule_id", hr.rules_of(hr.LEVER))
def test_regra_de_classe_lever_tem_lever_escrevivel_ou_nota(rule_id):
    """Se dizemos ao cliente 'usa o campo em vez de prosa', o campo tem de ser
    escrevível por ele — ou a nota tem de dizer onde está o lever."""
    entry = hr.rule(rule_id)
    writable = [p for p in entry["lever_paths"] if exp.exposure_of(p) == exp.CLIENT_WRITE]
    assert writable or "tools.config" in entry["enforcement_note"], (
        f"'{rule_id}' é LEVER mas nenhum lever_path é client_write e a nota não "
        "diz onde o lever vive"
    )


def test_severidade_por_classe_cobre_todas_as_classes():
    assert set(hr.SEVERITY_BY_CLASS) == set(hr.CLASSES)
    for rule_id in hr.rule_ids():
        assert hr.severity_for(rule_id) in hr.SEVERITY_BY_CLASS.values()
    assert hr.severity_for("nao_existe") is None
    assert hr.rule("nao_existe") is None


def test_invariantes_declarados_explicitamente():
    """Lista fechada, com motivo: promover ou despromover uma regra é uma
    decisão de produto e muda o que o lint diz ao cliente ('sem efeito' vs
    'aviso'). Muda-se AQUI no mesmo commit, e explica-se."""
    esperados = {
        "grounded_only": "grounding_gate força a tool no turno 1",
        "period_not_from_name": "trigger coluna_sem_cabecalho / trigger M",
        "response_language": "excepção declarada + output guard expected_script",
        "prompt_secrecy": "_prompt_leak_refusal",
        "ai_disclosure": "core/compliance/ai_disclosure.py",
        "image_provenance": "core/compliance/ai_marking.py",
        "brand_safety": "brand_safety.py hard_block/post_filter",
        "action_confirmation": "gate de confirmação determinístico",
    }
    assert set(hr.rules_of(hr.INVARIANT)) == set(esperados), (
        "A lista de invariantes mudou. Um invariante só é invariante com portão "
        "em código — confirma o portão e actualiza esta lista no mesmo commit."
    )


def test_anchored_rules_so_devolve_regras_com_ancora():
    anch = hr.anchored_rules()
    assert anch
    for rule_id, anchor in anch.items():
        assert hr.rule(rule_id)["anchor"] == anchor
    for rule_id in hr.rule_ids():
        if hr.rule(rule_id)["anchor"] is None:
            assert rule_id not in anch


def test_all_rules_devolve_copias():
    a = hr.all_rules()
    a["grounded_only"]["class"] = "x"
    assert hr.rule("grounded_only")["class"] == hr.INVARIANT


# ── texto por língua ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("locale", hr.LOCALES)
def test_cada_lingua_cobre_todas_as_regras_com_todas_as_chaves(locale):
    textos = hr.texts(locale)
    assert set(textos) == set(hr.rule_ids()), (
        f"{locale}: o texto e o registo divergem — em falta "
        f"{set(hr.rule_ids()) - set(textos)}, a mais {set(textos) - set(hr.rule_ids())}"
    )
    for rule_id, rec in textos.items():
        assert set(rec) == set(hr.TEXT_KEYS), f"{locale}/{rule_id}: chaves {set(rec)}"
        for key in ("title", "summary", "boundary", "example_ok"):
            assert isinstance(rec[key], str) and rec[key].strip(), f"{locale}/{rule_id}/{key} vazio"
        assert isinstance(rec["example_conflict"], str)


def test_as_duas_linguas_cobrem_os_mesmos_ids():
    assert set(hr.texts("pt-PT")) == set(hr.texts("en-GB"))


@pytest.mark.parametrize("rule_id", hr.rule_ids())
def test_example_conflict_so_falta_em_guidance(rule_id):
    """Uma regra que o cliente pode chocar tem de mostrar COMO se choca — é o
    exemplo que o lint dá ao LLM e ao utilizador. Só a apresentação passa sem."""
    for locale in hr.LOCALES:
        rec = hr.text_of(rule_id, locale)
        if hr.rule(rule_id)["class"] != hr.GUIDANCE:
            assert rec["example_conflict"].strip(), f"{locale}/{rule_id} sem example_conflict"


def test_lingua_desconhecida_devolve_vazio():
    assert hr.texts("xx-XX") == {}
    assert hr.text_of("grounded_only", "xx-XX") == {}


def test_describe_funde_registo_e_texto():
    d = hr.describe("pt-PT")
    assert set(d) == set(hr.rule_ids())
    g = d["grounded_only"]
    assert g["id"] == "grounded_only"
    assert g["severity"] == "no_effect"
    assert isinstance(g["lever_paths"], list)
    assert g["title"] and g["boundary"]


def test_a_clausula_de_override_esta_declarada():
    assert hr.OVERRIDE_CLAUSE_ANCHOR == "the instruction here wins"
