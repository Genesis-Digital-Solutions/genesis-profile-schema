"""
Referências opacas de quem pede/carrega no GAIBO (F-S104, 15 Nov 2026).

`PublishRequest.requested_by_ref`, `RunDocument.uploaded_by_ref` e
`InviteRequest.requested_by_ref` só eram validados pelo comprimento: a regra
«nunca o email nem o nome» vivia num comentário. Passa a allowlist opaca
(`is_valid_opaque_ref`). Os valores aceites são os que o GAIBO produz HOJE
(lidos no produtor a 15 Nov 2026): `ref-<uuid hex>` (`knowledge/publication.py`),
o `user_id` nos convites (`team/service.py`, `product_team/service.py`): oid GUID
do Entra, uuid da ficha, `genesis-support:<oid>` (`core/rbac.py`), e o
`studio-republish` do próprio Studio.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from genesis_profile_schema import gaibo_index as gi

NOW = datetime(2026, 11, 15, 10, 0, tzinfo=timezone.utc).isoformat()
SRC = "gaibo/j-abcdefgh/manual.pdf"
OID = "550e8400-e29b-41d4-a716-446655440000"

REAIS = [
    "ref-" + "0123456789abcdef" * 2,              # publicação (uuid4().hex)
    OID,                                          # oid do Entra / uuid da ficha
    f"genesis-support:{OID}",                     # suporte da Genesis
    "support:" + OID,                             # forma citada no relatório do F-S104
    "studio-republish",                           # republicação pelo Studio
    "aQ9mK2xZ7bN4pR8vC1dF6gH3jL0wS5tU9yA2eB7nX4q",  # `sub` do Entra (base64url)
    "u-7", "audit-123", "x" * 128,
]

RECUSADOS = [
    "ana.silva@remax.pt",            # canário: um email
    "Ana Silva",                     # canário: um nome
    "João",                          # acentos (texto livre)
    " ref-1", "ref-1 ", "ref-1\n",   # espaços e quebra de linha (fullmatch)
    "-ref", ":ref", ".ref",          # tem de começar por letra ou dígito
    "ref/1", "ref|1", "<ref>", "ref%40x",
    "ref-٢٠٢٦",                      # dígitos de outra escrita (só ASCII)
    "ｒｅｆ",                         # largura total
    "x" * 129,
    "",
]


@pytest.mark.parametrize("value", REAIS)
def test_valores_reais_do_gaibo_passam(value):
    assert gi.is_valid_opaque_ref(value)
    req = gi.PublishRequest.model_validate({
        "request_id": "pr-abcdefgh", "client_id": "remax-v2-dev", "requested_at": NOW,
        "requested_by_ref": value,
        "items": [{"source_file": SRC, "action": "remove"}]})
    assert req.requested_by_ref == value
    doc = gi.RunDocument.model_validate({"source_file": SRC, "action": "indexed", "uploaded_by_ref": value})
    assert doc.uploaded_by_ref == value
    inv = gi.InviteRequest.model_validate({
        "invite_id": "inv-abcdefgh12", "client_id": "remax-v2-dev", "requested_at": NOW,
        "requested_by_ref": value, "email": "ana@remax.pt"})
    assert inv.requested_by_ref == value


@pytest.mark.parametrize("value", RECUSADOS)
def test_email_nome_e_texto_livre_recusados_nos_tres_campos(value):
    assert not gi.is_valid_opaque_ref(value)
    with pytest.raises(ValidationError):
        gi.PublishRequest.model_validate({
            "request_id": "pr-abcdefgh", "client_id": "remax-v2-dev", "requested_at": NOW,
            "requested_by_ref": value,
            "items": [{"source_file": SRC, "action": "remove"}]})
    with pytest.raises(ValidationError):
        gi.RunDocument.model_validate({"source_file": SRC, "action": "indexed", "uploaded_by_ref": value})
    with pytest.raises(ValidationError):
        gi.InviteRequest.model_validate({
            "invite_id": "inv-abcdefgh12", "client_id": "remax-v2-dev", "requested_at": NOW,
            "requested_by_ref": value, "email": "ana@remax.pt"})


def test_uploaded_by_ref_continua_opcional():
    # relatórios antigos não o têm — e um `null` explícito também carrega
    assert gi.RunDocument.model_validate({"source_file": SRC, "action": "indexed"}).uploaded_by_ref is None
    assert gi.RunDocument.model_validate(
        {"source_file": SRC, "action": "indexed", "uploaded_by_ref": None}).uploaded_by_ref is None


def test_nao_texto_recusado():
    for value in (None, 12, ["ref-1"], {"ref": 1}):
        assert not gi.is_valid_opaque_ref(value)
