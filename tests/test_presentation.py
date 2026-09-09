"""
Gate dos controlos (`genesis_profile_schema/presentation.py`).

O que se protege aqui é a promessa de que a tabela é PEQUENA: tudo o que o
schema consegue dizer sozinho tem de continuar a ser derivado. Uma tabela que
comece a repetir o que já está no contrato volta a ser a segunda fonte que
envelhece.
"""

import pytest

from genesis_profile_schema import exposure as exp
from genesis_profile_schema import presentation as pr
from genesis_profile_schema import ui_text as ui


def _formas():
    """As formas que a derivação vê: o perfil E os blocos tipados de `tools.config`."""
    return {**exp.tool_config_shapes(), **exp.leaf_shapes()}


def test_tabela_sem_entradas_mortas():
    assert pr.orphan_overrides() == ()


def test_controlos_declarados_sao_dos_conhecidos():
    maus = {p: c for p, c in pr.CONTROL_OVERRIDES.items() if c not in pr.CONTROLS}
    assert maus == {}


def test_toda_a_folha_tem_um_controlo_conhecido():
    for path in exp.leaf_paths():
        assert pr.control_for(path) in pr.CONTROLS, path


def test_caminho_desconhecido_cai_em_texto():
    assert pr.control_for("area.que.nao.existe") == pr.TEXT
    assert pr.control_for("") == pr.TEXT
    assert pr.collection_of("area.que.nao.existe") is None


@pytest.mark.parametrize("path,esperado", [
    ("response.show_sources", pr.TOGGLE),
    ("response.followup_count", pr.NUMBER),
    ("retrieval.min_score", pr.NUMBER),
    ("identity.register", pr.SELECT),
    ("brand_safety.level", pr.SELECT),
    ("frontend.branding.primaryColor", pr.COLOUR),
    ("frontend.branding.theme.dark.bgPage", pr.COLOUR),
    ("identity.company_name", pr.TEXT),
    ("custom_instructions", pr.MULTILINE),
    ("product_identification.patterns", pr.CODE),
    ("identity.logo_url", pr.URL),
    ("ingest.alerts.email", pr.EMAIL),
    ("compliance.classification.classified_at", pr.DATETIME),
    ("compliance.classification.next_review_due", pr.DATE),
    # Nome de um preset (issue #6 do gaibo): texto livre com sugestões, não prosa.
    ("tools.config.generate_boq.prompt_preset", pr.COMBOBOX),
    ("tools.config.extract_legal_terms.prompt_preset", pr.COMBOBOX),
    # Lista fechada que o schema tipa como `str` — o espaço é `UI_LANGS`.
    ("frontend.language.default", pr.SELECT),
    ("frontend.language.enabled", pr.SELECT),
    # Dentro de `tools.config`: derivado do modelo tipado do bloco, sem linha na tabela.
    ("tools.config.search_web.mode", pr.SELECT),
    ("tools.config.record_contact_details.legal_basis", pr.SELECT),
    ("tools.config.record_contact_details.notify_on_capture", pr.TOGGLE),
    ("tools.config.record_contact_details.retention_days", pr.NUMBER),
    ("tools.config.generate_boq.rates.price", pr.NUMBER),
])
def test_casos_conhecidos(path, esperado):
    assert pr.control_for(path) == esperado


def test_prompt_preset_deixou_de_ser_prosa():
    """Até à v0.1.59 os dois `prompt_preset` estavam na secção "prosa" da tabela
    e `control_for` mandava desenhar uma textarea para o nome de um preset.
    O teste nomeia o caso para o erro não voltar por um copy-paste do vizinho
    `prompt_custom`, que É prosa."""
    for tool in ("generate_boq", "extract_legal_terms"):
        assert pr.control_for(f"tools.config.{tool}.prompt_preset") == pr.COMBOBOX
        assert pr.control_for(f"tools.config.{tool}.prompt_custom") == pr.MULTILINE


@pytest.mark.parametrize("locale", ui.LOCALES)
def test_combobox_tem_sugestoes_nomeadas_e_nao_e_lista_fechada(locale):
    """Um `combobox` sem sugestões é uma caixa de texto com outro nome; um
    `combobox` sobre um `enum` devia ser `select`. As duas metades da promessa,
    nas duas línguas."""
    formas = _formas()
    comboboxes = [p for p, c in pr.CONTROL_OVERRIDES.items() if c == pr.COMBOBOX]
    assert comboboxes, "a tabela deixou de ter comboboxes — o teste ficou sem objecto"
    for path in comboboxes:
        assert (formas.get(path) or {}).get("enum") is None, f"{path} é enum: devia ser select"
        sugestoes = ui.options_of(path, locale)
        assert sugestoes, f"{path} é combobox sem sugestões em {locale}"
        assert all(nome.strip() for nome in sugestoes.values()), path


@pytest.mark.parametrize("locale", ui.LOCALES)
def test_valores_nomeados_implicam_um_controlo_de_escolha(locale):
    """A regra que teria apanhado o issue #6 sozinha: se o catálogo de texto
    nomeia os valores de um campo, o controlo desse campo tem de ser uma
    escolha — `select` (fechado) ou `combobox` (com texto livre). Uma textarea
    ou uma caixa de texto por cima de valores nomeados é a classificação a
    dizer uma coisa e o catálogo outra."""
    desalinhados = {
        path: pr.control_for(path)
        for path, rec in ui.catalogue(locale).items()
        if rec.get("options") and pr.control_for(path) not in (pr.SELECT, pr.COMBOBOX)
    }
    assert desalinhados == {}, f"valores nomeados sem controlo de escolha em {locale}: {desalinhados}"


def test_dentro_de_tools_config_deriva_se_sem_tabela():
    """Os blocos tipados de `tools.config` dizem sozinhos o que são as suas
    folhas; escrevê-las na tabela seria repetir o modelo."""
    formas = exp.tool_config_shapes()
    assert formas, "tool_config_shapes() vazio — a travessia dos blocos tipados partiu"
    enums = [p for p, f in formas.items() if f.get("enum")]
    assert "tools.config.search_web.mode" in enums
    for path in enums:
        assert path not in pr.CONTROL_OVERRIDES, f"{path} é enum do modelo: não precisa de linha"
        assert pr.control_for(path) == pr.SELECT, path
    # O mapa aberto continua a ser um mapa aberto: as folhas dos blocos não
    # passam a ser folhas do perfil (senão exigiam entrada em EXPOSURE).
    assert not any(p.startswith("tools.config.") for p in exp.leaf_paths())
    # E o que herda do vizinho continua a herdar — `rates` é lista de OBJECTOS,
    # não uma lista escalar: sem colecção, como antes.
    assert pr.collection_of("tools.config.generate_boq.rates") is None
    assert pr.collection_of("tools.config.search_web.allowed_domains") == pr.LIST


def test_o_container_e_uma_pergunta_separada_do_valor():
    """Uma lista de textos longos: controlo `multiline`, colecção `list`."""
    assert pr.control_for("system_prompt_disclaimers") == pr.MULTILINE
    assert pr.collection_of("system_prompt_disclaimers") == pr.LIST
    assert pr.control_for("personality.tone_instructions") == pr.MULTILINE
    assert pr.collection_of("personality.tone_instructions") == pr.MAP
    assert pr.collection_of("identity.company_name") is None


def test_lista_de_numeros_nao_e_lista_de_textos():
    assert pr.control_for("frontend.shareExpiryOptionsDays") == pr.NUMBER
    assert pr.collection_of("frontend.shareExpiryOptionsDays") == pr.LIST
    assert pr.control_for("guardrails.blocked_words") == pr.TEXT
    assert pr.collection_of("guardrails.blocked_words") == pr.LIST


def test_indices_normalizados():
    assert pr.control_for("retrieval.indexes.0.name") == pr.control_for("retrieval.indexes.name")


def test_conteudo_de_mapa_aberto_herda_o_controlo_do_mapa():
    assert pr.control_for("personality.tone_instructions.professional") == pr.MULTILINE
    assert pr.control_for("frontend.welcomeMessage.pt") == pr.MULTILINE
    assert pr.control_for("tools.config.generate_boq.prompt_custom") == pr.MULTILINE
    # Um bloco de `tools.config` SEM modelo tipado continua a cair no default.
    assert pr.control_for("tools.config.tool_que_nao_existe.campo") == pr.TEXT


def test_a_tabela_nao_repete_o_que_o_schema_ja_diz():
    """Nenhum override pode estar a dizer o mesmo que a derivação já daria —
    se estiver, é uma linha a manter à mão sem necessidade."""
    formas = _formas()
    redundantes = []
    for path, controlo in pr.CONTROL_OVERRIDES.items():
        forma = formas.get(path)
        if not forma:
            continue                      # dentro de mapa aberto sem modelo: não deriva
        if forma.get("enum") and controlo == pr.SELECT:
            redundantes.append(path)
        tipo = forma.get("items_type") if forma.get("type") == "array" else forma.get("type")
        if tipo == "boolean" and controlo == pr.TOGGLE:
            redundantes.append(path)
        if tipo in ("integer", "number") and controlo == pr.NUMBER:
            redundantes.append(path)
    assert redundantes == [], f"overrides que a derivação já dava: {redundantes}"


def test_as_cores_todas_derivam_sem_uma_linha_escrita():
    """57 campos de cor na v0.1.50, nenhum na tabela."""
    cores = [p for p in exp.leaf_paths() if pr.control_for(p) == pr.COLOUR]
    assert len(cores) >= 50
    assert not any(p in pr.CONTROL_OVERRIDES for p in cores)


def test_a_tabela_cobre_uma_minoria_dos_campos():
    """Se isto crescer para perto das 359, a derivação deixou de funcionar e
    alguém está a escrever à mão o que o contrato já diz."""
    assert len(pr.CONTROL_OVERRIDES) < len(exp.leaf_paths()) // 4
