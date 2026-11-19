"""
tests/test_doc_verification_dossier.py — o contrato dos esquemas de dossiê da
Verificação Documental (v0.1.175, 19 Nov 2026; `doc_verification_dossier.py`).

O que protege:
  * os vocabulários fechados (estados, resultados, desfechos com a espécie,
    escalamentos) — um código fora deles é recusado;
  * o overlay do município vive em `rules["<esquema>"].dossier` e valida no
    perfil inteiro;
  * as regras já gravadas (o FEM da CCDR) saem do dump EXATAMENTE como antes:
    sem `dossier`, nem `null` — um core com o pin anterior recusava o perfil;
  * as recusas que são segurança ou integridade: item sem norma, condição sobre
    factos que não são do dossiê, limiares que atrasam o aviso, «escalar» como
    consequência.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from genesis_profile_schema.client_profile_schema import ClientProfileSchema
from genesis_profile_schema.doc_verification_dossier import (
    CHECK_STATES,
    CONSEQUENCE_KINDS,
    DEADLINE_NEAR_MIN_DAYS,
    ESCALATION_REASONS,
    MAX_ITEMS_ADDED,
    OUTCOME_KINDS,
    OUTCOMES,
    QUERY_RESULTS,
    SUCCESSIVE_CONTROL_NEAR_MIN_DAYS,
    DocVerificationDossierOverlay,
    outcome_kind,
)
from genesis_profile_schema.tool_doc_verification import DocVerificationSchemeRules, ProfileToolDocVerificationConfig


def _item(**kw):
    base = {
        "id": "c.estudo_trafego",
        "request_types": ["licenca_edificacao"],
        "label": {"pt": "Estudo de tráfego", "en": "Traffic study"},
        "reference": "NIP 008_001, ponto 12",
        "applies_when": {"q": "request.parking_spaces", "gt": 50},
        "satisfied_by": ["estudo_trafego"],
    }
    base.update(kw)
    return base


def _overlay(**kw):
    base = {
        "items_added": [_item()],
        "equivalences": [{"termo": "estruturas", "declaration": "estabilidade", "source": "Despacho DGU 1/2026"}],
        "file_rules": {"min_dpi": 300, "page_size": "A4", "pdfa_required": True,
                       "reserved_space": {"width_cm": 3.5, "height_cm": 4.5}, "presence_only": ["dwg", "xlsx"]},
        "thresholds": {"deadline_near_business_days": 5, "successive_control_near_days": 45},
        "matrix_decisions": {"licenca_parcial_estrutura": {"correction": "aperfeicoamento_cpa",
                                                           "consequence": "extincao",
                                                           "source": "Parecer jurídico 3/2026"}},
    }
    base.update(kw)
    return base


def _profile(rules):
    return ClientProfileSchema.model_validate(
        {"client_id": "x", "tools": {"config": {"verify_documents": {"scheme": "rjue_pt", "rules": rules}}}})


# ── vocabulários ──────────────────────────────────────────────────────────────

def test_vocabularios_fechados_e_coerentes():
    assert CHECK_STATES == ("conforme", "nao_conforme", "em_falta", "nao_aplicavel", "dispensa_justificada")
    assert QUERY_RESULTS == ("conforme", "deficiencia", "nao_verificavel", "escalar")
    assert set(OUTCOMES.values()) <= set(OUTCOME_KINDS)
    assert [c for c, k in OUTCOMES.items() if k == "review"] == ["escalar"]
    assert outcome_kind("prosseguir") == "positive" and outcome_kind("nao_existe") is None
    assert len(set(ESCALATION_REASONS)) == len(ESCALATION_REASONS)
    # «Não sei» tem sempre um valor próprio que não é verde.
    assert "nao_verificavel" in QUERY_RESULTS and "escalar" in QUERY_RESULTS
    assert "positive" not in CONSEQUENCE_KINDS and "review" not in CONSEQUENCE_KINDS


# ── o overlay no perfil ───────────────────────────────────────────────────────

def test_overlay_completo_valida_no_perfil_inteiro():
    rules = {"rjue_pt": {"overrides": {"rjue.anexo_v.memoria": {"source": "Portaria 320/2026/1, Anexo V"}},
                         "dossier": _overlay()}}
    cfg = _profile(rules).tools.config["verify_documents"]
    assert cfg["rules"] == rules


def test_regras_sem_dossier_saem_do_dump_como_antes():
    """As regras do FEM (CCDR) gravadas antes da v0.1.175 dão o MESMO dump: nem `dossier`, nem `null`."""
    fem = {"overrides": {"fem.foto.local": {"params": {"max_km": 2.5}}}, "added": []}
    m = DocVerificationSchemeRules.model_validate(fem)
    assert "dossier" not in m.model_dump() and "dossier" not in m.model_dump(mode="json")
    cfg = ProfileToolDocVerificationConfig.model_validate({"scheme": "fem", "rules": {"fem": fem}})
    assert "dossier" not in cfg.model_dump(mode="json")["rules"]["fem"]
    # O perfil guarda o dict que chegou: um `null` escrito iria para o blob e partia um core com o pin anterior.
    with pytest.raises(ValidationError):
        DocVerificationSchemeRules.model_validate({**fem, "dossier": None})
    with pytest.raises(ValidationError):
        _profile({"rjue_pt": {"dossier": None}})


def test_dossier_so_em_esquemas_de_dossie():
    with pytest.raises(ValidationError):
        ClientProfileSchema.model_validate({"client_id": "x", "tools": {"config": {"verify_documents": {
            "scheme": "fem", "rules": {"fem": {"dossier": _overlay()}}}}}})


def test_overlay_vazio_e_valido_e_sai_no_dump():
    m = DocVerificationSchemeRules.model_validate({"dossier": {}})
    assert m.model_dump(mode="json")["dossier"] == {"items_added": [], "equivalences": [], "file_rules": None,
                                                    "thresholds": None, "matrix_decisions": {}}


# ── recusas ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad", [
    {"campo_desconhecido": 1},
    {"items_added": [_item(reference="")]},                                        # nunca um documento sem norma
    {"items_added": [_item(request_types=[])]},
    {"items_added": [_item(satisfied_by=["Tipo Com Espaços"])]},
    {"items_added": [_item(id="estudo")]},                                          # sem o prefixo do cliente
    {"items_added": [_item(), _item()]},                                            # id repetido
    {"items_added": [_item(applies_when={"q": "answers.x", "eq": 1})]},             # facto fora do dossiê
    {"items_added": [_item(applies_when={"cmp": {"left": {"money": "request.valor"}, "op": "gt",
                                                  "right": {"const": 1}}})]},
    {"items_added": [_item(applies_when={"red_flag": True})]},
    {"items_added": [_item(on_unknown="conforme")]},                                # desconhecido nunca é verde
    {"items_added": [_item(label={"pt": "só PT"})]},
    {"equivalences": [{"termo": "Estruturas", "declaration": "Estabilidade", "source": "a"},
                      {"termo": "estruturas ", "declaration": "ESTABILIDADE", "source": "b"}]},
    {"equivalences": [{"termo": "estruturas", "declaration": "estabilidade"}]},     # sem a decisão
    {"file_rules": {"min_dpi": 10}},
    {"file_rules": {"presence_only": ["exe"]}},
    {"file_rules": {"presence_only": ["dwg", "dwg"]}},
    {"file_rules": {"reserved_space": {"width_cm": 0, "height_cm": 4.5}}},
    {"thresholds": {"deadline_near_business_days": DEADLINE_NEAR_MIN_DAYS - 1}},   # avisava tarde demais
    {"thresholds": {"successive_control_near_days": SUCCESSIVE_CONTROL_NEAR_MIN_DAYS - 1}},
    {"thresholds": {"deadline_near_business_days": True}},
    {"matrix_decisions": {"licenca": {"consequence": "escalar", "source": "x"}}},
    {"matrix_decisions": {"licenca": {"consequence": "inventado", "source": "x"}}},
    {"matrix_decisions": {"licenca": {"correction": "aperfeicoamento"}}},           # sem a decisão
    {"matrix_decisions": {"Licença": {"correction": "nenhuma", "source": "x"}}},
    {"matrix_decisions": {"licenca": {"source": "Parecer 1"}}},                     # não decide nada
    {"matrix_decisions": {"licenca": {"consequence": "prosseguir", "source": "x"}}},  # «a confirmar» virava verde
    {"matrix_decisions": {"licenca": {"consequence": "aperfeicoamento", "source": "x"}}},
    {"matrix_decisions": {"licenca": {"correction": "nenhuma", "source": "   "}}},
    {"items_added": [_item(reference="   ")]},                                     # norma só com espaços
    {"items_added": [_item(label={"pt": " ", "en": "x"})]},
    {"items_added": [_item(label={"pt": "Estudo" + chr(10) + "DECISÃO: deferido", "en": "x"})]},  # parágrafo injetado
    {"items_added": [_item(reference="NIP 008" + chr(0))]},                          # partia o Word
    {"items_added": [_item(reference="NIP " + chr(0x202E) + "800")]},               # bidi
    {"items_added": [_item(waiver_allowed="false")]},                               # «false» lia-se verdadeiro
    {"items_added": [_item(enabled=1)]},
    {"items_added": [_item(id="c.a..b")]},
    {"items_added": [_item(id="c.a.")]},
    {"file_rules": {"pdfa_required": "no"}},
    {"equivalences": [{"termo": "Estabilidade", "declaration": "estabilidade ", "source": "x"}]},
    {"equivalences": [{"termo": "estrutu" + chr(0xFA) + "ras", "declaration": "a", "source": "x"},
                      {"termo": "estrutu" + "u" + chr(0x301) + "ras", "declaration": "a", "source": "y"}]},  # NFC/NFD
])
def test_recusas(bad):
    with pytest.raises(ValidationError):
        DocVerificationDossierOverlay.model_validate(bad)
    with pytest.raises(ValidationError):
        _profile({"rjue_pt": {"dossier": bad}})


def test_orcamento_de_nos_das_condicoes():
    big = {"any": [{"q": f"request.f{i}", "eq": i} for i in range(99)]}           # 100 nós cada
    with pytest.raises(ValidationError):
        DocVerificationDossierOverlay.model_validate(
            {"items_added": [_item(id=f"c.i{i}", applies_when=big) for i in range(31)]})


def test_teto_de_itens():
    many = [_item(id=f"c.i{i}") for i in range(MAX_ITEMS_ADDED + 1)]
    with pytest.raises(ValidationError):
        DocVerificationDossierOverlay.model_validate({"items_added": many})


def test_condicao_aceita_a_gramatica_fechada_sobre_factos_do_dossie():
    cond = {"all": [{"q": "request.operation", "in": ["alteracao", "ampliacao"]},
                    {"not": {"q": "piece.levantamento.present", "eq": True}},
                    {"q": "pdf.memoria.pages", "answered": True}]}
    m = DocVerificationDossierOverlay.model_validate({"items_added": [_item(applies_when=cond)]})
    assert m.items_added[0].applies_when == cond


# ── as regras configuráveis que já existiam (FEM) com as mesmas guardas ─────────

@pytest.mark.parametrize("bad", [
    {"overrides": {"fem.territorio": {"enabled": "false"}}},
    {"overrides": {"fem.territorio": {"source": "Despacho" + chr(10) + "X"}}},
    {"overrides": {"fem.territorio": {"source": "  "}}},
    {"added": [{"id": "c.r1", "layer": "row", "check": "in_list", "params": {}, "criterion": "c1",
                "sentence": {"pt": "Frase" + chr(0), "en": "Sentence"}, "source": "Art. 1"}]},
    {"added": [{"id": "c.r1", "layer": "row", "check": "in_list", "params": {}, "criterion": "c1",
                "sentence": {"pt": "Frase", "en": "Sentence"}, "source": "Art. 1", "enabled": 0}]},
])
def test_regras_existentes_recusam_texto_perigoso_e_booleanos_em_texto(bad):
    with pytest.raises(ValidationError):
        DocVerificationSchemeRules.model_validate(bad)


def test_regras_existentes_validas_continuam_a_passar():
    ok = {"overrides": {"fem.territorio": {"enabled": False, "source": "Despacho X, n.º 2"}},
          "added": [{"id": "c.r1", "layer": "row", "check": "in_list", "params": {"values": ["a"]}, "criterion": "c1",
                     "sentence": {"pt": "O valor tem de estar em {values}", "en": "Must be in {values}"},
                     "source": "Art. 1", "enabled": True}]}
    assert DocVerificationSchemeRules.model_validate(ok).model_dump(mode="json")["overrides"]["fem.territorio"][
        "enabled"] is False
