"""
tests/test_tool_workspace_default.py — `frontend.features.toolWorkspace` é
OPT-IN (v0.1.69, 23 Set 2026).

O que protege: o core funde o perfil do Blob por cima de
`ClientProfileSchema().to_blob_dict()` (DEFAULT_PROFILE) e resolve o workspace
com `toolWorkspace is not True`. Com o default a True (até à v0.1.68), todo o
perfil SEM a chave recebia o layout dedicado da fatura/BoQ ao ligar a tool —
o ecrã de um cliente mudava sem ninguém o pedir. A migração de clientes do
Studio parte do mesmo dict.
"""

from __future__ import annotations

from genesis_profile_schema import ClientProfileSchema


def test_default_do_modelo_e_false():
    assert ClientProfileSchema().frontend.features.toolWorkspace is False


def test_dict_de_defaults_leva_false():
    # É ESTE dict que o core usa como base do merge (DEFAULT_PROFILE).
    base = ClientProfileSchema().to_blob_dict()
    assert base["frontend"]["features"]["toolWorkspace"] is False


def test_true_explicito_continua_a_valer():
    p = ClientProfileSchema.model_validate({"frontend": {"features": {"toolWorkspace": True}}})
    assert p.frontend.features.toolWorkspace is True
