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


# ─── v0.1.68: campos jurídicos (nota de 22 Set 2026, §12-13) ────────────────

CAMINHOS_068 = [
    "compliance.config_variations.config_version_assessed",
    "compliance.config_variations.change_ref",
    "compliance.config_variations.materiality",
    "compliance.config_variations.legal_rationale",
    "compliance.config_variations.controls_impacted",
    "compliance.config_variations.evidence_refs",
    "compliance.config_variations.required_actions.action",
    "compliance.config_variations.required_actions.owner",
    "compliance.config_variations.required_actions.done",
    "compliance.config_variations.reassessment_triggers",
    "compliance.config_variations.reassessment_notes",
]


def test_entrada_da_v065_continua_a_carregar_sem_os_campos_novos():
    """Os registos feitos com a v0.1.65 não têm nada disto."""
    v = ProfileComplianceConfigVariation.model_validate({"capability": "tabular", "purpose": "x"})
    assert v.materiality == "" and v.controls_impacted == [] and v.required_actions == []


def test_entrada_completa_da_v068():
    v = ProfileComplianceConfigVariation.model_validate({
        "capability": "consulta analítica tabular",
        "config_version_assessed": "v42", "change_ref": "CV-2026-09-22-001",
        "materiality": "no_material_change",
        "legal_rationale": "capacidade do catálogo comum; sem mudança de finalidade",
        "controls_impacted": ["technical_docs", "art50_transparency"],
        "evidence_refs": ["https://x/nota.pdf"],
        "required_actions": [{"action": "atualizar o Anexo IV", "owner": "Bruno", "done": False}],
        "reassessment_triggers": ["model_change", "new_personal_data_category"],
    })
    assert v.required_actions[0].owner == "Bruno"
    assert "model_change" in v.reassessment_triggers


@pytest.mark.parametrize("campo,valor", [
    ("materiality", "talvez"),
    ("controls_impacted", ["inventado"]),
    ("reassessment_triggers", ["qualquer"]),
])
def test_vocabularios_fechados(campo, valor):
    """Campos novos, sem valores históricos: aqui o vocabulário fechado não
    impede ninguém de carregar e evita que o Anexo IV mostre um código cru."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ProfileComplianceConfigVariation.model_validate({campo: valor})


@pytest.mark.parametrize("caminho", CAMINHOS_068)
def test_campos_juridicos_sao_internos(caminho):
    assert exp.exposure_of(caminho) == exp.INTERNAL


@pytest.mark.parametrize("caminho", [
    "compliance.config_variations.controls_impacted",
    "compliance.config_variations.reassessment_triggers",
])
def test_listas_fechadas_sao_escolha_multipla(caminho):
    from genesis_profile_schema.presentation import collection_of, control_for
    assert control_for(caminho) == "select" and collection_of(caminho) == "list"


# ─── v0.1.68: responsável pelo tratamento (nota de 21 Set 2026, §10) ───────

def test_bloco_de_direitos_existe_vazio_por_defeito():
    p = ClientProfileSchema.model_validate({"client_id": "acme"})
    d = p.compliance.data_subject_rights
    assert d.controller_name == "" and d.request_channel == "" and d.dpo_contact == ""


@pytest.mark.parametrize("caminho", [
    "compliance.data_subject_rights.controller_name",
    "compliance.data_subject_rights.request_channel",
    "compliance.data_subject_rights.dpo_contact",
])
def test_direitos_sao_do_cliente(caminho):
    """O responsável pelo tratamento é o cliente — é a ele que cabe mantê-lo."""
    assert exp.exposure_of(caminho) == exp.CLIENT_WRITE


def test_canal_nao_e_validado_no_modelo():
    """Um valor mal formado tem de continuar a CARREGAR (o mesmo modelo serve
    o bot); quem o recusa é o core ao mostrá-lo, não o schema ao ler."""
    p = ClientProfileSchema.model_validate(
        {"client_id": "a", "compliance": {"data_subject_rights": {"request_channel": "javascript:x"}}})
    assert p.compliance.data_subject_rights.request_channel == "javascript:x"
