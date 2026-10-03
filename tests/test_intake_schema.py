"""
tests/test_intake_schema.py — `intake.definitions`, a definição de campo única
e a gramática das condições (v0.1.79, 2 Out 2026; épico Intake, bloco B1).

O que protege:
  * a gramática só aceita JSON estruturado da allowlist — nada que se pareça
    com código; tectos de profundidade, nós, listas e texto; números finitos;
  * toda a referência (pergunta, opção, pontuação, red flag, resultado, secção)
    é confirmada ao gravar — uma regra sobre algo que não existe dava sempre
    falso em silêncio;
  * uma pontuação não depende de outra; a completude e as red flags não
    dependem do resultado;
  * `use_case` fecha a porta ao alto risco (solvabilidade, recrutamento);
  * blocos novos fecham chaves inventadas (`extra="forbid"`);
  * o bloco é inerte por omissão e interno (sem consumidor ainda);
  * round-trip byte-fiel.

A definição de teste é SINTÉTICA e genérica: nenhum cliente real vive neste
repo (as definições de clientes são configuração deles, no perfil).
"""

from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from genesis_profile_schema import exposure as exp
from genesis_profile_schema.client_profile_schema import ClientProfileSchema
from genesis_profile_schema.field_definition import FORM_FIELD_TYPES, FieldDefinition
from genesis_profile_schema.intake_schema import (
    INTAKE_USE_CASES,
    IntakeDefinition,
    ProfileIntake,
)
from genesis_profile_schema.rules_grammar import (
    MAX_DEPTH,
    MAX_NODES,
    validate_predicate,
    validate_value,
)


def _t(pt: str, en: str | None = None) -> dict:
    return {"pt": pt, "en": en or pt}


def _yesno(key: str, section: str, **extra) -> dict:
    return {"key": key, "section": section, "label": _t(key), "type": "select",
            "options": [{"value": "yes", "label": _t("Sim", "Yes")},
                        {"value": "no", "label": _t("Não", "No")}], **extra}


def _definicao() -> dict:
    """Definição sintética com todos os tipos de regra."""
    return {
        "title": _t("Avaliação de exemplo"),
        "use_case": "appropriateness",
        "languages": ["pt", "en"],
        "sections": [
            {"key": "perfil", "title": _t("Perfil")},
            {"key": "experiencia", "title": _t("Experiência")},
            {"key": "conhecimento", "title": _t("Conhecimento"), "assist": False},
        ],
        "questions": [
            {"key": "grau", "section": "perfil", "label": _t("Grau"), "type": "select",
             "options": [{"value": "basico", "label": _t("Básico")},
                         {"value": "superior", "label": _t("Superior")}]},
            {"key": "areas", "section": "perfil", "label": _t("Áreas"), "type": "multiselect",
             "options": [{"value": "economia", "label": _t("Economia")},
                         {"value": "direito", "label": _t("Direito")},
                         {"value": "outra", "label": _t("Outra")}],
             "show_if": {"q": "grau", "eq": "superior"}},
            _yesno("acoes", "experiencia"),
            {"key": "acoes.operacoes", "section": "experiencia", "label": _t("N.º"),
             "type": "number", "integer": True, "min": 0, "allow_unknown": True,
             "show_if": {"q": "acoes", "eq": "yes"}},
            {"key": "acoes.valor", "section": "experiencia", "label": _t("Valor médio"),
             "type": "money", "currencies": ["EUR", "USD"], "allow_unknown": True,
             "show_if": {"q": "acoes", "eq": "yes"}},
            {"key": "acoes.ano", "section": "experiencia", "label": _t("Ano"),
             "type": "year", "allow_unknown": True, "show_if": {"q": "acoes", "eq": "yes"}},
            _yesno("fundos", "experiencia"),
            {"key": "k1", "section": "conhecimento", "label": _t("P1"), "type": "select",
             "assist": False,
             "options": [{"value": "yes", "label": _t("Sim")}, {"value": "no", "label": _t("Não")},
                         {"value": "dont_know", "label": _t("Não sei")}]},
            {"key": "k2", "section": "conhecimento", "label": _t("P2"), "type": "select",
             "assist": False,
             "options": [{"value": "yes", "label": _t("Sim")}, {"value": "no", "label": _t("Não")},
                         {"value": "dont_know", "label": _t("Não sei")}]},
        ],
        "glossary": [
            {"key": "acao", "term": _t("Ação"), "text": _t("Parte do capital de uma empresa."),
             "sections": ["experiencia"]},
        ],
        "methodology": {
            "version": "1.0",
            "effective_from": "2026-10-01",
            "approval": {"by": "Responsável de conformidade", "at": "2026-09-25"},
            "outcomes": [
                {"key": "ok", "label": _t("Adequado"), "kind": "positive"},
                {"key": "nok", "label": _t("Não adequado"), "kind": "negative"},
                {"key": "info", "label": _t("Informação insuficiente"), "kind": "insufficient"},
                {"key": "rev", "label": _t("Revisão manual"), "kind": "review"},
            ],
            "scores": [
                {"key": "conh", "label": _t("Conhecimento"),
                 "terms": [{"kind": "count_matches",
                            "items": [{"q": "k1", "eq": "no"}, {"q": "k2", "eq": "yes"}]}],
                 "bands": [{"min": 0, "label": _t("Insuficiente")},
                           {"min": 2, "label": _t("Suficiente")}]},
                {"key": "exp", "label": _t("Experiência"),
                 "terms": [
                     {"kind": "category_max", "categories": [
                         {"key": "acoes", "when": {"q": "acoes", "eq": "yes"}, "base": 2,
                          "bonuses": [
                              {"when": {"q": "acoes.operacoes", "gt": 5}, "points": 1},
                              {"when": {"cmp": {"left": {"money": "acoes.valor"}, "op": "gte",
                                                "right": {"const": 50000}}}, "points": 1},
                              {"when": {"cmp": {"left": {"q": "acoes.ano"}, "op": "gte",
                                                "right": {"ref_year_offset": -3}}}, "points": 1},
                          ]},
                         {"key": "fundos", "when": {"q": "fundos", "eq": "yes"}, "base": 3},
                     ]},
                     {"kind": "bonus", "when": {"count": [{"q": "acoes", "eq": "yes"},
                                                          {"q": "fundos", "eq": "yes"}], "gte": 2},
                      "points": 1},
                 ]},
                {"key": "form", "label": _t("Formação"),
                 "terms": [{"kind": "points", "items": [
                     {"q": "grau", "values": {"superior": 1}},
                     {"q": "areas", "values": {"economia": 2, "direito": 1}, "agg": "max",
                      "when": {"q": "grau", "eq": "superior"}},
                 ]}]},
            ],
            "required": [
                {"q": "grau"},
                {"q": "areas", "when": {"q": "grau", "eq": "superior"}},
                {"q": "acoes"}, {"q": "fundos"}, {"q": "k1"}, {"q": "k2"},
            ],
            "red_flags": [
                {"key": "erro_essencial", "label": _t("Falha em risco essencial"),
                 "when": {"q": "k1", "in": ["yes", "dont_know"]}},
                {"key": "sem_base", "label": _t("Sem experiência nem formação"),
                 "when": {"all": [{"cmp": {"left": {"score": "exp"}, "op": "eq", "right": {"const": 0}}},
                                  {"cmp": {"left": {"score": "form"}, "op": "lt", "right": {"const": 2}}}]}},
            ],
            "decision": [
                {"key": "r1", "when": {"incomplete": True}, "outcome": "info"},
                {"key": "r2", "when": {"red_flag": True}, "outcome": "nok"},
                {"key": "r3", "when": {"cmp": {"left": {"score": "conh"}, "op": "lt",
                                               "right": {"const": 2}}}, "outcome": "nok"},
                {"key": "r4", "when": {"cmp": {"left": {"score": "exp"}, "op": "gte",
                                               "right": {"const": 3}}}, "outcome": "ok"},
            ],
            "default_outcome": "rev",
            "escalations": [
                {"key": "contradicao", "label": _t("Respostas contraditórias"),
                 "when": {"all": [{"q": "fundos", "eq": "yes"}, {"q": "acoes", "eq": "no"}]},
                 "replace_outcomes": ["ok"], "set_outcome": "rev"},
            ],
            "reference_cases": [
                {"key": "c01", "label": "Perfil forte",
                 "reference_date": "2026-10-02",
                 "fx_rates": {"USD": 1.10},
                 "answers": {"grau": "superior", "areas": ["economia", "direito"],
                             "acoes": "yes", "acoes.operacoes": 10,
                             "acoes.valor": {"amount": 60000, "currency": "USD"},
                             "acoes.ano": 2025, "fundos": "no", "k1": "no", "k2": "yes"},
                 "expected": {"outcome": "ok", "mandatory_review": False,
                              "scores": {"conh": 2, "exp": 5, "form": 3}}},
            ],
        },
    }


def _ok(d: dict) -> IntakeDefinition:
    return IntakeDefinition.model_validate(d)


def _falha(d: dict, contem: str) -> None:
    with pytest.raises(ValidationError) as e:
        IntakeDefinition.model_validate(d)
    assert contem in str(e.value), str(e.value)


# ── Bloco no perfil ──────────────────────────────────────────────────────────

def test_inerte_por_omissao():
    p = ClientProfileSchema.model_validate({"client_id": "x"})
    assert p.intake.definitions == {}
    assert p.to_blob_dict()["intake"] == {"definitions": {}}


def test_interno_por_inteiro_ate_haver_consumidor():
    assert exp.exposure_of("intake.definitions") == exp.INTERNAL
    assert exp.exposure_of("intake.definitions.qualquer.methodology.scores") == exp.INTERNAL
    assert exp.exposure_of("intake.definitions.qualquer.glossary") == exp.INTERNAL


def test_definicao_valida_e_round_trip_fiel():
    d = _definicao()
    perfil = ClientProfileSchema.model_validate({"client_id": "x", "intake": {"definitions": {"exemplo": d}}})
    blob = perfil.to_blob_dict()
    de_novo = ClientProfileSchema.model_validate(blob)
    assert de_novo.to_blob_dict() == blob


def test_chave_inventada_e_recusada_em_todo_o_lado():
    for caminho in ([], ["methodology"], ["questions", 0], ["methodology", "scores", 0]):
        d = _definicao()
        alvo = d
        for parte in caminho:
            alvo = alvo[parte]
        alvo["inventada"] = 1
        with pytest.raises(ValidationError):
            _ok(d)
    with pytest.raises(ValidationError):
        ProfileIntake.model_validate({"definitions": {}, "outra": 1})


def test_ids_de_definicao_tem_forma_de_chave():
    with pytest.raises(ValidationError):
        ProfileIntake.model_validate({"definitions": {"tem espaços": _definicao()}})


# ── use_case: a porta do alto risco ──────────────────────────────────────────

@pytest.mark.parametrize("caso", ["credit_scoring", "hiring", "", "qualquer"])
def test_use_case_fora_da_allowlist_e_recusado(caso):
    d = _definicao()
    d["use_case"] = caso
    _falha(d, "use_case")


def test_allowlist_nao_tem_alto_risco():
    assert "credit_scoring" not in INTAKE_USE_CASES
    assert "hiring" not in INTAKE_USE_CASES


# ── Referências ──────────────────────────────────────────────────────────────

def test_show_if_sobre_pergunta_inexistente():
    d = _definicao()
    d["questions"][1]["show_if"] = {"q": "nao_existe", "eq": "x"}
    _falha(d, "pergunta inexistente")


def test_show_if_sobre_a_propria_pergunta():
    d = _definicao()
    d["questions"][1]["show_if"] = {"q": "areas", "answered": True}
    _falha(d, "própria pergunta")


def test_secao_inexistente():
    d = _definicao()
    d["questions"][0]["section"] = "fantasma"
    _falha(d, "secção inexistente")


def test_perguntas_repetidas():
    d = _definicao()
    d["questions"].append(copy.deepcopy(d["questions"][0]))
    _falha(d, "perguntas repetidos")


def test_opcao_inexistente_numa_pontuacao():
    d = _definicao()
    d["methodology"]["scores"][2]["terms"][0]["items"][1]["values"]["gestao"] = 1
    _falha(d, "não tem as opções")


def test_resposta_certa_que_nao_e_opcao():
    d = _definicao()
    d["methodology"]["scores"][0]["terms"][0]["items"][0]["eq"] = "talvez"
    _falha(d, "não aceita eq 'talvez'")


def test_money_sobre_pergunta_que_nao_e_montante():
    d = _definicao()
    bonus = d["methodology"]["scores"][1]["terms"][0]["categories"][0]["bonuses"][1]
    bonus["when"]["cmp"]["left"] = {"money": "acoes.operacoes"}
    _falha(d, "não é montante")


def test_pontuacao_nao_pode_referir_pontuacao():
    d = _definicao()
    d["methodology"]["scores"][1]["terms"][1]["when"] = {
        "cmp": {"left": {"score": "conh"}, "op": "gte", "right": {"const": 1}}}
    _falha(d, "outra pontuação")


def test_completude_nao_pode_depender_do_resultado():
    d = _definicao()
    d["methodology"]["required"][1]["when"] = {"red_flag": True}
    _falha(d, "não é permitido aqui")


def test_red_flag_nao_depende_de_red_flags():
    d = _definicao()
    d["methodology"]["red_flags"][0]["when"] = {"red_flag": "sem_base"}
    _falha(d, "não é permitido aqui")


def test_decisao_com_resultado_inexistente():
    d = _definicao()
    d["methodology"]["decision"][0]["outcome"] = "talvez"
    _falha(d, "resultado inexistente")


def test_decisao_com_pontuacao_ou_red_flag_inexistente():
    d = _definicao()
    d["methodology"]["decision"][2]["when"]["cmp"]["left"] = {"score": "fantasma"}
    _falha(d, "pontuações inexistentes")
    d = _definicao()
    d["methodology"]["decision"][1]["when"] = {"red_flag": "fantasma"}
    _falha(d, "red flags inexistentes")


def test_escalamento_exige_o_par_e_resultados_existentes():
    d = _definicao()
    d["methodology"]["escalations"][0]["set_outcome"] = None
    _falha(d, "andam juntos")
    d = _definicao()
    d["methodology"]["escalations"][0]["set_outcome"] = "fantasma"
    _falha(d, "resultados inexistentes")


def test_caso_com_resposta_invalida_ou_pergunta_inexistente():
    d = _definicao()
    d["methodology"]["reference_cases"][0]["answers"]["grau"] = "doutoramento"
    _falha(d, "grau: opção inválida")
    d = _definicao()
    d["methodology"]["reference_cases"][0]["answers"]["fantasma"] = "x"
    _falha(d, "perguntas inexistentes")
    d = _definicao()
    d["methodology"]["reference_cases"][0]["expected"]["outcome"] = "fantasma"
    _falha(d, "resultado esperado inexistente")


@pytest.mark.parametrize("valor", [
    {"amount": -1, "currency": "EUR"},
    {"amount": 10, "currency": "euro"},
    {"amount": float("inf"), "currency": "EUR"},
    {"amount": 10, "currency": "EUR", "extra": 1},
    {"x": {"y": 1}},
    "a" * 20001,
])
def test_respostas_mal_formadas_sao_recusadas(valor):
    d = _definicao()
    d["methodology"]["reference_cases"][0]["answers"]["acoes.valor"] = valor
    with pytest.raises(ValidationError):
        _ok(d)


# ── Gramática: só JSON estruturado, com tectos ───────────────────────────────

@pytest.mark.parametrize("cond", [
    {"eval": "__import__('os')"},
    {"q": "x", "eq": "y", "or": 1},
    {"q": "x", "matches": ".*"},
    {"q": "__class__", "eq": 1} | {"extra": 1},
    {"cmp": {"left": {"q": "x"}, "op": "in", "right": {"const": 1}}},
    {"cmp": {"left": {"attr": "x"}, "op": "eq", "right": {"const": 1}}},
    {"cmp": {"left": {"const": float("inf")}, "op": "eq", "right": {"const": 1}}},
    {"cmp": {"left": {"const": float("nan")}, "op": "eq", "right": {"const": 1}}},
    {"cmp": {"left": {"const": True}, "op": "eq", "right": {"const": 1}}},
    {"q": "x", "gt": "5"},
    {"q": "tem espaços", "eq": 1},
    {"all": []},
    {"not": {}},
    {"count": [{"q": "x", "eq": 1}]},
    {"incomplete": False},
    {},
    [],
    "x == 1",
])
def test_formas_fora_da_gramatica_sao_recusadas(cond):
    with pytest.raises(ValueError):
        validate_predicate(cond)


def test_profundidade_maxima():
    cond = {"q": "x", "eq": 1}
    for _ in range(MAX_DEPTH + 2):
        cond = {"not": cond}
    with pytest.raises(ValueError, match="aninhada"):
        validate_predicate(cond)


def test_numero_maximo_de_nos():
    cond = {"any": [{"all": [{"q": "x", "eq": i} for i in range(100)]} for _ in range(4)]}
    with pytest.raises(ValueError, match="grande demais"):
        validate_predicate(cond)
    assert MAX_NODES < 4 * 101


def test_texto_e_listas_com_tecto():
    with pytest.raises(ValueError):
        validate_predicate({"q": "x", "eq": "a" * 201})
    with pytest.raises(ValueError):
        validate_predicate({"q": "x", "in": list(range(101))})
    with pytest.raises(ValueError):
        validate_value({"ref_year_offset": 10_000})


def test_referencias_sao_devolvidas():
    refs = validate_predicate({"all": [
        {"q": "a", "eq": 1},
        {"cmp": {"left": {"money": "b"}, "op": "gte", "right": {"score": "s"}}},
        {"red_flag": "f"},
        {"cmp": {"left": {"q": "c"}, "op": "gte", "right": {"ref_year_offset": -3}}},
    ]})
    assert refs.questions == {"a", "b", "c"}
    assert refs.money_questions == {"b"}
    assert refs.scores == {"s"}
    assert refs.red_flags == {"f"}
    assert refs.uses_reference_year


# ── Definição de campo única ─────────────────────────────────────────────────

def test_os_seis_tipos_do_form_continuam_validos():
    for tipo in FORM_FIELD_TYPES:
        extra = {"options": [{"value": "a", "label": _t("A")}]} if tipo == "select" else {}
        FieldDefinition.model_validate({"key": "c", "label": _t("C"), "type": tipo, **extra})


@pytest.mark.parametrize("campo", [
    {"type": "select"},                                               # sem opções
    {"type": "text", "options": [{"value": "a", "label": _t("A")}]},  # opções a mais
    {"type": "table"},                                                # sem colunas
    {"type": "text", "currencies": ["EUR"]},
    {"type": "text", "allow_unknown": True},
    {"type": "number", "min": 5, "max": 1},
    {"type": "number", "min": float("inf")},
    {"type": "select", "options": [{"value": "a", "label": _t("A")},
                                   {"value": "a", "label": _t("B")}]},
])
def test_campos_incoerentes_sao_recusados(campo):
    with pytest.raises(ValidationError):
        FieldDefinition.model_validate({"key": "c", "label": _t("C"), **campo})


def test_textos_com_tecto_e_linguas_validas():
    with pytest.raises(ValidationError):
        FieldDefinition.model_validate({"key": "c", "label": {"pt": "x" * 2001}})
    with pytest.raises(ValidationError):
        FieldDefinition.model_validate({"key": "c", "label": {"<script>": "x"}})
    with pytest.raises(ValidationError):
        FieldDefinition.model_validate({"key": "c", "label": {}})
    with pytest.raises(ValidationError):
        FieldDefinition.model_validate({"key": "c", "label": {"pt": "   "}})


# ── Revisão independente de 2 Out: um teste por achado ───────────────────────

from genesis_profile_schema.field_values import validate_answers  # noqa: E402
from genesis_profile_schema.intake_schema import MAX_DEFINITION_NODES  # noqa: E402


@pytest.mark.parametrize("cond,contem", [
    ({"q": "k1", "in": ["Yes", "dont-know"]}, "não aceita in"),          # opção mal escrita
    ({"q": "grau", "eq": "Superior"}, "não aceita eq"),                  # maiúscula
    ({"q": "grau", "contains": "superior"}, "não aceita contains"),      # contains numa escolha única
    ({"q": "areas", "eq": "economia"}, "use contains"),                  # eq numa escolha múltipla
    ({"q": "acoes.operacoes", "eq": "10"}, "não aceita eq"),             # texto num número
    ({"q": "acoes.operacoes", "eq": True}, "não aceita eq"),             # booleano num número
    ({"q": "acoes.valor", "gt": 5}, "use money"),                        # literal sobre montante
])
def test_literais_confirmados_contra_tipo_e_opcoes(cond, contem):
    d = _definicao()
    d["methodology"]["red_flags"][0]["when"] = cond
    _falha(d, contem)


def test_null_nao_e_literal_e_count_inalcancavel_e_recusado():
    with pytest.raises(ValueError, match="answered"):
        validate_predicate({"q": "x", "eq": None})
    with pytest.raises(ValueError, match="nunca se cumpre"):
        validate_predicate({"count": [{"q": "x", "eq": 1}], "gte": 5})
    with pytest.raises(ValueError, match="nunca se cumpre"):
        validate_predicate({"count": [{"q": "x", "eq": 1}, {"q": "y", "eq": 1}], "gt": 2})


def test_count_matches_numerico_sobre_escolha_e_recusado():
    d = _definicao()
    d["methodology"]["scores"][0]["terms"][0]["items"][0]["eq"] = 1
    _falha(d, "não aceita eq 1")


def test_map_so_sobre_escolhas_e_com_opcoes_existentes():
    d = _definicao()
    d["methodology"]["decision"][2]["when"]["cmp"]["left"] = {"map": {"q": "grau", "values": {"Superior": 1}}}
    _falha(d, "não tem as opções")
    d = _definicao()
    d["methodology"]["decision"][2]["when"]["cmp"]["left"] = {"map": {"q": "acoes.ano", "values": {"1": 1}}}
    _falha(d, "'map' só sobre escolhas")


def test_comparacao_numerica_so_sobre_numeros_e_anos():
    d = _definicao()
    d["methodology"]["decision"][2]["when"]["cmp"]["left"] = {"q": "grau"}
    _falha(d, "não é número nem ano")


def test_points_so_sobre_escolhas_ou_caixas_e_max_so_em_multipla():
    d = _definicao()
    d["methodology"]["scores"][2]["terms"][0]["items"][0] = {"q": "acoes.ano", "values": {"2025": 1}}
    _falha(d, "'points' só sobre escolhas")
    d = _definicao()
    d["methodology"]["scores"][2]["terms"][0]["items"][0]["agg"] = "max"
    _falha(d, "agg 'max' só em escolha múltipla")


def test_show_if_em_ciclo_e_recusado_e_cadeia_longa_e_aceite():
    d = _definicao()
    d["questions"][0]["show_if"] = {"q": "areas", "answered": True}   # grau ↔ areas
    _falha(d, "ciclo")
    d = _definicao()
    for i in range(60):
        q = {"key": f"c{i}", "section": "perfil", "label": _t(f"C{i}"), "type": "text"}
        if i:
            q["show_if"] = {"q": f"c{i - 1}", "answered": True}
        d["questions"].append(q)
    defin = _ok(d)
    ordem = defin.visibility_order()
    assert ordem.index("c0") < ordem.index("c59")


def test_orcamento_de_nos_por_definicao():
    d = _definicao()
    grande = {"any": [{"all": [{"q": "k1", "eq": "yes"}, {"q": "k2", "eq": "no"}]} for _ in range(99)]}
    d["methodology"]["red_flags"] = [
        {"key": f"f{i}", "label": _t("F"), "when": grande} for i in range(MAX_DEFINITION_NODES // 290 + 1)]
    _falha(d, "definição grande demais")


def test_escalamentos_nao_se_encadeiam():
    d = _definicao()
    d["methodology"]["escalations"].append(
        {"key": "seguinte", "label": _t("S"), "when": {"q": "fundos", "eq": "yes"},
         "replace_outcomes": ["rev"], "set_outcome": "nok"})
    _falha(d, "encadeados")


@pytest.mark.parametrize("caminho,valor", [
    (("methodology", "scores", 0, "terms", 0, "points_each"), True),
    (("methodology", "scores", 0, "terms", 0, "points_each"), "1"),
    (("methodology", "reference_cases", 0, "fx_rates", "USD"), 0),
    (("methodology", "reference_cases", 0, "fx_rates", "USD"), -1.1),
    (("methodology", "reference_cases", 0, "fx_rates", "USD"), True),
    (("methodology", "reference_cases", 0, "expected", "scores", "exp"), True),
    (("questions", 3, "min"), "0"),
])
def test_numeros_estritos(caminho, valor):
    d = _definicao()
    alvo = d
    for parte in caminho[:-1]:
        alvo = alvo[parte]
    alvo[caminho[-1]] = valor
    with pytest.raises(ValidationError):
        _ok(d)


@pytest.mark.parametrize("pergunta,valor", [
    ("acoes.operacoes", "dez"),
    ("acoes.operacoes", -5),                          # min 0
    ("acoes.operacoes", 2.5),                         # integer
    ("acoes.ano", {"amount": 1, "currency": "EUR"}),
    ("acoes.valor", 5),
    ("areas", ["economia", "economia"]),              # repetidos
    ("areas", "economia"),                            # texto numa múltipla
    ("grau", ["superior"]),                           # lista numa escolha única
    ("k1", True),                                     # booleano numa escolha
])
def test_respostas_dos_casos_passam_pelo_validador_por_tipo(pergunta, valor):
    d = _definicao()
    d["methodology"]["reference_cases"][0]["answers"][pergunta] = valor
    with pytest.raises(ValidationError):
        _ok(d)


def test_validador_de_respostas_conta_chaves_desconhecidas_sem_as_ecoar():
    defin = _ok(_definicao())
    chk = validate_answers(defin.questions, {"grau": "basico", "<script>" * 10: 1, "x": None})
    assert chk.ok and chk.clean == {"grau": "basico"} and chk.unknown_keys == 2
    with pytest.raises(ValueError):
        validate_answers(defin.questions, ["grau"])
    chk = validate_answers(defin.questions, {"acoes.operacoes": 10 ** 400, "acoes.ano": float("nan")})
    assert set(chk.errors) == {"acoes.operacoes", "acoes.ano"}
    assert all("10" * 5 not in m for m in chk.errors.values())   # o valor não é ecoado


# ── 2.ª ronda de revisão (2 Out): N1, N4, N6, N7 ─────────────────────────────

@pytest.mark.parametrize("cond", [
    {"count": [{"q": "k1", "eq": "yes"}], "lt": 0},
    {"count": [{"q": "k1", "eq": "yes"}], "lte": 1},
    {"count": [{"q": "k1", "eq": "yes"}], "ne": 5},
    {"count": [{"q": "k1", "eq": "yes"}], "gte": 0},
])
def test_count_sempre_verdadeiro_ou_falso_e_recusado(cond):
    with pytest.raises(ValueError, match="sempre|nunca"):
        validate_predicate(cond)


@pytest.mark.parametrize("cond", [
    {"q": "acoes.operacoes", "eq": 2.5},       # inteiro
    {"q": "acoes.operacoes", "eq": -1},        # min 0
    {"q": "acoes.ano", "eq": 50},              # ano fora 1000–3000
])
def test_literal_numerico_impossivel_e_recusado(cond):
    d = _definicao()
    d["methodology"]["red_flags"][0]["when"] = cond
    _falha(d, "fora do que a pergunta aceita")


def test_datas_iso_canonicas():
    defin = _ok(_definicao())
    from genesis_profile_schema.field_definition import FieldDefinition as FD
    data = FD.model_validate({"key": "d", "label": _t("D"), "type": "date"})
    assert validate_answers([data], {"d": "2000-01-01"}).clean == {"d": "2000-01-01"}
    for mau in ("20000101", "2000-W01-6", "ontem"):
        assert validate_answers([data], {"d": mau}).errors
    assert defin


def test_taxa_abaixo_do_piso_e_recusada():
    d = _definicao()
    d["methodology"]["reference_cases"][0]["fx_rates"]["USD"] = 1e-14
    with pytest.raises(ValidationError):
        _ok(d)


def test_escalamentos_com_destinos_diferentes_para_o_mesmo_resultado():
    d = _definicao()
    d["methodology"]["escalations"].append(
        {"key": "outro", "label": _t("O"), "when": {"q": "fundos", "eq": "yes"},
         "replace_outcomes": ["ok"], "set_outcome": "info"})
    _falha(d, "destinos diferentes")


# ── acesso de quem responde (v0.1.80, B4) ───────────────────────────────────

def test_acesso_por_omissao_sao_as_decisoes():
    a = IntakeDefinition.model_validate(_definicao()).access
    assert (a.link_valid_days, a.session_idle_minutes, a.code_ttl_minutes, a.code_max_attempts,
            a.max_failed_codes, a.code_min_interval_seconds, a.codes_per_day,
            a.channels) == (30, 30, 10, 5, 3, 60, 10, ["email", "sms"])


@pytest.mark.parametrize("campo,valor", [
    ("code_max_attempts", 0), ("code_max_attempts", 11), ("link_valid_days", 91),
    ("max_failed_codes", 0), ("code_min_interval_seconds", 5), ("codes_per_day", 100),
    ("channels", []), ("channels", ["email", "email"]), ("channels", ["whatsapp"]),
    ("session_idle_minutes", "30"), ("desconhecido", 1),
])
def test_acesso_nao_desliga_a_protecao(campo, valor):
    d = _definicao()
    d["access"] = {campo: valor}
    with pytest.raises(ValidationError):
        IntakeDefinition.model_validate(d)


def test_acesso_configuravel_dentro_dos_tetos():
    d = _definicao()
    d["access"] = {"link_valid_days": 14, "channels": ["email"]}
    a = IntakeDefinition.model_validate(d).access
    assert a.link_valid_days == 14 and a.channels == ["email"] and a.code_max_attempts == 5



# ── apresentação (v0.1.81, B5) ──────────────────────────────────────────────

def test_apresentacao_por_omissao_vazia():
    p = IntakeDefinition.model_validate(_definicao()).presentation
    assert p.bilingual is False and p.footer == {}


def test_apresentacao_configuravel():
    d = _definicao()
    d["presentation"] = {"bilingual": True, "footer": {"pt": "Rodapé legal."}}
    p = IntakeDefinition.model_validate(d).presentation
    assert p.bilingual is True and p.footer == {"pt": "Rodapé legal."}


def test_bilingue_precisa_de_duas_linguas():
    d = _definicao()
    d["languages"] = d["languages"][:1]
    d["presentation"] = {"bilingual": True}
    with pytest.raises(ValidationError):
        IntakeDefinition.model_validate(d)


@pytest.mark.parametrize("valor", [
    {"bilingual": "sim"}, {"bilingual": 1}, {"footer": {"pt": "x" * 5000}}, {"footer": {"PT": "x"}},
    {"footer": "texto"}, {"cor": "#000"},
])
def test_apresentacao_recusa_invalidos(valor):
    d = _definicao()
    d["presentation"] = valor
    with pytest.raises(ValidationError):
        IntakeDefinition.model_validate(d)


def test_logo_nos_cabecalhos_escuros_ligado_por_omissao():
    from genesis_profile_schema.client_profile_schema import ProfileFrontendBranding
    assert ProfileFrontendBranding().darkHeaderLogo is True
    assert ProfileFrontendBranding(darkHeaderLogo=False).darkHeaderLogo is False


# ── revisão pela equipa (v0.1.82, B6) ───────────────────────────────────────

def test_revisao_por_omissao():
    r = IntakeDefinition.model_validate(_definicao()).review
    assert r.roles["create"] == ["Intake.Commercial"] and r.roles["second_review"] == ["Intake.Supervisor"]
    assert r.double_validation.min_amount is None and r.double_validation.on_red_flags is True
    assert r.amount_required is False


def test_revisao_configuravel():
    d = _definicao()
    outcome = d["methodology"]["outcomes"][0]["key"]
    d["review"] = {"roles": {"view": ["Analista"], "review": ["Analista"]},
                   "double_validation": {"min_amount": 500000, "currency": "EUR", "outcomes": [outcome]},
                   "amount_required": True}
    r = IntakeDefinition.model_validate(d).review
    assert r.roles == {"view": ["Analista"], "review": ["Analista"]}
    assert r.double_validation.min_amount == 500000 and r.double_validation.outcomes == [outcome]


@pytest.mark.parametrize("valor", [
    {"roles": {"aprovar_especial": ["X"]}},          # capacidade inventada
    {"roles": {"quality": ["X"]}},                    # reservada até existir
    {"roles": {"review": ["X", "X"]}},
    {"roles": {"review": ["papel com espaço"]}},
    {"double_validation": {"min_amount": 0}},
    {"double_validation": {"min_amount": "500000"}},
    {"double_validation": {"currency": "eur"}},
    {"double_validation": {"outcomes": ["nao_existe"]}},
    {"double_validation": {"on_red_flags": 1}},
    {"amount_required": "sim"},
    {"outro": 1},
])
def test_revisao_recusa_invalidos(valor):
    d = _definicao()
    d["review"] = valor
    with pytest.raises(ValidationError):
        IntakeDefinition.model_validate(d)


def test_share_access_por_omissao_auto_e_fechado():
    from genesis_profile_schema.client_profile_schema import ProfileFrontendFeatures
    assert ProfileFrontendFeatures().shareAccess == "auto"
    assert ProfileFrontendFeatures(shareAccess="login").shareAccess == "login"
    with pytest.raises(ValidationError):
        ProfileFrontendFeatures(shareAccess="todos")
