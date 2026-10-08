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
