"""Números por pessoa no painel do agente (`team.people_numbers`, v0.1.182, nível 2 da P15)."""

import pytest

from genesis_profile_schema import ClientProfileSchema, people_numbers_on, people_numbers_problems
from genesis_profile_schema import team as T
from genesis_profile_schema import team_people_numbers as P
from genesis_profile_schema.exposure import EXPOSURE, leaf_paths
from genesis_profile_schema.ui_text import help_of, label_of, note_of

REC = {"text": "Interesse legítimo; AIPD de 20 Nov 2026", "date": "2026-11-20", "channel": "AIPD",
       "by": "Ana Silva (DPO)"}
INF = {"text": "Comunicação interna a todos os trabalhadores", "date": "2026-11-21", "channel": "email",
       "by": "RH"}


def _team(**pn):
    return {"people_numbers": pn}


def test_desligado_por_omissao_e_sem_problemas():
    assert T.ProfileTeam().people_numbers.enabled is False
    assert ClientProfileSchema().team is None
    assert people_numbers_problems(None) == []
    assert people_numbers_problems({}) == []
    assert people_numbers_on(None) is False
    assert people_numbers_on(_team(enabled=False, legal_basis=REC, workers_informed=INF)) is False


def test_ligado_com_os_dois_registos_vale():
    t = _team(enabled=True, legal_basis=REC, workers_informed=INF)
    assert people_numbers_problems(t, today="2026-11-26") == []
    assert people_numbers_on(t) is True


@pytest.mark.parametrize("missing", ["legal_basis", "workers_informed"])
def test_ligado_sem_um_dos_registos_recusa_e_nao_vale(missing):
    t = _team(enabled=True, legal_basis=REC, workers_informed=INF)
    t["people_numbers"].pop(missing)
    codes = [p["code"] for p in people_numbers_problems(t)]
    assert codes == [P.LEGAL_BASIS_MISSING if missing == "legal_basis" else P.WORKERS_NOT_INFORMED]
    assert people_numbers_on(t) is False


@pytest.mark.parametrize("field,value", [
    ("text", ""), ("text", "   "), ("text", "x" * (P.TEXT_MAX + 1)), ("text", "a\u202eb"), ("text", "a\u2028b"), ("text", "a\nb"),
    ("date", "20-11-2026"), ("date", "2026-02-30"), ("date", "２０２６-11-20"), ("date", None),
    ("channel", ""), ("channel", "c" * (P.CHANNEL_MAX + 1)), ("by", ""), ("by", "b" * (P.BY_MAX + 1)),
    ("by", 7),
])
def test_registo_incompleto_ou_mal_formado_nao_conta(field, value):
    rec = dict(REC, **{field: value})
    t = _team(enabled=True, legal_basis=rec, workers_informed=INF)
    assert [p["code"] for p in people_numbers_problems(t)] == [P.LEGAL_BASIS_MISSING]
    assert people_numbers_on(t) is False


def test_os_problemas_nunca_levam_o_valor():
    t = _team(enabled=True, legal_basis=dict(REC, text="SEGREDO-DO-CLIENTE", date="bad"), workers_informed=None)
    out = people_numbers_problems(t)
    assert "SEGREDO" not in repr(out)
    assert {p["loc"] for p in out} == {"team.people_numbers.legal_basis", "team.people_numbers.workers_informed"}


def test_data_no_futuro_recusa_so_com_o_hoje_de_quem_grava():
    t = _team(enabled=True, legal_basis=dict(REC, date="2026-12-31"), workers_informed=INF)
    assert [p["code"] for p in people_numbers_problems(t, today="2026-11-26")] == [P.DATE_IN_FUTURE]
    # Amanhã é tolerado (fuso: Lisboa à meia-noite ainda é ontem em UTC).
    t2 = _team(enabled=True, legal_basis=dict(REC, date="2026-11-27"), workers_informed=INF)
    assert people_numbers_problems(t2, today="2026-11-26") == []
    # Sem relógio (o core em execução), a forma basta.
    assert people_numbers_on(t) is True


def test_ligado_tem_de_ser_booleano_estrito():
    with pytest.raises(Exception):
        T.ProfileTeam.model_validate({"people_numbers": {"enabled": "true"}})
    # Uma string nunca liga a regra pura.
    assert people_numbers_problems({"people_numbers": {"enabled": "true"}}) == []
    assert people_numbers_on({"people_numbers": {"enabled": "true", "legal_basis": REC,
                                                 "workers_informed": INF}}) is False


def test_o_perfil_valida_e_grava_o_bloco():
    p = ClientProfileSchema.model_validate({"team": {"people_numbers": {
        "enabled": True, "legal_basis": REC, "workers_informed": INF}}})
    d = p.to_blob_dict()
    assert d["team"]["people_numbers"]["enabled"] is True
    assert d["team"]["people_numbers"]["legal_basis"]["by"] == "Ana Silva (DPO)"
    # Forma do blob gravado por um core com a 0.1.182 sem o bloco: registos a `null` (contam como ausentes).
    d2 = ClientProfileSchema.model_validate({"team": {"enabled": True}}).to_blob_dict()
    assert d2["team"]["people_numbers"] == {"enabled": False, "legal_basis": None, "workers_informed": None}
    assert people_numbers_on(d2["team"]) is False


def test_teto_do_texto_no_modelo():
    with pytest.raises(Exception):
        T.ProfileTeam.model_validate({"people_numbers": {"legal_basis": {"text": "x" * (P.TEXT_MAX + 1)}}})


def test_capacidade_no_catalogo_e_so_todas_as_frentes():
    assert P.CAPABILITY == "team.people_numbers"
    assert P.CAPABILITY in T.CAPABILITY_IDS
    assert T.capability_module(P.CAPABILITY) == T.MODULE_TEAM
    # Prefixo `team.`: o core trata-a como «todas as frentes» e nunca a dá ao Agent Tester.
    assert P.CAPABILITY.startswith("team.")
    # Nenhum papel pronto a traz: é o cliente que decide quem vê os números dos outros.
    assert all(P.CAPABILITY not in r["capabilities"] for m in T.MODULES for r in T.role_templates(m))


def test_exposicao_o_cliente_le_so_a_genesis_grava():
    folhas = [p for p in leaf_paths() if p.startswith("team.people_numbers.")]
    assert len(folhas) == 9
    assert all(EXPOSURE[p] == "client_read" for p in folhas)


@pytest.mark.parametrize("loc", ["pt-PT", "en-GB"])
def test_textos_com_aviso_legal(loc):
    assert label_of("team.people_numbers.enabled", loc)
    assert help_of("team.people_numbers.enabled", loc)
    note = note_of("team.people_numbers.enabled", loc)
    assert ("parecer jurídico" in note) if loc == "pt-PT" else ("legal advice" in note)
    for p in leaf_paths():
        if p.startswith("team.people_numbers."):
            assert label_of(p, loc), p


def test_nunca_ha_campo_de_pontuacao_nem_ranking():
    """Nível 3 da P15: nada de pontuações, rankings ou apreciações sobre pessoas neste bloco."""
    import json
    sch = json.dumps(P.TeamPeopleNumbers.model_json_schema()).lower()
    for word in ("score", "rank", "rating", "pontua", "avalia", "apprais"):
        assert word not in sch, word
