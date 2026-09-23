"""
tests/test_tool_cv_analysis.py — `tools.config.analyse_cv` (v0.1.71, 23 Set
2026; épico Análise de CVs, Fase 4).

O que protege:
  * os pisos e tectos são os que o genai-core já aplica
    (`tools/cv_analysis/jobs/settings.py`) — o schema recusa o que o core
    cortaria em silêncio (retenção 183–365, lote 50–500, paralelismo 1–16);
  * não há interruptor da máscara nem do texto escondido (contrato, D2);
  * o cliente edita o domínio, a retenção e as vagas-tipo; lote, paralelismo e
    deployment são internos (custo e quota);
  * round-trip byte-fiel, como os outros blocos tipados.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from genesis_profile_schema import exposure as exp
from genesis_profile_schema import presentation as pr
from genesis_profile_schema import ui_text as ui
from genesis_profile_schema.client_profile_schema import (
    ClientProfileSchema,
    _DEFAULT_TOOLS_ENABLED,
    _KNOWN_TOOL_CONFIG_MODELS,
)
from genesis_profile_schema.tool_cv_analysis import (
    ProfileToolCvAnalysisConfig,
    ProfileToolCvJobTemplate,
    ProfileToolCvTemplateCriterion,
)

P = "tools.config.analyse_cv"


def test_registado_e_off_por_default():
    assert _KNOWN_TOOL_CONFIG_MODELS["analyse_cv"] is ProfileToolCvAnalysisConfig
    assert "analyse_cv" not in _DEFAULT_TOOLS_ENABLED
    assert "analyse_cv" not in ClientProfileSchema.model_validate({"client_id": "x"}).tools.config


def test_defaults_iguais_aos_do_core():
    c = ProfileToolCvAnalysisConfig()
    assert (c.prompt_preset, c.prompt_custom, c.retention_days, c.max_batch,
            c.parallelism, c.deployment, c.job_templates) == ("", "", 183, 50, 4, "", [])


@pytest.mark.parametrize("campo,ok,maus", [
    ("retention_days", (183, 200, 365), (0, 30, 182, 366, 3650)),
    ("max_batch", (50, 120, 500), (0, 10, 49, 501)),
    ("parallelism", (1, 4, 16), (0, 17)),
])
def test_limites_sao_os_que_o_core_honra(campo, ok, maus):
    for v in ok:
        assert getattr(ProfileToolCvAnalysisConfig(**{campo: v}), campo) == v
    for v in maus:
        with pytest.raises(ValidationError):
            ProfileToolCvAnalysisConfig(**{campo: v})


def test_mascara_e_texto_escondido_nao_sao_opcao():
    campos = set(ProfileToolCvAnalysisConfig.model_fields)
    assert not campos & {"anonymise", "anonymize", "mask", "hidden_text_policy"}


def test_vaga_tipo_valida():
    t = ProfileToolCvJobTemplate.model_validate({
        "id": "analista-financeiro", "title": "Analista financeiro",
        "criteria": [
            {"type": "EDUCATION", "description": "Licenciatura em Economia ou Gestão", "must_have": True,
             "scale": {"dimension": "education", "min_level": "Licenciatura", "subject": "Economia"}},
            {"type": "LEGAL", "description": "Carta de condução de categoria B",
             "needs_protected_attr": "driving_licence"},
            {"type": "SKILL", "description": "Power BI", "must_have": False, "weight": 3},
        ],
    })
    assert [c.type for c in t.criteria] == ["EDUCATION", "LEGAL", "SKILL"]
    assert t.criteria[0].must_have is True
    # Ausente = desejável, como o core lê (`normalize_criteria`).
    assert t.criteria[1].must_have is False


@pytest.mark.parametrize("mau", [
    {"description": ""},                                            # critério vazio
    {"description": "   "},                                         # só espaços
    {"description": "x" * 501},                                     # acima do tecto do motor
    {"description": "Python", "weight": 4},
    {"description": "Python", "type": "SCORE"},
    {"description": "Idade", "needs_protected_attr": "gender"},     # atributo fora da lista
    {"description": "Inglês", "scale": {"dimension": "height"}},
])
def test_criterio_invalido_e_recusado(mau):
    with pytest.raises(ValidationError):
        ProfileToolCvTemplateCriterion.model_validate(mau)


def test_vaga_tipo_tectos_do_motor():
    base = {"id": "a", "title": "A", "criteria": [{"description": "Python"}]}
    with pytest.raises(ValidationError):
        ProfileToolCvJobTemplate.model_validate({**base, "criteria": [{"description": f"c{i}"} for i in range(41)]})
    with pytest.raises(ValidationError):
        ProfileToolCvJobTemplate.model_validate({**base, "requirements": "x" * 30001})
    with pytest.raises(ValidationError):
        ProfileToolCvJobTemplate.model_validate({**base, "id": "Com Espaços"})
    with pytest.raises(ValidationError):
        ProfileToolCvTemplateCriterion.model_validate(
            {"description": "Inglês", "scale": {"dimension": "language", "min_level": "B" * 81}})


def test_vaga_tipo_sem_criterios_ou_com_id_repetido_e_recusada():
    """O core deitava-as fora em silêncio; o schema recusa-as à gravação."""
    with pytest.raises(ValidationError):
        ProfileToolCvJobTemplate.model_validate({"id": "a", "title": "A"})
    with pytest.raises(ValidationError):
        ProfileToolCvJobTemplate.model_validate({"id": "a", "title": "A", "criteria": []})
    with pytest.raises(ValidationError):
        ProfileToolCvJobTemplate.model_validate({"id": "a", "title": "   ", "criteria": [{"description": "X"}]})
    t = {"id": "a", "title": "A", "criteria": [{"description": "Python"}]}
    with pytest.raises(ValidationError):
        ProfileToolCvAnalysisConfig.model_validate({"job_templates": [t, {**t, "title": "B"}]})


@pytest.mark.parametrize("onde", ["vaga", "criterio", "escala"])
def test_vaga_tipo_nao_aceita_chaves_inventadas(onde):
    t = {"id": "a", "title": "A", "criteria": [{"description": "Inglês",
                                                "scale": {"dimension": "language", "min_level": "B2"}}]}
    alvo = {"vaga": t, "criterio": t["criteria"][0], "escala": t["criteria"][0]["scale"]}[onde]
    alvo["evil"] = "x" * 1000
    with pytest.raises(ValidationError):
        ProfileToolCvJobTemplate.model_validate(t)


def test_round_trip_byte_fiel_e_validado_no_perfil_inteiro():
    raw = {"client_id": "x", "tools": {"enabled": ["analyse_cv"], "config": {"analyse_cv": {
        "retention_days": 365, "extra_livre": 1,
        "job_templates": [{"id": "a", "title": "A", "criteria": [{"description": "Python"}]}]}}}}
    prof = ClientProfileSchema.model_validate(raw)
    assert prof.tools.config["analyse_cv"] == raw["tools"]["config"]["analyse_cv"]
    with pytest.raises(ValidationError):
        ClientProfileSchema.model_validate(
            {"client_id": "x", "tools": {"config": {"analyse_cv": {"retention_days": 3650}}}})


def test_exposicao_cliente_edita_dominio_retencao_e_vagas():
    for campo in ("prompt_preset", "prompt_custom", "retention_days", "job_templates",
                  "job_templates.criteria.description", "job_templates.criteria.scale.subject"):
        assert exp.exposure_of(f"{P}.{campo}") == exp.CLIENT_WRITE, campo
    for campo in ("max_batch", "parallelism", "deployment"):
        assert exp.exposure_of(f"{P}.{campo}") == exp.INTERNAL, campo


def test_cada_folha_editavel_tem_entrada_exacta():
    """Caminhos exactos, nunca prefixos (os modelos são extra="allow"): toda a
    folha do bloco que o cliente edita está na tabela, e nenhuma entrada da
    tabela aponta para um campo que o modelo não tem."""
    formas = {p for p in exp.tool_config_shapes() if p.startswith(P + ".")}
    entradas = {p for p in exp.EXPOSURE if p.startswith(P + ".")}
    assert entradas, "sem excepções para a triagem"
    antepassados = {".".join(p.split(".")[:i]) for p in formas for i in range(1, len(p.split(".")))}
    assert all(e in formas or e in antepassados for e in entradas), entradas - formas - antepassados
    editaveis = {p for p in formas if p.startswith(f"{P}.job_templates")}
    assert editaveis <= entradas, editaveis - entradas


def test_controlos():
    assert pr.control_for(f"{P}.prompt_preset") == pr.COMBOBOX
    assert pr.control_for(f"{P}.prompt_custom") == pr.MULTILINE
    assert pr.control_for(f"{P}.job_templates.requirements") == pr.MULTILINE
    assert pr.control_for(f"{P}.job_templates.criteria.type") == pr.SELECT
    assert pr.control_for(f"{P}.job_templates.criteria.scale.dimension") == pr.SELECT
    assert pr.control_for(f"{P}.retention_days") == pr.NUMBER


@pytest.mark.parametrize("locale", ui.LOCALES)
def test_texto_nas_duas_linguas_e_opcoes_alinhadas(locale):
    formas = exp.tool_config_shapes()
    for path, forma in formas.items():
        if not path.startswith(P + "."):
            continue
        assert ui.label_of(path, locale), f"{path} sem label em {locale}"
        membros = [m for m in (forma.get("enum") or ()) if m is not None]
        if membros:
            nomeados = ui.options_of(path, locale)
            assert set(membros) == set(nomeados), (path, membros, nomeados)
    assert set(ui.options_of(f"{P}.prompt_preset", locale)) == {"", "general", "technology", "regulated_health"}
