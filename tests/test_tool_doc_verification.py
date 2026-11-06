"""
tests/test_tool_doc_verification.py — `tools.config.verify_documents` (v0.1.100,
8 Out 2026; épico Verificação Documental, Fase 4).

O que protege:
  * os limites são os que o genai-core aplica (`processing_config`: paralelismo
    1–8, 4 por omissão) e o slug do esquema tem a gramática do `create_case`;
  * o esquema é texto com sugestões, NUNCA lista fechada — um esquema novo não
    pode partir o carregamento do perfil num core com o pin antigo;
  * não há interruptor do login nem nomes de papéis no perfil (são env);
  * tudo interno; round-trip byte-fiel, como os outros blocos tipados.
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
from genesis_profile_schema.tool_doc_verification import ProfileToolDocVerificationConfig

P = "tools.config.verify_documents"


def test_registado_e_off_por_default():
    assert _KNOWN_TOOL_CONFIG_MODELS["verify_documents"] is ProfileToolDocVerificationConfig
    assert "verify_documents" not in _DEFAULT_TOOLS_ENABLED
    assert "verify_documents" not in ClientProfileSchema.model_validate({"client_id": "x"}).tools.config


def test_defaults_iguais_aos_do_core():
    c = ProfileToolDocVerificationConfig()
    assert (c.scheme, c.parallelism, c.deployment) == ("concursos", 4, "")


def test_paralelismo_e_o_que_o_core_honra():
    for v in (1, 4, 8):
        assert ProfileToolDocVerificationConfig(parallelism=v).parallelism == v
    for v in (0, 9, 16):
        with pytest.raises(ValidationError):
            ProfileToolDocVerificationConfig(parallelism=v)


@pytest.mark.parametrize("ok", ["concursos", "concursos@2026.10", "outro_esquema", "a"])
def test_esquema_aceita_slug_mesmo_desconhecido(ok):
    assert ProfileToolDocVerificationConfig(scheme=ok).scheme == ok


@pytest.mark.parametrize("mau", ["", "Concursos", "../x", "a b", "x" * 65, "-a", "a;b"])
def test_esquema_recusa_o_que_nao_e_slug(mau):
    with pytest.raises(ValidationError):
        ProfileToolDocVerificationConfig(scheme=mau)


def test_esquema_nao_e_lista_fechada():
    forma = exp.tool_config_shapes()[f"{P}.scheme"]
    assert not forma.get("enum")
    assert pr.control_for(f"{P}.scheme") == pr.COMBOBOX


def test_login_e_papeis_nao_sao_opcao():
    campos = set(ProfileToolDocVerificationConfig.model_fields)
    assert not campos & {"require_login", "auth", "role_names", "allowed_tenants", "classification"}


def test_round_trip_byte_fiel_e_validado_no_perfil_inteiro():
    raw = {"client_id": "x", "tools": {"enabled": ["verify_documents"], "config": {"verify_documents": {
        "scheme": "concursos", "parallelism": 2, "extra_livre": 1}}}}
    prof = ClientProfileSchema.model_validate(raw)
    assert prof.tools.config["verify_documents"] == raw["tools"]["config"]["verify_documents"]
    with pytest.raises(ValidationError):
        ClientProfileSchema.model_validate(
            {"client_id": "x", "tools": {"config": {"verify_documents": {"parallelism": 50}}}})


def test_tudo_interno():
    for campo in ("scheme", "parallelism", "deployment"):
        assert exp.exposure_of(f"{P}.{campo}") == exp.INTERNAL, campo


@pytest.mark.parametrize("locale", ui.LOCALES)
def test_texto_nas_duas_linguas_e_sugestoes(locale):
    for path in exp.tool_config_shapes():
        if path.startswith(P + "."):
            assert ui.label_of(path, locale), f"{path} sem label em {locale}"
    assert "concursos" in ui.options_of(f"{P}.scheme", locale)

# ── nomes no ecrã (28 Out 2026) ──────────────────────────────────────────────

L = f"{P}.labels"


def test_nomes_opcionais_e_null_do_blob_valem_ausente():
    assert ProfileToolDocVerificationConfig().labels is None
    assert ProfileToolDocVerificationConfig.model_validate({"labels": None}).labels is None
    c = ProfileToolDocVerificationConfig.model_validate({"labels": {"case_singular": {"pt": "candidatura", "en": "application"}}})
    assert c.labels.case_singular == {"pt": "candidatura", "en": "application"} and c.labels.title == {}


def test_nomes_curtos_linguas_validas_e_sem_campos_a_mais():
    for mau in ({"title": {"pt": "x" * 201}}, {"title": {"PT!": "x"}}, {"titulo": {"pt": "x"}},
                {"case_plural": "candidaturas"}, {"title": {"pt\n": "x"}}):
        with pytest.raises(ValidationError):
            ProfileToolDocVerificationConfig.model_validate({"labels": mau})


def test_nomes_sao_multilingues_internos_e_com_texto():
    from genesis_profile_schema.i18n_fields import i18n_field_paths
    campos = ("title", "subtitle", "case_singular", "case_plural", "name_example")
    assert {f"{L}.{c}" for c in campos} <= i18n_field_paths()
    for c in campos:
        assert exp.exposure_of(f"{L}.{c}") == exp.INTERNAL, c
        for locale in ui.LOCALES:
            assert ui.label_of(f"{L}.{c}", locale), (c, locale)
    for locale in ui.LOCALES:
        assert "fem" in ui.options_of(f"{P}.scheme", locale)

# ── moldes do cliente dos documentos finais (3 Nov 2026) ─────────────────────

T = f"{P}.document_templates"
SHA = "a" * 64


def _ref(**kw):
    return {"scheme": "fem", "document": "parecer", "name": "parecer_cliente.docx", "sha256": SHA, **kw}


def test_moldes_vazio_por_omissao_e_aceita_a_referencia_do_core():
    assert ProfileToolDocVerificationConfig().document_templates == []
    c = ProfileToolDocVerificationConfig.model_validate({"document_templates": [
        _ref(), _ref(scheme="concursos@2026.10", document="conformidade", name="relatorio-v2.docx")]})
    assert [(r.scheme, r.document) for r in c.document_templates] == [("fem", "parecer"),
                                                                       ("concursos@2026.10", "conformidade")]


@pytest.mark.parametrize("mau", [
    {"scheme": "FEM"}, {"scheme": "../x"}, {"document": "Parecer"}, {"document": "p"}, {"document": "x" * 33},
    {"name": "parecer.doc"}, {"name": "parecer.xlsx"}, {"name": "../parecer.docx"}, {"name": ".docx"},
    {"name": "a b.docx"}, {"sha256": "A" * 64}, {"sha256": "a" * 63}, {"extra": 1},
])
def test_moldes_recusam_referencia_mal_escrita(mau):
    with pytest.raises(ValidationError):
        ProfileToolDocVerificationConfig.model_validate({"document_templates": [_ref(**mau)]})


def test_moldes_um_por_documento_do_esquema():
    with pytest.raises(ValidationError):
        ProfileToolDocVerificationConfig.model_validate({"document_templates": [_ref(), _ref(name="outro.docx")]})
    # a versão fixa conta como o esquema base (o core compara pelo base)
    with pytest.raises(ValidationError):
        ProfileToolDocVerificationConfig.model_validate({"document_templates": [_ref(), _ref(scheme="fem@2026.10")]})
    ok = ProfileToolDocVerificationConfig.model_validate({"document_templates": [
        _ref(), _ref(document="nota_decisao", name="nota.docx")]})
    assert len(ok.document_templates) == 2


def test_moldes_internos_com_texto_e_no_perfil_inteiro():
    for campo in ("scheme", "document", "name", "sha256"):
        assert exp.exposure_of(f"{T}.{campo}") == exp.INTERNAL, campo
        for locale in ui.LOCALES:
            assert ui.label_of(f"{T}.{campo}", locale), (campo, locale)
    for locale in ui.LOCALES:
        assert ui.label_of(T, locale) and ui.help_of(T, locale)
    raw = {"client_id": "x", "tools": {"enabled": ["verify_documents"], "config": {"verify_documents": {
        "scheme": "fem", "document_templates": [_ref()]}}}}
    prof = ClientProfileSchema.model_validate(raw)
    assert prof.tools.config["verify_documents"] == raw["tools"]["config"]["verify_documents"]
    with pytest.raises(ValidationError):
        ClientProfileSchema.model_validate({"client_id": "x", "tools": {"config": {"verify_documents": {
            "document_templates": [_ref(sha256="x")]}}}})


# ── regras mudadas pelo cliente (6 Nov 2026, F2 das regras configuráveis) ────

R = f"{P}.rules"


def _rules(rules):
    return ClientProfileSchema.model_validate(
        {"client_id": "x", "tools": {"config": {"verify_documents": {"scheme": "fem", "rules": rules}}}})


def test_regras_validas_e_vazio_por_omissao():
    ok = {"fem": {"overrides": {
        "fem.territorio": {"params": {"values": ["Leiria", "Pombal"]}, "source": "Despacho X, n.º 2"},
        "fem.janela_evento": {"params": {"from": "2026-01-27", "to": "2026-03-15"}},
        "fem.foto.local": {"params": {"max_km": 2.5}, "severity": "critical"},
        "fem.foto.repetida": {"enabled": False, "params": {"max_hamming": 4}},
    }}}
    cfg = _rules(ok).tools.config["verify_documents"]
    assert cfg["rules"] == ok
    m = ProfileToolDocVerificationConfig.model_validate({"scheme": "fem"})
    assert m.rules == {} and m.model_dump()["rules"] == {}                      # nunca `null` no blob


@pytest.mark.parametrize("bad", [
    {"fem": {"overrides": {"fem.x": {"severity": "info"}}}},                     # gravidade fora da lista
    {"fem": {"overrides": {"fem.x": {"params": {"max_km": True}}}}},            # bool não passa por número
    {"fem": {"overrides": {"fem.x": {"params": {"values": []}}}}},              # lista vazia
    {"fem": {"overrides": {"fem.x": {"params": {"values": ["a" * 201]}}}}},     # valor demasiado longo
    {"fem": {"overrides": {"fem.x": {"params": {"values": ["ok", "  "]}}}}},    # valor em branco
    {"fem": {"overrides": {"fem.x": {"params": {"values": ["a"] * 1001}}}}},    # lista demasiado longa
    {"fem": {"overrides": {"fem.x": {"params": {"Bad-Key": 1}}}}},              # nome de parâmetro estranho
    {"fem": {"overrides": {"fem.x": {"params": {"x": {"nested": 1}}}}}},        # nada de objetos
    {"fem": {"overrides": {"FEM X": {}}}},                                      # id estranho
    {"fem": {"overrides": {"fem.x": {"sentence": "texto livre"}}}},             # só os campos previstos
    {"Fem!": {"overrides": {}}},                                                 # esquema estranho
])
def test_regras_invalidas_recusadas(bad):
    with pytest.raises(Exception):
        _rules(bad)


def test_regras_tem_texto_nas_duas_linguas():
    for locale in ui.LOCALES:
        assert ui.label_of(R, locale)
