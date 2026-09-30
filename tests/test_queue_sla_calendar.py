"""
Prazo por fila e calendário de negócio (v0.1.77, F1.4 do genai-core).

  • `reviewQueues.{fila}.sla`: valor > 0, unidade fechada, prazo por urgência
    só com números positivos;
  • `calendar`: feriados `AAAA-MM-DD` ou `MM-DD` válidos, fim de semana de 0 a
    6 (nunca os 7), `national` fechado;
  • um perfil sem nada disto valida e não ganha `calendar` (fica None).
"""

import pytest
from pydantic import ValidationError

from genesis_profile_schema.client_profile_schema import (
    ClientProfileSchema, ProfileCalendar, ProfileReviewQueueSla,
)


def test_sla_valido():
    s = ProfileReviewQueueSla(value=15, unit="business_days", by_urgency={"Urgente": 2})
    assert s.value == 15 and s.unit == "business_days" and s.by_urgency == {"Urgente": 2.0}


@pytest.mark.parametrize("bad", [{"value": 0}, {"value": -1}, {"value": 9000},
                                 {"value": True},
                                 {"unit": "dias"}, {"by_urgency": {"alta": 0}},
                                 {"by_urgency": {"alta": True}}, {"by_urgency": ["alta"]},
                                 {"by_urgency": {"alta": None}}, {"by_urgency": {"alta": [1]}},
                                 {"by_urgency": {"alta": {"x": 1}}}, {"by_urgency": {"": 1}},
                                 {"by_urgency": {"Média": 1, " media ": 2}},
                                 {"value": 400, "unit": "business_days"},
                                 {"by_urgency": {"alta": 400}, "unit": "business_days"}])
def test_sla_invalido(bad):
    with pytest.raises(ValidationError):
        ProfileReviewQueueSla(**bad)


def test_calendario_valido_e_sem_repetidos():
    c = ProfileCalendar(national="none", weekend=[4, 5, 5], holidays=["06-13", "2026-12-24", "06-13"])
    assert c.weekend == [4, 5] and c.holidays == ["06-13", "2026-12-24"]


@pytest.mark.parametrize("bad", [{"holidays": ["13/06"]}, {"holidays": ["02-30"]},
                                 {"holidays": ["2026-13-01"]}, {"weekend": [7]},
                                 {"weekend": [0, 1, 2, 3, 4, 5, 6]}, {"national": "ES"},
                                 {"weekend": [True]}, {"holidays": ["easter+200"]},
                                 {"holidays": ["pascoa+1"]},
                                 # 108 datas: acima do tecto de 100
                                 {"holidays": [f"2026-{m:02d}-{d:02d}" for m in range(1, 13)
                                               for d in range(1, 10)]}])
def test_calendario_invalido(bad):
    with pytest.raises(ValidationError):
        ProfileCalendar(**bad)


def test_perfil_sem_nada_disto_nao_ganha_calendario():
    p = ClientProfileSchema.model_validate({"reviewQueues": {"f": {}}})
    assert p.calendar is None and p.reviewQueues["f"].sla is None
    # No blob fica `null` (o to_blob_dict não omite nulos) — é o que o core lê.
    blob = p.to_blob_dict()
    assert blob.get("calendar") is None and blob["reviewQueues"]["f"].get("sla") is None


def test_urgencia_arabe_e_feriados_moveis():
    s = ProfileReviewQueueSla(by_urgency={"عاجل": 1, "عادي": 48})
    assert s.by_urgency == {"عاجل": 1.0, "عادي": 48.0}
    c = ProfileCalendar(holidays=["EASTER+39", "easter-47", "easter"])
    assert c.holidays == ["easter+39", "easter-47", "easter"]


def test_perfil_com_sla_e_calendario():
    p = ClientProfileSchema.model_validate({
        "reviewQueues": {"recl": {"sla": {"value": 15, "unit": "business_days"}}},
        "calendar": {"holidays": ["06-13"]}})
    assert p.reviewQueues["recl"].sla.value == 15
    assert p.calendar.national == "PT" and p.calendar.weekend == [5, 6]
