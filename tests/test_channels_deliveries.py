"""channels.outbound.deliveries (v0.1.172, C2-mín fase 5): a forma do mapeamento de uma entrega a um GED."""

import copy
import typing

import pytest
from pydantic import ValidationError

from genesis_profile_schema.channels import ProfileChannels
from genesis_profile_schema import channels_deliveries as cd


def _delivery(**over):
    d = {
        "id": "parecer-filedoc", "enabled": True,
        "when": {"module": "doc_verification", "event": "opinion_issued"},
        "to": {"transport": "mcp", "server": "mcp-filedoc-demogen-dev", "connector": "dms"},
        "record": {"record_type": 40, "subtype": "outgoing", "company_id": 1, "classification": [3],
                   "subject": {"template": "Parecer — {case.application_number} — {case.entity_name}"},
                   "from_user": "issuer_by_email", "to": {"user_id": 21},
                   "dynamic_fields": {"autoKeyColum102": {"value": {"source": "case.application_number"},
                                                          "type": "Text"}}},
        "process": {"by": "number", "from": "case.procedure"},
        "files": {"main": "pdf", "extra": ["docx", "rules"]},
        "route": {"routing_type": 3, "to": {"group_id": 7}, "message": {"literal": "Para assinatura"},
                  "deadline_days": 5},
    }
    d.update(over)
    return d


def _channels(*deliveries, kinds=None):
    return {"outbound": {"kinds": kinds if kinds is not None else [{"kind": "document.deliver", "enabled": True}],
                         "deliveries": list(deliveries)}}


def _ok(d):
    return ProfileChannels.model_validate(_channels(d))


def _bad(d, *, where=("record", "subject")):
    with pytest.raises(ValidationError):
        _ok(d)


def test_forma_combinada_valida_e_relida_igual():
    m = _ok(_delivery())
    dumped = m.model_dump()
    assert ProfileChannels.model_validate(dumped).model_dump() == dumped
    out = dumped["outbound"]["deliveries"][0]
    # `from` é a chave do contrato, nunca `from_`, com ou sem by_alias
    assert out["process"] == {"by": "number", "from": "case.procedure"}
    assert m.model_dump(by_alias=True)["outbound"]["deliveries"][0]["process"]["from"] == "case.procedure"
    assert m.model_dump(mode="json")["outbound"]["deliveries"][0]["process"] == {"by": "number", "from": "case.procedure"}


def test_desligada_por_omissao():
    d = _delivery()
    d.pop("enabled")
    assert _ok(d).outbound.deliveries[0].enabled is False


def test_enabled_estrito():
    _bad(_delivery(enabled="yes"))
    _bad(_delivery(enabled=1))


@pytest.mark.parametrize("subject", [
    {"template": "Parecer {case.nope}"},                      # campo fora da lista
    {"template": "Parecer {case.name} }"},                    # chaveta solta
    {"template": "Parecer {{case.name}}"},                    # aninhado
    {"template": "Parecer {case.name|upper}"},                # filtro
    {"template": "Sem marcadores"},                           # devia ser literal
    {"template": "x" * 1025 + "{case.name}"},                 # teto
    {"template": "x" * 502 + "{case.name}"},                  # teto do assunto (512)
    {"literal": "a\u202eb"},                                  # bidi (disfarça o texto)
    {"literal": "a\u200bb"},                                  # largura zero
    {"literal": "a\ufeffb"},                                  # BOM
    {"literal": "a\nb"},                                      # quebra de linha
    {"literal": "a\u2028b"},                                  # separador de linha unicode
    {"literal": "a\x00b"},                                    # NUL
    {"literal": "x" * 513},
    {"source": "case.x"},
    {"source": "name"},                                       # caminho livre
    {"literal": "a", "source": "case.name"},                  # dois de uma vez
    {},                                                       # nenhum
    {"literal": "a", "extra": 1},
])
def test_assunto_recusa(subject):
    d = _delivery()
    d["record"]["subject"] = subject
    _bad(d)


@pytest.mark.parametrize("subject", [
    {"source": "case.opinion_ref"}, {"literal": "Parecer"}, {"template": "{case.name}"},
    {"template": "Parecer {case.opinion_ref} v{case.opinion_version} de {case.issued_on}"},
])
def test_assunto_aceita(subject):
    d = _delivery()
    d["record"]["subject"] = subject
    _ok(d)


def test_modelo_so_no_assunto_e_na_mensagem():
    d = _delivery()
    d["record"]["dynamic_fields"]["autoKeyColum102"]["value"] = {"template": "{case.name}"}
    _bad(d)
    d = _delivery()
    d["route"]["message"] = {"template": "Parecer {case.opinion_ref}"}
    _ok(d)


def test_mensagem_do_encaminhamento_ate_1000():
    d = _delivery()
    d["route"]["message"] = {"literal": "x" * 1001}
    _bad(d)


@pytest.mark.parametrize("key", ["1abc", "a-b", "a b", "a" * 65, "ã"])
def test_chave_de_campo_dinamico_recusada(key):
    d = _delivery()
    d["record"]["dynamic_fields"] = {key: {"value": {"literal": "x"}}}
    _bad(d)


def test_tipo_do_campo_dinamico():
    d = _delivery()
    d["record"]["dynamic_fields"]["autoKeyColum102"]["type"] = 1
    _ok(d)
    for bad in (0, -1, "Text;drop", True):
        d["record"]["dynamic_fields"]["autoKeyColum102"]["type"] = bad
        _bad(d)


def test_destinatario_do_registo_sem_grupo():
    for to in ({"group_id": 1}, {"user_id": 1, "email": "a@b.pt"}, {}, {"user_id": 0}, {"user_id": "21"},
               {"email": "nao-e-email"}, {"email": "a@b.pt\n"}):
        d = _delivery()
        d["record"]["to"] = to
        _bad(d)
    d = _delivery()
    d["record"]["to"] = {"email": "ana.ferreira@ccdr.example.test"}
    _ok(d)


def test_destinatario_do_encaminhamento_exatamente_um():
    for to in ({}, {"user_id": 1, "group_id": 2}, {"group_id": 0}):
        d = _delivery()
        d["route"]["to"] = to
        _bad(d)


def test_processo():
    for proc in ({"by": "nif", "from": "case.entity_nif"}, {"by": "number", "from": "case.x"},
                 {"by": "number"}, {"by": "number", "from": "case.name", "x": 1}):
        d = _delivery(process=proc)
        _bad(d)
    _ok(_delivery(process=None))


def test_ficheiros():
    _bad(_delivery(files={"main": "docx"}))
    _bad(_delivery(files={"extra": ["pdf"]}))
    _bad(_delivery(files={"extra": ["docx", "docx"]}))
    _ok(_delivery(files={}))


def test_evento_e_transporte_fechados():
    _bad(_delivery(when={"module": "queue", "event": "opinion_issued"}))
    _bad(_delivery(when={"module": "doc_verification", "event": "case_decided"}))
    _bad(_delivery(to={"transport": "webhook", "server": "x", "connector": "dms"}))
    _bad(_delivery(to={"transport": "mcp", "server": "x y", "connector": "dms"}))
    _bad(_delivery(to={"transport": "mcp", "server": "", "connector": "dms"}))


@pytest.mark.parametrize("did", ["Parecer", "-x", "a" * 41, "a b", "a\n"])
def test_id_recusado(did):
    _bad(_delivery(id=did))


def test_ids_unicos_e_teto():
    with pytest.raises(ValidationError):
        ProfileChannels.model_validate(_channels(_delivery(), _delivery()))
    many = [_delivery(id=f"d{i}") for i in range(cd.MAX_DELIVERIES + 1)]
    with pytest.raises(ValidationError):
        ProfileChannels.model_validate(_channels(*many))


def test_classificacao():
    for cls in ([0], [1, 1], list(range(1, 22)), ["3"]):
        d = _delivery()
        d["record"]["classification"] = cls
        _bad(d)


def test_tetos_e_numeros_estritos():
    _bad(_delivery(route={"routing_type": 3, "to": {"user_id": 1}, "deadline_days": 366}))
    d = _delivery()
    d["record"]["record_type"] = "40"
    _bad(d)
    d = _delivery()
    d["record"]["dynamic_fields"] = {f"k{i}": {"value": {"literal": "x"}} for i in range(51)}
    _bad(d)


def test_sem_entregas_nao_se_grava():
    m = ProfileChannels.model_validate(_channels())
    assert "deliveries" not in m.model_dump()["outbound"]
    m = ProfileChannels.model_validate({"outbound": {"kinds": [], "deliveries": []}})
    assert "outbound" not in m.model_dump()


def test_so_entregas_grava_o_outbound():
    m = ProfileChannels.model_validate(_channels(_delivery(), kinds=[]))
    assert m.model_dump()["outbound"]["deliveries"][0]["id"] == "parecer-filedoc"


def test_lista_de_campos_e_o_literal_iguais():
    assert set(typing.get_args(cd.CaseField)) == set(cd.CASE_FIELDS)
    assert len(cd.CASE_FIELDS) == len(set(cd.CASE_FIELDS))
    for f in cd.CASE_FIELDS:
        assert cd.PLACEHOLDER_RE.fullmatch("{" + f + "}")


def test_entrada_original_nao_e_alterada():
    d = _delivery()
    before = copy.deepcopy(d)
    _ok(d)
    assert d == before
