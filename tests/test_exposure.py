"""
Gate da tabela de exposição (`genesis_profile_schema/exposure.py`).

O que estes testes garantem não é que a classificação esteja CERTA — isso
decide-se campo a campo, com o produto à frente. Garantem que:
  - nenhum campo do schema escapa à decisão (é o inverso do modo de falha que
    a allowlist-por-área tinha: campo novo em área permitida nascia exposto);
  - a tabela não acumula entradas mortas quando um campo desaparece;
  - as decisões de SEGURANÇA não podem ser invertidas por distração — estão
    escritas aqui, uma a uma, com o motivo.
"""

import pytest

from genesis_profile_schema import exposure as exp


def test_toda_a_folha_do_schema_esta_classificada():
    faltam = exp.unclassified_paths()
    assert faltam == (), (
        f"{len(faltam)} campo(s) do schema sem entrada em EXPOSURE: {faltam}. "
        "Um campo novo não pode nascer sem decisão — classifica-o (o default "
        "de runtime é 'internal', mas a decisão fica registada na tabela)."
    )


def test_tabela_sem_entradas_mortas():
    orfas = exp.orphan_entries()
    assert orfas == (), (
        f"entrada(s) em EXPOSURE que já não existem no schema: {orfas}"
    )


def test_niveis_validos():
    invalidos = {p: lvl for p, lvl in exp.EXPOSURE.items() if lvl not in exp.LEVELS}
    assert invalidos == {}


def test_default_e_internal_para_caminho_desconhecido():
    assert exp.exposure_of("area.que.nao.existe") == exp.INTERNAL
    assert exp.exposure_of("") == exp.INTERNAL
    assert not exp.is_client_visible("area.que.nao.existe")


def test_indices_e_marcadores_de_lista_sao_normalizados():
    assert exp.normalise_path("retrieval.indexes.0.name") == "retrieval.indexes.name"
    assert exp.normalise_path("retrieval.indexes[].name") == "retrieval.indexes.name"
    assert exp.exposure_of("retrieval.indexes.3.weight") == exp.INTERNAL


def test_conteudo_de_mapa_aberto_herda_o_nivel_do_mapa():
    # `personality.tone_instructions` é um mapa interno: as chaves lá dentro
    # (uma por tom) não podem ficar editáveis por não estarem na tabela.
    assert exp.exposure_of("personality.tone_instructions") == exp.INTERNAL
    assert exp.exposure_of("personality.tone_instructions.professional") == exp.INTERNAL
    # …e um mapa do cliente propaga-se na direcção oposta.
    assert exp.exposure_of("frontend.welcomeMessage") == exp.CLIENT_WRITE
    assert exp.exposure_of("frontend.welcomeMessage.pt") == exp.CLIENT_WRITE


def test_excepcao_exacta_ganha_ao_mapa_que_a_contem():
    assert exp.exposure_of("tools.config") == exp.INTERNAL
    assert exp.exposure_of("tools.config.generate_boq.rates.price") == exp.CLIENT_WRITE
    # A captura de contactos fica de fora da excepção, de propósito.
    assert exp.exposure_of("tools.config.record_contact_details.notify_emails") == exp.INTERNAL
    assert exp.exposure_of("tools.config.record_contact_details.legal_basis") == exp.INTERNAL


# ─────────────────────────────────────────────────────────────────────────────
# Invariantes de segurança — cada linha com o motivo pelo qual não se inverte
# ─────────────────────────────────────────────────────────────────────────────

NUNCA_VISIVEL = [
    ("frontend.csp.extraScriptSrc", "acrescentar origem a script-src = XSS persistente na página de chat"),
    ("frontend.csp.extraConnectSrc", "destino de exfiltração via fetch/XHR"),
    ("frontend.csp.extraFrameSrc", "enquadramento de terceiros na página do cliente"),
    ("frontend.csp.extraImgSrc", "canal de exfiltração por URL de imagem"),
    ("frontend.csp.extraStyleSrc", "injecção de CSS de terceiros"),
    ("frontend.auth.clientId", "identidade da app"),
    ("frontend.auth.tenantId", "identidade do tenant"),
    ("frontend.auth.widget_identity.secret_ref", "referência a segredo"),
    ("frontend.auth.providers.jwks_uri", "trocar o JWKS é trocar quem assina os tokens aceites"),
    ("mcp.servers.auth.token", "credencial de saída"),
    ("mcp.servers.auth.client_secret", "credencial de saída"),
    ("mcp.servers.trusted", "decide se uma tool externa corre sem confirmação"),
    ("mcp.servers.url", "destino das chamadas MCP (SSRF)"),
    ("retrieval.search_index_names", "repontar o bot para outro índice do serviço de pesquisa"),
    ("retrieval.min_score", "piso de relevância: baixá-lo alimenta o modelo com lixo"),
    ("retrieval.weak_grounding_ceiling", "tecto de grounding fraco — protecção anti-invenção"),
    ("retrieval.refuse_pregen_min_score", "limiar de recusa antes de gerar — protecção anti-invenção"),
    ("retrieval.faithfulness_overlap_skip", "quando o juiz de fidelidade é dispensado"),
    ("runtime.agent_model", "escolha de modelo = custo e qualidade da frota"),
    ("runtime.internal_model", "idem, no modelo interno"),
    ("pricing.usd_to_eur", "estrutura de custo da Genesis"),
    ("pricing.models", "estrutura de custo da Genesis"),
    ("frontend.llmModels", "ids provider:model:mode — escolha de modelo pelo utilizador final"),
    ("ingest.sources", "wiring de containers de blob"),
    ("contacts.attribute_paths", "wiring de identidade/CRM"),
]


@pytest.mark.parametrize("path,motivo", NUNCA_VISIVEL, ids=[p for p, _ in NUNCA_VISIVEL])
def test_caminhos_que_nunca_podem_ficar_visiveis(path, motivo):
    assert exp.exposure_of(path) == exp.INTERNAL, (
        f"'{path}' passou a estar visível ao cliente. Motivo pelo qual não pode: {motivo}. "
        "Se a decisão mudou mesmo, muda esta lista no mesmo commit e explica porquê."
    )


NUNCA_ESCRITO_PELO_CLIENTE = [
    ("guardrails.allow_general_knowledge", "desliga o grounded-only; é a origem do trabalho anti-invenção"),
    ("guardrails.citation_support_warning", "decide se o aviso de alucinação chega ao utilizador final"),
    ("frontend.aiDisclosure.enabled", "divulgação obrigatória (AI Act Art. 50)"),
    ("voice.aiDisclosure", "divulgação obrigatória no canal de voz (AI Act Art. 50)"),
    ("compliance.classification.risk_level", "a classificação de risco é do provider, não do deployer"),
    ("compliance.classification.classified_by", "proveniência da classificação"),
    ("compliance.classification.classified_at", "proveniência da classificação"),
    ("compliance.annex_iv_doc_url", "documentação técnica gerada pela Genesis"),
    ("tools.enabled", "escopo contratado, não preferência de UI"),
    ("guestAccess.rateLimits.perDay", "limite de abuso definido pela Genesis"),
    ("language.fallback", "é o NOME CANÓNICO que vai como instrução ao modelo, não um código ISO: "
                          "um \"pt-PT\" escrito pelo cliente dá instrução pior e iso_code vazio, em silêncio"),
]


@pytest.mark.parametrize(
    "path,motivo", NUNCA_ESCRITO_PELO_CLIENTE, ids=[p for p, _ in NUNCA_ESCRITO_PELO_CLIENTE]
)
def test_caminhos_que_o_cliente_ve_mas_nao_escreve(path, motivo):
    assert exp.exposure_of(path) == exp.CLIENT_READ, (
        f"'{path}' devia ser client_read (é {exp.exposure_of(path)}). Motivo: {motivo}."
    )


def test_areas_inteiramente_internas():
    """Áreas onde nem um campo pode escapar — verificado contra o schema real,
    não contra a tabela, para apanhar um campo novo que lá entre."""
    for area in ("retrieval", "mcp", "runtime", "pricing", "query_cache", "contacts"):
        expostos = [
            p for p in exp.leaf_paths()
            if p.split(".")[0] == area and exp.exposure_of(p) != exp.INTERNAL
        ]
        assert expostos == [], f"área '{area}' devia ser inteiramente interna; expostos: {expostos}"


def test_frontend_csp_e_auth_inteiros():
    for prefixo in ("frontend.csp.", "frontend.auth."):
        expostos = [
            p for p in exp.leaf_paths()
            if p.startswith(prefixo) and exp.exposure_of(p) != exp.INTERNAL
        ]
        assert expostos == [], f"'{prefixo}*' devia ser interno; expostos: {expostos}"


# ─────────────────────────────────────────────────────────────────────────────
# Campos sem consumidor
# ─────────────────────────────────────────────────────────────────────────────

CAMPOS_SEM_CONSUMIDOR = [
    ("identity.default_language",
     "DEPRECADO: nada o lê. A língua da resposta vem de language.strategy/allowed/fallback "
     "e a da interface de frontend.language.default. Ligar um terceiro campo criava "
     "ambiguidade sobre qual ganha."),
]


@pytest.mark.parametrize("path,motivo", CAMPOS_SEM_CONSUMIDOR,
                         ids=[p for p, _ in CAMPOS_SEM_CONSUMIDOR])
def test_campo_sem_consumidor_fica_escondido(path, motivo):
    """Um campo editável que não faz nada é pior do que um campo ausente: o
    cliente muda-o, acredita que mudou algo, e o suporte descobre meses
    depois. Motivo por campo: """
    assert exp.exposure_of(path) == exp.INTERNAL, (
        f"'{path}' voltou a estar visível. {motivo}"
    )


def test_o_campo_deprecado_esta_marcado_no_proprio_schema():
    """A marca tem de estar onde um consumidor que só lê JSON Schema a veja —
    não só num comentário que ninguém importa."""
    from genesis_profile_schema.client_profile_schema import ClientProfileSchema

    js = ClientProfileSchema.model_json_schema()
    campo = js["$defs"]["ProfileIdentity"]["properties"]["default_language"]
    assert campo.get("deprecated") is True, campo
