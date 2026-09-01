# -*- coding: utf-8 -*-
"""
Invariantes dos espaços de valores das línguas.

O que estes testes existem para impedir não é uma gralha de escrita — é a
confusão entre os três espaços, que já custou um campo editável a pedir prosa
com cara de código (`language.fallback`, corrigido na v0.1.51).
"""

import pytest

from genesis_profile_schema.client_profile_schema import (
    ProfileFrontendLanguage,
    ProfileLanguage,
)
from genesis_profile_schema.field_checks import (
    SUGGESTED_LOCALES,
    language_tag_problems,
    looks_like_language_tag,
)
from genesis_profile_schema.languages import (
    ANY_LANGUAGE,
    CANONICAL_NAMES,
    CANONICAL_TO_ISO,
    ISO_TO_CANONICAL,
    LANGUAGE_CODES,
    RTL_UI_LANGS,
    UI_LANG_LOCALES,
    UI_LANGS,
    canonical_for,
    is_known_canonical_name,
    is_known_language_code,
    is_rtl_ui_lang,
    iso_for,
    normalise_ui_lang,
)
from genesis_profile_schema.ui_text import LOCALES, options_of


# ─────────────────────────────────────────────────────────────────────────────
# O mapa
# ─────────────────────────────────────────────────────────────────────────────

def test_a_inversao_nao_perde_nenhuma_lingua():
    """Dois códigos com o mesmo nome canónico e um deles desaparecia do
    CANONICAL_TO_ISO em silêncio — o core resolveria o ISO errado."""
    assert len(CANONICAL_TO_ISO) == len(ISO_TO_CANONICAL)
    assert len(set(ISO_TO_CANONICAL.values())) == len(ISO_TO_CANONICAL)


def test_as_tuplas_derivam_do_mapa():
    assert set(LANGUAGE_CODES) == set(ISO_TO_CANONICAL)
    assert set(CANONICAL_NAMES) == set(ISO_TO_CANONICAL.values())
    assert LANGUAGE_CODES == tuple(sorted(LANGUAGE_CODES))
    assert CANONICAL_NAMES == tuple(sorted(CANONICAL_NAMES))


def test_ida_e_volta_em_todas_as_entradas():
    for iso, canonical in ISO_TO_CANONICAL.items():
        assert canonical_for(iso) == canonical
        assert iso_for(canonical) == iso


@pytest.mark.parametrize("lixo", [None, 0, 1, [], {}, "", "   ", "nao-existe"])
def test_as_consultas_nunca_estouram_com_lixo(lixo):
    """Vêm de input externo (perfil no blob, formulário do backoffice)."""
    assert canonical_for(lixo) is None
    assert iso_for(lixo) is None
    assert is_known_language_code(lixo) is False
    assert is_known_canonical_name(lixo) is False
    assert normalise_ui_lang(lixo) == ""


# ─────────────────────────────────────────────────────────────────────────────
# Os defaults do contrato vivem dentro dos espaços de valores
#
# Este é o bloco que interessa: liga o valor que o pacote GRAVA ao espaço que o
# pacote PUBLICA. Se divergirem, o backoffice desenha um select onde o valor
# actual do cliente não aparece — e ao guardar, muda-o sem ninguém pedir.
# ─────────────────────────────────────────────────────────────────────────────

def test_o_fallback_de_fabrica_e_um_nome_canonico():
    assert ProfileLanguage().fallback in CANONICAL_NAMES


def test_os_aliases_de_fabrica_falam_codigos():
    aliases = ProfileLanguage().aliases
    assert aliases, "o default deixou de ter aliases — confirmar se é intencional"
    for chave, valor in aliases.items():
        assert is_known_language_code(chave), chave
        assert is_known_language_code(valor), valor


def test_o_allowed_de_fabrica_e_a_lista_aberta():
    assert ProfileLanguage().allowed == [ANY_LANGUAGE]


def test_os_idiomas_de_interface_de_fabrica_sao_linguas_de_interface():
    frontend = ProfileFrontendLanguage()
    assert frontend.default in UI_LANGS
    for codigo in frontend.enabled:
        assert codigo in UI_LANGS, codigo


# ─────────────────────────────────────────────────────────────────────────────
# Os espaços são separados — e têm de continuar
# ─────────────────────────────────────────────────────────────────────────────

def test_os_dois_espacos_nao_se_sobrepoem_e_isso_e_deliberado():
    """`pt` é locale de interface e NÃO é código do detector; `pt-PT` é o
    contrário. Juntar as duas listas parece arrumação e parte os dois campos."""
    assert "pt" in UI_LANGS and "pt" not in LANGUAGE_CODES
    assert "pt-PT" in LANGUAGE_CODES and "pt-PT" not in UI_LANGS


def test_forma_valida_nao_quer_dizer_conhecida():
    """A separação entre validar a FORMA e conhecer a língua. `allowed` aceita
    línguas de fora do mapa de propósito — nada aqui as pode recusar."""
    assert looks_like_language_tag("sw") is True
    assert is_known_language_code("sw") is False
    assert language_tag_problems(["sw", "sw-KE"]) == []


def test_todos_os_codigos_do_mapa_passam_o_validador_de_forma():
    """Coerência entre os dois módulos: um código no mapa que o validador
    marcasse como gralha fazia o backoffice avisar contra a nossa própria lista."""
    assert language_tag_problems(list(LANGUAGE_CODES)) == []


def test_o_wildcard_nao_e_uma_lingua():
    assert ANY_LANGUAGE not in LANGUAGE_CODES
    assert is_known_language_code(ANY_LANGUAGE) is False
    assert language_tag_problems([ANY_LANGUAGE]) == []


# ─────────────────────────────────────────────────────────────────────────────
# Locales da interface
# ─────────────────────────────────────────────────────────────────────────────

def test_normalise_ui_lang_espelha_o_fecore():
    for codigo in UI_LANGS:
        assert normalise_ui_lang(codigo) == codigo
        assert normalise_ui_lang(codigo.upper()) == codigo
    assert normalise_ui_lang("pt-PT") == "pt"
    assert normalise_ui_lang("de-CH") == "de"
    # o fecore não tem strings em chinês — cai para "", não inventa
    assert normalise_ui_lang("zh-CN") == ""


def test_as_sugestoes_de_locale_cabem_todas_na_interface():
    """Se uma sugestão não normalizar para uma língua de interface, um cliente
    escolhia-a em `frontend.language.default` e a UI abria noutra língua."""
    for locale in SUGGESTED_LOCALES:
        assert normalise_ui_lang(locale) != "", locale


def test_o_mapa_de_locales_cobre_exactamente_as_linguas_de_interface():
    assert set(UI_LANG_LOCALES) == set(UI_LANGS)


def test_as_linguas_rtl_sao_linguas_de_interface():
    for codigo in RTL_UI_LANGS:
        assert codigo in UI_LANGS
        assert is_rtl_ui_lang(codigo) is True
    assert is_rtl_ui_lang("pt") is False
    assert is_rtl_ui_lang("ar-AE") is True


@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize(
    "caminho", ["frontend.language.default", "frontend.language.enabled"]
)
def test_cada_lingua_de_interface_tem_etiqueta_no_catalogo(locale, caminho):
    """Acrescentar uma língua ao fecore e esquecer a etiqueta dava uma opção
    sem nome no backoffice do cliente. É este teste que chumba nesse dia."""
    etiquetas = options_of(caminho, locale)
    assert set(etiquetas) == set(UI_LANGS), (
        "as opções de %s em %s não cobrem UI_LANGS" % (caminho, locale)
    )
    for codigo, nome in etiquetas.items():
        assert nome.strip(), codigo
