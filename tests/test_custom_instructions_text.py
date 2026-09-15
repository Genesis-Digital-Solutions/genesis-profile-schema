"""
Gate da separação playbook/cliente em `custom_instructions`.

Os cabeçalhos abaixo são os QUATRO reais de `core/agent/mcp/templates.py`
(Set 2026). Se o core criar uma família nova com outro formato de marcador,
este ficheiro é o primeiro a saber.
"""

from genesis_profile_schema import custom_instructions_text as ct

HEADERS = (
    "## Dados financeiros (ERP) [genesis-mcp-playbook-v1]",
    "## Encomendas & clientes (ERP SAP) [genesis-mcp-sap-playbook-v1]",
    "## Base de dados do cliente (Cosmos DB) [genesis-mcp-cosmos-playbook-v3]",
    "## Folhas de cálculo consultáveis (Tabular) [genesis-mcp-tabular-playbook-v8]",
)


def _playbook(header: str) -> str:
    return (
        f"{header}\n"
        "Quando o utilizador perguntar por números:\n"
        "### Regras\n"
        "- chama a tool `db_query` com o filtro certo\n"
        "- nunca listes linhas para as somar tu\n"
    )


def test_vazio_e_nao_string():
    assert ct.split_playbook_blocks("") == {"playbook_blocks": [], "client_text": ""}
    assert ct.split_playbook_blocks(None) == {"playbook_blocks": [], "client_text": ""}


def test_sem_marcador_tudo_e_do_cliente():
    txt = "<regras>\nNão respondas sobre concorrentes.\n</regras>"
    r = ct.split_playbook_blocks(txt)
    assert r["playbook_blocks"] == []
    assert r["client_text"] == txt


def test_os_quatro_cabecalhos_reais_sao_reconhecidos():
    for h in HEADERS:
        r = ct.split_playbook_blocks(_playbook(h))
        assert len(r["playbook_blocks"]) == 1, h
        b = r["playbook_blocks"][0]
        assert b["family"].endswith("playbook")
        assert b["marker"] in h
        assert b["text"].startswith(h)
        assert "db_query" in b["text"]
        assert r["client_text"] == ""


def test_familia_e_versao_separadas():
    r = ct.split_playbook_blocks(_playbook(HEADERS[3]))
    b = r["playbook_blocks"][0]
    assert b["family"] == "genesis-mcp-tabular-playbook"
    assert b["version"] == 8
    assert b["marker"] == "[genesis-mcp-tabular-playbook-v8]"


def test_familia_xero_sem_segmento_do_meio():
    b = ct.split_playbook_blocks(_playbook(HEADERS[0]))["playbook_blocks"][0]
    assert b["family"] == "genesis-mcp-playbook"
    assert b["version"] == 1


def test_texto_do_cliente_antes_e_depois_sobrevive():
    antes = "<regras>\nSê breve.\n</regras>"
    depois = "Encaminha reclamações para apoio@cliente.pt."
    txt = f"{antes}\n\n{_playbook(HEADERS[3])}\n\n{depois}"
    r = ct.split_playbook_blocks(txt)
    assert len(r["playbook_blocks"]) == 1
    assert r["client_text"] == f"{antes}\n\n{depois}"
    assert "db_query" not in r["client_text"]


def test_cabecalho_h2_do_cliente_fecha_o_bloco():
    txt = _playbook(HEADERS[2]) + "## Famílias documentais\nA mais recente pelo ano no nome.\n"
    r = ct.split_playbook_blocks(txt)
    assert "Famílias documentais" not in r["playbook_blocks"][0]["text"]
    assert r["client_text"].startswith("## Famílias documentais")


def test_linha_em_branco_fecha_o_bloco_texto_do_cliente_por_baixo():
    """O mcp_console cola o playbook no FIM do campo com uma linha em branco;
    o que o operador escrever por baixo, sem cabeçalho, tem de voltar ao cliente."""
    txt = _playbook(HEADERS[3]) + "\nEncaminha reclamações para apoio@cliente.pt.\n"
    r = ct.split_playbook_blocks(txt)
    assert "apoio@cliente.pt" not in r["playbook_blocks"][0]["text"]
    assert r["client_text"] == "Encaminha reclamações para apoio@cliente.pt."


def test_h3_interno_nao_fecha_o_bloco():
    r = ct.split_playbook_blocks(_playbook(HEADERS[1]))
    assert "### Regras" in r["playbook_blocks"][0]["text"]


def test_dois_playbooks_de_familias_diferentes():
    txt = _playbook(HEADERS[2]) + "\n" + _playbook(HEADERS[3])
    r = ct.split_playbook_blocks(txt)
    assert [b["family"] for b in r["playbook_blocks"]] == [
        "genesis-mcp-cosmos-playbook", "genesis-mcp-tabular-playbook",
    ]
    assert ct.duplicate_playbook_families(txt) == []


def test_familia_duplicada_e_detectada():
    v7 = HEADERS[3].replace("-v8]", "-v7]")
    txt = _playbook(v7) + "\n" + _playbook(HEADERS[3])
    assert ct.playbook_families(txt) == ["genesis-mcp-tabular-playbook"] * 2
    assert ct.duplicate_playbook_families(txt) == ["genesis-mcp-tabular-playbook"]


def test_marcador_no_meio_de_uma_linha_normal_nao_conta():
    txt = "Nota: o playbook [genesis-mcp-tabular-playbook-v8] foi removido.\n"
    r = ct.split_playbook_blocks(txt)
    assert r["playbook_blocks"] == []
    assert r["client_text"] == txt.strip()
