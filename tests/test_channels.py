"""
`channels` (v0.1.163, carril C1a do pack dos canais): entradas e encaminhamento.
Ausente = hoje; gramática fechada (campo/operador desconhecido = erro).
"""

import pytest
from pydantic import ValidationError

from genesis_profile_schema.channels import (MAX_CONDITIONS, OPS, OPS_BY_KIND, ROUTE_FIELDS,
                                             ChannelCondition, ProfileChannels)
from genesis_profile_schema.client_profile_schema import ClientProfileSchema as ClientProfile
from genesis_profile_schema.exposure import exposure_of


def _route(**kw):
    base = {"id": "r1", "to": {"module": "queue", "queue": "consultas"}}
    base.update(kw)
    return base


def test_ausente_e_null_valem_hoje():
    assert ClientProfile.model_validate({}).channels is None
    assert ClientProfile.model_validate({"channels": None}).channels is None


def test_forma_completa_e_dump_com_os_nomes_do_perfil():
    raw = {"inputs": [{"id": "candidaturas", "channel": "email", "ingest_source": "caixa_geral"}],
           "routes": [_route(id="cand", inputs=["candidaturas"],
                             when={"all": [{"field": "from.domain", "op": "in_list", "value": ["cliente.pt"]}],
                                   "any": [{"field": "subject", "op": "contains", "value": "candidatura"},
                                           {"field": "attachments.mime", "op": "equals", "value": "application/pdf"}]}),
                      _route(id="resto")]}
    ch = ProfileChannels.model_validate(raw)
    out = ch.model_dump(mode="json")
    assert out["routes"][0]["when"]["all"][0]["field"] == "from.domain"
    assert "any" in out["routes"][0]["when"] and out["routes"][1]["when"] == {"all": [], "any": []}
    assert ProfileChannels.model_validate(out) == ch, "o dump volta a validar igual"
    prof = ClientProfile.model_validate({"channels": raw}).to_blob_dict()
    assert prof["channels"]["inputs"][0]["ingest_source"] == "caixa_geral"


@pytest.mark.parametrize("bad", [
    {"field": "remetente", "op": "equals", "value": "x"},           # campo desconhecido
    {"field": "subject", "op": "startswith", "value": "x"},         # operador desconhecido
    {"field": "subject", "op": "gte", "value": 3},                  # operador de número num texto
    {"field": "time.hour", "op": "contains", "value": "9"},         # texto num número
    {"field": "time.hour", "op": "gte", "value": 24},
    {"field": "attachments.size", "op": "lte", "value": -1},
    {"field": "attachments.size", "op": "gte", "value": True},      # bool não é número
    {"field": "thread.is_reply", "op": "equals", "value": "sim"},
    {"field": "subject", "op": "exists", "value": "sim"},
    {"field": "subject", "op": "in_list", "value": []},
    {"field": "subject", "op": "in_list", "value": ["ok", ""]},
    {"field": "subject", "op": "equals", "value": ""},
    {"field": "subject", "op": "equals", "value": "x" * 201},
    {"field": "attachments.size", "op": "gte", "value": float("inf")},
    {"field": "attachments.size", "op": "gte", "value": float("nan")},
    {"field": "subject", "op": "equals", "value": "x", "extra": 1},
])
def test_condicao_fora_da_gramatica_e_erro(bad):
    with pytest.raises(ValidationError):
        ChannelCondition.model_validate(bad)


def test_operadores_por_tipo_cobrem_os_campos():
    assert set(OPS) == {op for ops in OPS_BY_KIND.values() for op in ops}
    assert set(ROUTE_FIELDS.values()) <= set(OPS_BY_KIND)


def test_teto_de_condicoes():
    many = [{"field": "subject", "op": "contains", "value": f"t{i}"} for i in range(MAX_CONDITIONS + 1)]
    with pytest.raises(ValidationError):
        ProfileChannels.model_validate({"routes": [_route(when={"any": many})]})


@pytest.mark.parametrize("raw", [
    {"inputs": [{"id": "a", "channel": "email"}]},                                  # email sem fonte
    {"inputs": [{"id": "a", "channel": "sms", "ingest_source": "x"}]},              # fonte fora do email
    {"inputs": [{"id": "-a", "channel": "email", "ingest_source": "x"}]},           # id a começar por hífen
    {"inputs": [{"id": "a" + chr(10), "channel": "email", "ingest_source": "x"}]},  # quebra de linha no fim
    {"inputs": [{"id": "a" * 65, "channel": "email", "ingest_source": "x"}]},      # longo demais
    {"inputs": [{"id": "a", "channel": "email", "ingest_source": " x "},
                {"id": "b", "channel": "email", "ingest_source": "x"}]},           # a mesma fonte com espaços
    {"inputs": [{"id": "a", "channel": "fax", "ingest_source": "x"}]},              # canal desconhecido
    {"inputs": [{"id": "a", "channel": "email", "ingest_source": "x"},
                {"id": "a", "channel": "email", "ingest_source": "y"}]},           # id repetido
    {"inputs": [{"id": "a", "channel": "email", "ingest_source": "x"},
                {"id": "b", "channel": "email", "ingest_source": "x"}]},           # duas para a mesma fonte
    {"routes": [_route(), _route()]},                                               # rota repetida
    {"routes": [_route(to={"module": "doc_verification", "queue": "x"})]},          # módulo fora do C1a
    {"routes": [_route(to={"module": "queue", "queue": " "})]},
    {"routes": [_route(inputs=["a", "a"])]},
    {"inputs": [{"id": "a", "channel": "email", "ingest_source": "x"}],
     "routes": [_route(inputs=["b"])]},                                             # entrada que não existe
    {"routes": [_route(extra=True)]},
])
def test_formas_invalidas(raw):
    with pytest.raises(ValidationError):
        ProfileChannels.model_validate(raw)


def test_sem_entradas_declaradas_as_rotas_apontam_para_fontes():
    ch = ProfileChannels.model_validate({"routes": [_route(inputs=["caixa_geral"])]})
    assert ch.routes[0].inputs == ["caixa_geral"]


def test_entradas_da_genesis_rotas_do_cliente():
    for path in ("channels.inputs.id", "channels.inputs.ingest_source", "channels.inputs.enabled"):
        assert exposure_of(path) == "internal"
    for path in ("channels.routes.when.all.value", "channels.routes.to.queue", "channels.routes.enabled",
                 "channels.routes.to.module", "channels.routes.to.front", "channels.routes.to.join.by",
                 "channels.routes.to.join.window_days", "channels.routes.to.receipt.enabled",
                 "channels.routes.to.receipt.list_refused", "channels.routes.id", "channels.routes.inputs"):
        assert exposure_of(path) == "client_write"


def test_ids_das_fontes_do_studio_servem_de_entrada():
    ch = ProfileChannels.model_validate({"routes": [_route(inputs=["Encomendas-PT", "pedidos_agente", "x" * 64])]})
    assert ch.routes[0].inputs[0] == "Encomendas-PT"


def test_fonte_guardada_sem_espacos():
    ch = ProfileChannels.model_validate({"inputs": [{"id": "a", "channel": "email", "ingest_source": " caixa "}]})
    assert ch.inputs[0].ingest_source == "caixa"


@pytest.mark.parametrize("cond", [
    {"field": "from.domain", "op": "contains", "value": "exemplo.pt"},     # endereços: nunca substring
    {"field": "to", "op": "contains", "value": "x"},
    {"field": "subject", "op": "regex", "value": "x"},                    # sem regex (ReDoS)
])
def test_endereco_sem_substring_e_sem_regex(cond):
    with pytest.raises(ValidationError):
        ChannelCondition.model_validate(cond)


def test_destino_verificacao_documental():
    ch = ProfileChannels.model_validate({"routes": [{
        "id": "cand", "when": {"all": [{"field": "subject", "op": "contains", "value": "candidatura"}]},
        "to": {"module": "doc_verification", "front": " Candidaturas ",
               "join": {"by": ["reference", "thread"], "window_days": 14},
               "receipt": {"enabled": True}}}]})
    t = ch.routes[0].to
    assert t.module == "doc_verification" and t.front == "candidaturas" and t.queue is None
    assert t.join.by == ["reference", "thread"] and t.join.window_days == 14
    assert t.receipt.enabled and t.receipt.list_refused
    # Por omissão: frente da caixa, junção pela referência em 7 dias, sem recibo.
    t = ProfileChannels.model_validate({"routes": [{"id": "c", "to": {"module": "doc_verification"}}]}).routes[0].to
    assert t.front is None and t.join is None and t.receipt is None
    assert C_JOIN().by == ["reference"] and C_JOIN().window_days == 7


def C_JOIN():
    from genesis_profile_schema.channels import CaseJoin
    return CaseJoin()


@pytest.mark.parametrize("to", [
    {"module": "doc_verification", "queue": "x"},                       # VD não leva fila
    {"module": "queue"},                                                 # fila sem fila
    {"module": "queue", "queue": "x", "front": "cand"},                  # frente só na VD
    {"module": "queue", "queue": "x", "receipt": {"enabled": True}},     # recibo só na VD
    {"module": "doc_verification", "front": "Não Slug!"},
    {"module": "doc_verification", "join": {"by": ["nif"]}},             # critério fora da lista
    {"module": "doc_verification", "join": {"by": ["sender", "sender"]}},
    {"module": "doc_verification", "join": {"window_days": 0}},
    {"module": "doc_verification", "join": {"window_days": 91}},
    {"module": "doc_verification", "receipt": {"enabled": True, "text": "x"}},  # campo desconhecido
    {"module": "doc_verification", "join": {"by": []}},                  # junção sem critério
    {"module": "doc_verification", "join": {"window_days": True}},       # inteiro estrito
    {"module": "doc_verification", "join": {"window_days": "7"}},
    {"module": "doc_verification", "front": "-cand"},                    # slug começa por letra/dígito
    {"module": "queue", "queue": "x", "join": {"by": ["reference"]}},    # junção só na VD
    {"module": "outro"},
])
def test_destinos_invalidos(to):
    with pytest.raises(ValidationError):
        ProfileChannels.model_validate({"routes": [{"id": "r", "to": to}]})


def test_literais_batem_com_as_constantes():
    from typing import get_args
    from genesis_profile_schema import channels as C
    assert set(get_args(C.ChannelKind)) == set(C.CHANNEL_KINDS)
    assert set(get_args(C.RouteField)) == set(C.ROUTE_FIELDS)
    assert set(get_args(C.RouteOp)) == set(C.OPS)
    assert set(get_args(C.RouteTarget.model_fields["module"].annotation)) == set(C.MODULES)
    by_args = get_args(get_args(C.CaseJoin.model_fields["by"].annotation)[0])
    assert set(by_args) == set(C.JOIN_BY)
    assert set(C.LIVE_CHANNELS) <= set(C.CHANNEL_KINDS)


def test_rota_de_fila_grava_so_o_que_tinha():
    # Um core com a v0.1.163 (`extra="forbid"`) recusava chaves `null` novas no `to`.
    ch = ProfileChannels.model_validate({"routes": [{"id": "r", "to": {"module": "queue", "queue": "fila"}}]})
    assert ch.model_dump(mode="json")["routes"][0]["to"] == {"module": "queue", "queue": "fila"}
    vd = ProfileChannels.model_validate({"routes": [{"id": "v", "to": {"module": "doc_verification"}}]})
    assert vd.model_dump(mode="json")["routes"][0]["to"] == {"module": "doc_verification"}
    # E pelo perfil inteiro (`to_blob_dict`).
    blob = ClientProfile.model_validate({"client_id": "x", "channels": {"routes": [
        {"id": "r", "to": {"module": "queue", "queue": "fila"}}]}}).to_blob_dict()
    assert blob["channels"]["routes"][0]["to"] == {"module": "queue", "queue": "fila"}


def test_vd_com_fila_vazia_e_a_mensagem_certa():
    ch = ProfileChannels.model_validate({"routes": [{"id": "v", "to": {"module": "doc_verification", "queue": ""}}]})
    assert ch.routes[0].to.queue is None
    with pytest.raises(ValidationError, match="precisa da fila"):
        ProfileChannels.model_validate({"routes": [{"id": "r", "to": {"module": "queue", "queue": "  "}}]})
