"""
Gate das verificações de valor (`genesis_profile_schema/field_checks.py`).

O caso que deu origem a isto está no primeiro teste: os valores destes campos
são interpolados literalmente numa directiva do CSP, e um `;` fecha a
directiva e abre outra.
"""

import pytest

from genesis_profile_schema import field_checks as fc


# ─────────────────────────────────────────────────────────────────────────────
# Origens do CSP
# ─────────────────────────────────────────────────────────────────────────────

VALIDAS = [
    "https://www.cliente.pt",
    "http://intranet.cliente.local",
    "https://*.cliente.pt",
    "https://cliente.pt:8443",
    "cliente.pt",
    "https://cliente.pt/",
    "localhost:4200",
    "https://sub.dominio.cliente.co.uk",
    "https://xn--mnchen-3ya.de",          # IDN em punycode, como o CSP exige
    # Casos que a primeira versao deste validador recusava, e que existem na
    # frota. Recusa-los tirava a um site a autorizacao de embeber que tinha.
    "https://site.pt/embed",              # URL completo com caminho
    "https://site.pt/embed/widget",
    "https://intranet",                   # host de rotulo unico COM esquema
    "https://portal_interno.cliente.pt",  # underscore no host
    "https://192.168.1.10:8080",
]

INVALIDAS = [
    "https://evil.com; script-src 'unsafe-inline' *",   # a injecção
    "'self'",
    "'unsafe-inline'",
    "*",
    "data:",
    "blob:",
    "javascript:alert(1)",
    "https://evil.com;",
    'https://evil.com"',
    "https://münchen.de",                 # IDN por converter
    "",
    "   ",
    # Continua a recusar o que nao tem esquema NEM ponto — e o que impede
    # os tokens de uma injeccao de passarem por hosts.
    "script-src",
    "unsafe-inline",
    "intranet",
    "https://evil.com/a;b",               # caminho nao serve de veiculo
]


@pytest.mark.parametrize("origem", VALIDAS)
def test_origens_legitimas_passam(origem):
    assert fc.is_valid_csp_source(origem), origem


@pytest.mark.parametrize("origem", INVALIDAS)
def test_origens_perigosas_ou_malformadas_nao_passam(origem):
    assert not fc.is_valid_csp_source(origem), origem


def test_a_injeccao_de_csp_e_neutralizada():
    """O caso real: um valor no perfil que reescrevia o script-src da app."""
    aceites, recusados = fc.sanitise_csp_sources(
        ["https://www.cliente.pt", "https://evil.com; script-src 'unsafe-inline' *"]
    )
    assert aceites == ["https://www.cliente.pt"]
    assert recusados, "a entrada maliciosa tem de ser reportada, não engolida"
    assert not any(";" in a or "'" in a for a in aceites)


def test_entrada_com_varias_origens_e_dividida_nao_deitada_fora():
    """Hoje uma entrada assim funciona por acidente. Recusá-la em bloco
    tirava a um site a autorização de embeber que ele já tinha."""
    aceites, recusados = fc.sanitise_csp_sources(["https://a.pt https://b.pt"])
    assert aceites == ["https://a.pt", "https://b.pt"]
    assert recusados == []


def test_barra_final_e_repeticoes_desaparecem():
    aceites, _ = fc.sanitise_csp_sources(
        ["https://a.pt/", "https://a.pt", "  https://b.pt  "]
    )
    assert aceites == ["https://a.pt", "https://b.pt"]


def test_lista_vazia_ou_lixo_nao_rebenta():
    assert fc.sanitise_csp_sources(None) == ([], [])
    assert fc.sanitise_csp_sources([]) == ([], [])
    aceites, recusados = fc.sanitise_csp_sources([None, 123, {"a": 1}])
    assert aceites == []
    assert len(recusados) == 3


# ─────────────────────────────────────────────────────────────────────────────
# Regex do cliente
# ─────────────────────────────────────────────────────────────────────────────

def test_regex_saudavel_nao_da_aviso():
    for pattern in (r"\bOT-\d{4,}\b", r"[A-Z]{2,3}\d{3,6}", r"REF[-_]?\d+"):
        assert fc.regex_risk(pattern) is None, pattern


def test_regex_que_nao_compila_e_apanhada():
    motivo = fc.regex_risk(r"[A-Z")
    assert motivo and "não compila" in motivo


def test_quantificador_encaixado_e_apanhado():
    for pattern in (r"(a+)+$", r"(\d*)*", r"(a|a)+"):
        assert fc.regex_risk(pattern), pattern


def test_regex_vazia_e_apanhada():
    assert fc.regex_risk("")
    assert fc.regex_risk("   ")


def test_regex_risks_devolve_so_os_problematicos():
    problemas = fc.regex_risks([r"\bOT-\d+\b", r"(a+)+", r"[A-Z"])
    assert len(problemas) == 2
    assert all(isinstance(p, tuple) and len(p) == 2 for p in problemas)


def test_limite_de_comprimento_e_generoso():
    """A regra da casa é que limites só sobem. Se alguém apertar isto para
    'poupar', este teste chumba."""
    assert fc.REGEX_LENGTH_WARN >= 500
    assert fc.regex_risk("a" * 400) is None


# ─────────────────────────────────────────────────────────────────────────────
# Códigos de língua
# ─────────────────────────────────────────────────────────────────────────────

def test_etiquetas_bem_formadas():
    for tag in ("pt", "pt-PT", "en", "en-GB", "zh-Hant", "zh-Hant-TW", "es-419"):
        assert fc.looks_like_language_tag(tag), tag


def test_os_typos_do_pedido_do_backoffice_sao_apanhados():
    for tag in ("pt_PT", "portugues", "PT-PT-PT", "", "   ", "*"):
        assert not fc.looks_like_language_tag(tag), tag
    # `PT-PT` maiúsculo é forma válida de BCP-47 (a norma é case-insensitive).
    assert fc.looks_like_language_tag("PT-PT")


def test_asterisco_e_legitimo_em_allowed():
    assert fc.language_tag_problems(["*"]) == []
    assert fc.language_tag_problems(["pt-PT", "en", "*"]) == []
    assert fc.language_tag_problems(["pt-PT", "pt_BR"]) == ["pt_BR"]


def test_a_frase_do_fallback_nao_e_um_codigo():
    """Prova de que esta função não serve para `language.fallback`: o default
    do próprio schema é uma frase, e seria rejeitado."""
    from genesis_profile_schema.client_profile_schema import ProfileLanguage

    default = ProfileLanguage().fallback
    assert " " in default, "o default deixou de ser uma frase — rever esta decisão"
    assert not fc.looks_like_language_tag(default)


def test_sugestoes_batem_certo_com_as_vozes_de_fabrica():
    """As sugestões não podem divergir dos locales para que o produto já traz
    voz — se as vozes mudarem, isto chumba em vez de envelhecer em silêncio."""
    from genesis_profile_schema.client_profile_schema import ProfileVoices

    assert set(fc.SUGGESTED_LOCALES) == set(ProfileVoices().by_locale)


def test_o_caminho_nao_abre_porta_a_injeccao():
    """Aceitar caminhos foi para nao perder origens legitimas. O `;` continua
    barrado antes de a gramatica ser consultada."""
    aceites, recusados = fc.sanitise_csp_sources(
        ["https://site.pt/embed", "https://evil.pt/x; script-src 'unsafe-inline'"]
    )
    assert aceites == ["https://site.pt/embed"]
    assert recusados
