"""
tests/test_tool_run_code.py — `tools.config.run_code` (v0.1.67, 22 Set 2026;
F3 do parecer GPT-6 Astra: análise com código numa sandbox do Azure OpenAI).

O que protege: a tool é OFF por omissão (só existe em `tools.enabled`); os
tectos têm piso — uma sessão de código factura-se à parte, por minuto com
mínimo de cinco, e um perfil malformado não pode pôr a sandbox a desistir ao
fim de 2 s nem a abrir 50 sessões por resposta; a memória é lista fechada; e
a config é interna (custo e dados que saem para o fornecedor não se afinam
pelo cliente).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from genesis_profile_schema import exposure as exp
from genesis_profile_schema.client_profile_schema import (
    ClientProfileSchema,
    ProfileToolRunCodeConfig,
    _DEFAULT_TOOLS_ENABLED,
)


def test_off_por_default():
    assert "run_code" not in _DEFAULT_TOOLS_ENABLED
    prof = ClientProfileSchema.model_validate({"client_id": "x"})
    assert "run_code" not in prof.tools.enabled
    assert "run_code" not in prof.tools.config


def test_defaults_e_pisos():
    c = ProfileToolRunCodeConfig()
    assert (c.deployment, c.timeout_s, c.max_runs_per_turn, c.memory,
            c.max_output_files, c.allow_attachments) == ("", 120, 2, "1g", 5, True)
    assert ProfileToolRunCodeConfig(timeout_s=60).timeout_s == 60
    with pytest.raises(ValidationError):
        ProfileToolRunCodeConfig(timeout_s=2)
    with pytest.raises(ValidationError):
        ProfileToolRunCodeConfig(max_runs_per_turn=0)
    with pytest.raises(ValidationError):
        ProfileToolRunCodeConfig(max_output_files=0)


def test_memoria_e_lista_fechada():
    for m in ("1g", "4g", "16g", "64g"):
        assert ProfileToolRunCodeConfig(memory=m).memory == m
    with pytest.raises(ValidationError):
        ProfileToolRunCodeConfig(memory="2g")


def test_o_bloco_e_validado_no_perfil_inteiro_sem_alterar_o_gravado():
    raw = {"client_id": "x", "tools": {"enabled": ["run_code"],
                                        "config": {"run_code": {"memory": "4g", "extra_livre": 1}}}}
    prof = ClientProfileSchema.model_validate(raw)
    # round-trip byte-fiel: o model tipado guarda a forma, não reescreve
    assert prof.tools.config["run_code"] == {"memory": "4g", "extra_livre": 1}
    with pytest.raises(ValidationError):
        ClientProfileSchema.model_validate(
            {"client_id": "x", "tools": {"config": {"run_code": {"timeout_s": 1}}}})


def test_config_e_interna_e_o_interruptor_e_visivel():
    """`tools.config` é interno em bloco (herança pelo mapa); `tools.enabled` é
    o escopo contratado que o cliente vê."""
    assert exp.exposure_of("tools.config.run_code.timeout_s") == exp.INTERNAL
    assert exp.exposure_of("tools.config.run_code.memory") == exp.INTERNAL
    assert exp.exposure_of("tools.enabled") == exp.CLIENT_READ
