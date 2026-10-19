# -*- coding: utf-8 -*-
"""
Campos multilíngues (`i18n_fields.py`) e acesso público aos modelos das tools
(`tool_configs.py`).

O que estes testes impedem: um campo `{língua: texto}` novo nascer sem que
ninguém saiba que é multilíngue (o Studio não lhe dá o ✨ Traduzir e o gaibo
não lhe dá editor por língua). Um `Dict[str, str]` novo tem de usar um alias de
língua OU ficar declarado como mapa que não é de línguas — em silêncio, nunca.
"""

from genesis_profile_schema import (
    NOT_I18N_STR_MAPS,
    UNMARKED_I18N_FIELDS,
    i18n_field_paths,
    str_map_field_paths,
    tool_config_models,
)
from genesis_profile_schema.client_profile_schema import _KNOWN_TOOL_CONFIG_MODELS


def test_campos_conhecidos_sao_multilingues():
    paths = i18n_field_paths()
    for p in (
        "frontend.welcomeMessage",
        "frontend.welcomeSubtitle",
        "frontend.starterPrompts.title",
        "frontend.starterPrompts.prompt",
        "frontend.widget.greeting",
        "frontend.aiDisclosure.textI18n",
        "voice.greeting",
        "memory.onboarding_title",
        "reviewQueues.*.fields.label",
        "intake.definitions.*.title",
        # herdado do FieldDefinition (classe-mãe): a MRO conta
        "intake.definitions.*.questions.label",
        "tools.config.record_contact_details.purpose",
    ):
        assert p in paths, p


def test_mapas_que_nao_sao_de_linguas_ficam_de_fora():
    paths = i18n_field_paths()
    for p in ("personality.tone_instructions", "voices.by_locale", "language.aliases"):
        assert p not in paths, p


def test_todo_o_dict_str_str_esta_classificado():
    """Um `Dict[str, str]` sem alias de língua tem de estar numa das duas listas."""
    unclassified = str_map_field_paths() - set(NOT_I18N_STR_MAPS) - set(UNMARKED_I18N_FIELDS)
    assert not unclassified, (
        f"mapas de texto por classificar: {sorted(unclassified)} — se as chaves são "
        "línguas, usar o alias I18nMap (combinar com o gaibo se o campo for visível); "
        "senão, acrescentar a NOT_I18N_STR_MAPS com a razão"
    )


def test_listas_sem_entradas_mortas():
    """Uma entrada que já não é um `Dict[str, str]` sem alias (campo removido,
    renomeado ou já marcado com o alias) sai da lista."""
    stale = (set(NOT_I18N_STR_MAPS) | set(UNMARKED_I18N_FIELDS)) - str_map_field_paths()
    assert not stale, f"entradas mortas: {sorted(stale)}"


def test_as_duas_listas_nao_se_sobrepoem():
    assert not set(NOT_I18N_STR_MAPS) & set(UNMARKED_I18N_FIELDS)


def test_sem_include_unmarked_so_os_do_alias():
    assert not i18n_field_paths(include_unmarked=False) & set(UNMARKED_I18N_FIELDS)


def test_tool_config_models_e_uma_copia_do_mapa_privado():
    models = tool_config_models()
    assert models == _KNOWN_TOOL_CONFIG_MODELS
    models["x"] = object
    assert "x" not in _KNOWN_TOOL_CONFIG_MODELS
