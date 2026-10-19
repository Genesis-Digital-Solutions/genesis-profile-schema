"""
i18n_fields.py — que campos do perfil são MULTILÍNGUES ({língua: texto}).

Regra do produto (Bruno, 19 Out 2026): todo o campo multilíngue tem a opção de
o agente traduzir. Para um consumidor (o Studio, o gaibo) o cumprir, precisa
de saber QUAIS são — e o schema não o diz sozinho: `I18nMap` é um alias simples
de `Dict[str, str]`, igual em runtime e no JSON Schema a mapas cujas chaves não
são línguas (`personality.tone_instructions`, `voices.by_locale`,
`language.aliases`).

A marca é o NOME do alias no código-fonte do pacote: `I18nMap`, `I18nText`,
`I18nHelp`, `I18nNotice`. É a mesma regra que o gaibo já usa
(`gaibo_api/profile/i18n_maps.py`, que lê o fonte do `client_profile_schema`),
aqui alargada aos módulos com modelos próprios (`field_definition`,
`intake_schema`) e aos blocos tipados de `tools.config`.

⚠️ Este módulo NÃO muda nenhum tipo. Trocar `Dict[str, str]` por um alias (ou
o alias por outra coisa) muda o que o gaibo faz: o gerador dele passa a dar
editor por língua ao campo e o portão de gravação passa a tratá-lo como mapa
de línguas. Por isso os três campos multilíngues que ainda não usam o alias
ficam declarados em `UNMARKED_I18N_FIELDS`, e marcá-los é uma mudança a
combinar com a equipa do gaibo, não uma limpeza.

Caminhos no dialecto do `exposure` (sem índices nem `[]`), com `*` no lugar da
chave de um mapa de modelos (`reviewQueues.*`, `intake.definitions.*`) e
`tools.config.<tool>` à frente dos blocos tipados das tools.
"""

import ast
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Dict, FrozenSet, Iterator, Tuple, Union, get_args, get_origin

from pydantic import BaseModel

__all__ = [
    "I18N_ALIASES",
    "NOT_I18N_STR_MAPS",
    "UNMARKED_I18N_FIELDS",
    "i18n_field_paths",
    "str_map_field_paths",
]

# Os nomes que, no fonte do pacote, dizem «chaves = línguas».
I18N_ALIASES: Tuple[str, ...] = ("I18nMap", "I18nText", "I18nHelp", "I18nNotice")

# Mapas de texto cujas chaves NÃO são línguas. Um `Dict[str, str]` novo tem de
# entrar aqui (com a razão) ou usar um dos aliases — o teste chumba caso contrário.
NOT_I18N_STR_MAPS: Dict[str, str] = {
    "personality.tone_instructions": "chave = tom (professional, friendly…), não língua",
    "retrieval.source_priority.label_overrides": "chave = entrada da allowlist de fontes",
    "language.aliases": "chave = código de língua de ENTRADA, valor = língua servida (não é texto)",
    "voices.by_locale": "chave = locale BCP-47, valor = nome de voz TTS (não é texto)",
    "voices.phonetic_map": "chave = palavra, valor = pronúncia",
    "frontend.ttsPhoneticMap": "chave = palavra, valor = pronúncia",
    "frontend.ttsVoiceMap": "chave = locale, valor = nome de voz TTS (não é texto)",
    "voice.transfer_sip_uris": "chave = destino, valor = URI SIP",
    "contacts.attribute_paths": "chave = atributo, valor = caminho no registo",
    "reviewQueues.*.gates.decide": "chave = decisão da tool, valor = consequência",
}

# Multilíngues DE FACTO (o Studio traduz-os com o ✨) que não usam o alias: são
# `Union[str, Dict[str, str]]`. Marcá-los muda o gaibo (ver docstring) — fica
# para combinar com a equipa do gaibo; até lá, contam como multilíngues aqui.
UNMARKED_I18N_FIELDS: Dict[str, str] = {
    "tools.config.extract_legal_terms.schema.*.label": "rótulo do campo extraído; o Studio traduz (✨)",
    "tools.config.record_contact_details.fields.label": "rótulo do campo da captura",
    "tools.config.record_contact_details.purpose": "finalidade da recolha; o Studio traduz (✨)",
}

_PACKAGE = "genesis_profile_schema"


@lru_cache(maxsize=1)
def _alias_annotated() -> FrozenSet[Tuple[str, str, str]]:
    """`(módulo, classe, campo)` de cada campo cuja anotação NO FONTE nomeia um
    dos `I18N_ALIASES`, em todos os módulos do pacote."""
    found = set()
    for src in sorted(Path(__file__).parent.glob("*.py")):
        tree = ast.parse(src.read_text(encoding="utf-8"))
        module = f"{_PACKAGE}.{src.stem}"
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            for stmt in node.body:
                if not (isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)):
                    continue
                names = {n.id for n in ast.walk(stmt.annotation) if isinstance(n, ast.Name)}
                if names & set(I18N_ALIASES):
                    found.add((module, node.name, stmt.target.id))
    return frozenset(found)


def _is_str_map(annotation: object) -> bool:
    """A anotação é (ou contém, por Optional/Union/Annotated) um `Dict[str, str]`."""
    origin = get_origin(annotation)
    if origin is Annotated:
        return _is_str_map(get_args(annotation)[0])
    if origin is dict:
        return get_args(annotation) == (str, str)
    if origin is Union:
        return any(_is_str_map(a) for a in get_args(annotation))
    return False


def _children(annotation: object, seg: str = "") -> Iterator[Tuple[type, str]]:
    """Os modelos a que a anotação leva, com o segmento de caminho (`""` numa
    lista ou diretamente, `".*"` num mapa de modelos)."""
    origin = get_origin(annotation)
    if origin is None:
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            yield annotation, seg
        return
    args = get_args(annotation)
    if origin is Annotated:
        yield from _children(args[0], seg)
    elif origin is dict:
        if len(args) == 2:
            yield from _children(args[1], seg + ".*")
    else:  # list, Optional/Union, …
        for a in args:
            if a is not type(None):
                yield from _children(a, seg)


def _walk(model: type, prefix: str, stack: Tuple[type, ...],
          visit) -> None:
    if model in stack:
        return
    for name, field in model.model_fields.items():
        path = f"{prefix}.{field.alias or name}" if prefix else (field.alias or name)
        visit(model, name, field.annotation, path)
        for child, seg in _children(field.annotation):
            _walk(child, path + seg, stack + (model,), visit)


def _roots() -> Iterator[Tuple[type, str]]:
    from .client_profile_schema import ClientProfileSchema
    from .tool_configs import tool_config_models

    yield ClientProfileSchema, ""
    for tool, model in tool_config_models().items():
        yield model, f"tools.config.{tool}"


@lru_cache(maxsize=1)
def _scan() -> Tuple[FrozenSet[str], FrozenSet[str]]:
    marked = _alias_annotated()
    i18n, str_maps = set(), set()

    def visit(model, name, annotation, path):
        # O campo pode vir de uma classe-mãe (ex.: as perguntas do Intake herdam o
        # `label`/`help` do `FieldDefinition`): procura-se em toda a MRO.
        if any((c.__module__, c.__name__, name) in marked for c in model.__mro__):
            i18n.add(path)
        elif _is_str_map(annotation):
            str_maps.add(path)

    for model, prefix in _roots():
        _walk(model, prefix, (), visit)
    return frozenset(i18n), frozenset(str_maps)


def i18n_field_paths(include_unmarked: bool = True) -> FrozenSet[str]:
    """Caminhos dos campos multilíngues. Com `include_unmarked` (por omissão),
    inclui os de `UNMARKED_I18N_FIELDS`, que também se traduzem."""
    marked = _scan()[0]
    return marked | frozenset(UNMARKED_I18N_FIELDS) if include_unmarked else marked


def str_map_field_paths() -> FrozenSet[str]:
    """Campos `Dict[str, str]` SEM alias de língua — cada um tem de estar em
    `NOT_I18N_STR_MAPS` ou em `UNMARKED_I18N_FIELDS` (há teste)."""
    return _scan()[1]
