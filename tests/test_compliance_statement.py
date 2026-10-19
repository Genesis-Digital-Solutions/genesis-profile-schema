# -*- coding: utf-8 -*-
"""Factos do AI Act Statement por deployment (19 Out 2026, próximo bump).

Protege-se: (1) a frota inteira, que não tem o bloco, continua a validar;
(2) o bloco é INTERNO — se alguém o expuser ao cliente sem decidir, falha;
(3) a data da triagem declara `format` (o Studio deriva o picker);
(4) só os dois valores por área do art. 5.º são aceites.
"""

import pytest
from pydantic import ValidationError

from genesis_profile_schema import exposure as exp
from genesis_profile_schema.client_profile_schema import (
    ClientProfileSchema,
    ProfileComplianceArt5Screening,
    ProfileComplianceStatement,
)


def test_perfil_sem_o_bloco_valida_com_defaults_vazios():
    p = ClientProfileSchema.model_validate({"compliance": {"sector": "saúde"}})
    st = p.compliance.statement
    assert st.intended_purpose == "" and st.out_of_scope_uses == []
    assert st.art50_4_relevance == "" and st.art5_screening.areas == {}


@pytest.mark.parametrize("path", [
    "compliance.statement.intended_purpose",
    "compliance.statement.dpa_ref",
    "compliance.statement.art5_screening.areas",
    "compliance.statement.art5_screening.reviewer",
])
def test_bloco_e_interno(path):
    assert not exp.is_client_visible(path)


def test_data_da_triagem_declara_formato():
    js = ProfileComplianceArt5Screening.model_json_schema()
    assert js["properties"]["screened_at"].get("format") == "date"


def test_area_do_art5_so_aceita_os_dois_resultados():
    ProfileComplianceArt5Screening(areas={"social_scoring": "not_identified"})
    with pytest.raises(ValidationError):
        ProfileComplianceArt5Screening(areas={"social_scoring": "talvez"})


def test_relevancia_50_4_fechada():
    with pytest.raises(ValidationError):
        ProfileComplianceStatement(art50_4_relevance="sim")
