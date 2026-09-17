# -*- coding: utf-8 -*-
"""Registo de variações materiais de configuração (v0.1.65, 17 Set 2026).

Nasce da nota jurídica complementar de 14 Set 2026: um deployment com uma
capacidade que o resto da frota não tem continua a ser o MESMO AI system, mas
a variação tem de ficar registada — capacidade, quando, finalidade, se altera
a finalidade prevista ou a classificação, o que trouxe de novo, e quem reviu.

O que estes testes protegem, por ordem de importância:
  1. um perfil que nunca ouviu falar do bloco continua a validar (a frota
     inteira está nesse caso);
  2. o registo é INTERNO — é a nossa avaliação de continuidade, não um painel
     do cliente. Se algum dia alguém o expuser sem decidir, o teste falha;
  3. as datas declaram `format`, porque é daí que o Studio deriva o picker.
"""

import pytest

from genesis_profile_schema import exposure as exp
from genesis_profile_schema.client_profile_schema import (
    ClientProfileSchema,
    ProfileCompliance,
    ProfileComplianceConfigVariation,
)

CAMINHOS = [
    "compliance.config_variations.capability",
    "compliance.config_variations.activated_at",
    "compliance.config_variations.purpose",
    "compliance.config_variations.changes_intended_purpose",
    "compliance.config_variations.changes_risk_classification",
    "compliance.config_variations.new_models_or_data",
    "compliance.config_variations.reviewed_by",
    "compliance.config_variations.reviewed_at",
    "compliance.config_variations.notes",
]


def test_default_e_lista_vazia():
    """Sem variações declaradas, o deployment está alinhado com o comum — que
    é o caso da esmagadora maioria da frota."""
    assert ProfileCompliance().config_variations == []


def test_perfil_sem_o_bloco_continua_a_validar():
    p = ClientProfileSchema.model_validate({"client_id": "acme"})
    assert p.compliance.config_variations == []


def test_uma_variacao_completa_carrega():
    v = ProfileComplianceConfigVariation.model_validate({
        "capability": "consulta analítica sobre dados tabulares",
        "activated_at": "2026-08-14",
        "purpose": "responder a perguntas sobre os mapas de exploração do cliente",
        "changes_intended_purpose": False,
        "changes_risk_classification": False,
        "new_models_or_data": "",
        "reviewed_by": "compliance@genesisdigitalsolutions.pt",
        "reviewed_at": "2026-09-17",
        "notes": "capacidade do catálogo comum, ativada por configuração",
    })
    assert v.capability.startswith("consulta")
    assert v.changes_intended_purpose is False


def test_chaves_desconhecidas_sobrevivem():
    """`extra=allow` em todo o schema: um campo que o jurista peça amanhã não
    se perde ao passar por uma versão antiga do pacote."""
    v = ProfileComplianceConfigVariation.model_validate(
        {"capability": "x", "dpa_clause": "6.6"}
    )
    assert v.model_dump().get("dpa_clause") == "6.6"


@pytest.mark.parametrize("caminho", CAMINHOS)
def test_o_registo_e_interno(caminho):
    assert exp.exposure_of(caminho) == exp.INTERNAL, (
        f"'{caminho}' deixou de ser interno. O registo de variações é a nossa "
        "avaliação de continuidade do sistema (inclui quem reviu e notas de "
        "dossier); ao deployer chega pela documentação Anexo IV, não por um "
        "painel editável."
    )


@pytest.mark.parametrize("campo,formato", [
    ("activated_at", "date"),
    ("reviewed_at", "date"),
])
def test_as_datas_declaram_formato(campo, formato):
    """O Studio e o backoffice derivam o controlo do `format`."""
    esquema = ProfileComplianceConfigVariation.model_json_schema()
    assert esquema["properties"][campo].get("format") == formato


def test_a_anotacao_de_formato_nao_valida_a_data():
    """Coerente com o resto do schema: o picker previne para a frente, mas um
    valor histórico imperfeito tem de continuar a carregar — o perfil que
    valida é o MESMO que serve o bot."""
    v = ProfileComplianceConfigVariation.model_validate({"activated_at": "ago/2026"})
    assert v.activated_at == "ago/2026"
