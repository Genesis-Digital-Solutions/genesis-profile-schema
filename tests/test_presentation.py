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
])
def test_casos_conhecidos(path, esperado):
    assert pr.control_for(path) == esperado


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


def test_a_tabela_nao_repete_o_que_o_schema_ja_diz():
    """Nenhum override pode estar a dizer o mesmo que a derivação já daria —
    se estiver, é uma linha a manter à mão sem necessidade."""
    formas = exp.leaf_shapes()
    redundantes = []
    for path, controlo in pr.CONTROL_OVERRIDES.items():
        forma = formas.get(path)
        if not forma:
            continue                      # dentro de mapa aberto: não deriva
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
