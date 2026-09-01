"""
ui_text.py — o nome e a explicação de cada campo, por língua.

Quarta camada do contrato: a forma está em `client_profile_schema.py`, quem
pode ver está em `exposure.py`, e aqui está como se chama isto em linguagem de
pessoa. O catálogo vive em `ui_text/<locale>.json`, indexado pelo caminho do
campo — o caminho JÁ é a chave, não há chaves de tradução a inventar nem a
manter em paralelo com ele.

PORQUÊ NO PACOTE
────────────────
Este texto estava escrito duas vezes: ~400 entradas no backoffice do cliente e
48 hints no editor do Studio, a descrever os mesmos campos, sem nada que
obrigasse qualquer um dos dois a acompanhar o schema. Um campo novo aparecia
nos dois com o nome cru (`enableLlmSelector`) e ninguém dava por isso. O
catálogo aqui é a fusão dessas duas fontes — nada foi inventado: o que não
existia foi escrito a partir dos comentários do próprio schema.

DOIS REGISTOS, DE PROPÓSITO
───────────────────────────
  label    — o nome do campo.
  help     — o que acontece se mexeres. Voz de quem usa o produto: diz o
             efeito, não a implementação.
  note     — detalhe técnico nosso (envs, precedências, acoplamentos). Voz de
             operador. O Studio mostra-a; uma montra de cliente não.
  options  — o nome de cada valor de uma lista fechada. Sem isto o cliente lê
             `soft_redirect`.

As duas vozes não são um luxo: as hints do Studio dizem coisas como "passa
para tool.__init__", que é exactamente o que um cliente não deve ler, e são
exactamente o que nós precisamos de ler.

FICHEIRO EM FALTA NÃO REBENTA
─────────────────────────────
Um catálogo ausente ou ilegível devolve vazio e cada consumidor cai no seu
próprio fallback (o caminho cru, que é o que já mostram hoje). Texto de
interface nunca deve derrubar o arranque de um serviço.
"""

import json
import os
from functools import lru_cache
from typing import Any, Dict, Optional, Tuple

from genesis_profile_schema.exposure import normalise_path

LOCALES: Tuple[str, ...] = ("pt-PT", "en-GB")
DEFAULT_LOCALE = "pt-PT"

_ENTRY_KEYS: Tuple[str, ...] = ("label", "help", "note", "options")
_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui_text")


@lru_cache(maxsize=len(LOCALES) + 1)
def catalogue(locale: str = DEFAULT_LOCALE) -> Dict[str, Dict[str, object]]:
    """`{caminho: {label, help, note, options}}` para esta língua.

    Língua desconhecida, ficheiro em falta ou JSON inválido devolvem `{}`.
    """
    if locale not in LOCALES:
        return {}
    try:
        with open(os.path.join(_DIR, locale + ".json"), encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, ValueError):
        return {}
    fields = payload.get("fields")
    return fields if isinstance(fields, dict) else {}


def text_for(path: str, locale: str = DEFAULT_LOCALE) -> Dict[str, object]:
    """O registo completo de um campo, ou `{}`.

    Sem fallback por antepassado, ao contrário do `exposure_of`: o nome do pai
    não é o nome do filho, e herdá-lo escreveria "Mensagem de boas-vindas" por
    cima de cada código de língua lá dentro.
    """
    return catalogue(locale).get(normalise_path(path), {})


def label_of(path: str, locale: str = DEFAULT_LOCALE) -> Optional[str]:
    value = text_for(path, locale).get("label")
    return value if isinstance(value, str) else None


def help_of(path: str, locale: str = DEFAULT_LOCALE) -> Optional[str]:
    value = text_for(path, locale).get("help")
    return value if isinstance(value, str) else None


def note_of(path: str, locale: str = DEFAULT_LOCALE) -> Optional[str]:
    value = text_for(path, locale).get("note")
    return value if isinstance(value, str) else None


def options_of(path: str, locale: str = DEFAULT_LOCALE) -> Dict[str, str]:
    value = text_for(path, locale).get("options")
    return dict(value) if isinstance(value, dict) else {}


def entry_keys() -> Tuple[str, ...]:
    """As chaves que um registo pode ter — o gate recusa qualquer outra."""
    return _ENTRY_KEYS


# ─────────────────────────────────────────────────────────────────────────────
# Projecção para dentro do JSON Schema
#
# Quem consome o contrato pela via normal — `model_json_schema()` — não vê o
# catálogo. Em vez de escrever o texto duas vezes (no modelo E aqui), que era o
# problema que este módulo veio resolver, projecta-se: uma fonte, duas formas.
#
#   title       ← label     (o `title` que o Pydantic gera sozinho é o nome do
#                            campo em titlecase, "Enablellmselector")
#   description ← help
#   x-genesis-option-labels ← options
#
# A `note` NÃO é projectada: é voz de operador e o JSON Schema é servido a
# quem não a deve ler.
# ─────────────────────────────────────────────────────────────────────────────

_OPTIONS_KEY = "x-genesis-option-labels"


def _index_nodes(schema: Dict[str, Any]) -> Dict[str, Any]:
    """`{caminho: nó}` seguindo properties, $ref e items.

    Devolve os nós do PRÓPRIO dicionário recebido, para se poderem anotar.
    Um `$def` referenciado em dois sítios devolve o MESMO nó em dois caminhos
    — é por isso que quem anota tem de verificar se o texto coincide.
    """
    defs = schema.get("$defs", {})
    nodes: Dict[str, Any] = {}

    def target(node):
        while isinstance(node, dict) and "$ref" in node:
            node = defs.get(node["$ref"].split("/")[-1], {})
        return node if isinstance(node, dict) else {}

    def walk(node, path, seen):
        node = node if isinstance(node, dict) else {}
        alvo = target(node)
        props = alvo.get("properties")
        if props:
            for key, sub in props.items():
                sub_path = f"{path}.{key}" if path else key
                nodes.setdefault(sub_path, sub)
                marca = id(sub)
                if marca in seen:      # modelo recursivo — não descer outra vez
                    continue
                walk(sub, sub_path, seen | {marca})
            return
        item = target(alvo.get("items", {}))
        if item.get("properties"):
            for key, sub in item["properties"].items():
                sub_path = f"{path}.{key}" if path else key
                nodes.setdefault(sub_path, sub)
                marca = id(sub)
                if marca in seen:
                    continue
                walk(sub, sub_path, seen | {marca})

    walk(schema, "", frozenset())
    return nodes


@lru_cache(maxsize=len(LOCALES) + 1)
def _annotate(locale: str) -> Tuple[Dict[str, Any], Tuple[str, ...]]:
    import copy

    from genesis_profile_schema.client_profile_schema import ClientProfileSchema

    schema = copy.deepcopy(ClientProfileSchema.model_json_schema())
    textos = catalogue(locale)
    nodes = _index_nodes(schema)

    # Um nó partilhado por vários caminhos só é anotado se todos concordarem
    # no texto — senão o `theme.light` levava a descrição do `theme.dark`.
    por_no: Dict[int, list] = {}
    for path, node in nodes.items():
        por_no.setdefault(id(node), []).append(path)

    conflitos = []
    for path, node in nodes.items():
        rec = textos.get(path)
        if not rec:
            continue
        irmaos = por_no.get(id(node), [path])
        if len(irmaos) > 1:
            valores = {
                (textos.get(p, {}).get("label"), textos.get(p, {}).get("help"))
                for p in irmaos
            }
            if len(valores) > 1:
                conflitos.append(path)
                continue
        if rec.get("label"):
            node["title"] = rec["label"]
        if rec.get("help"):
            node["description"] = rec["help"]
        if rec.get("options"):
            node[_OPTIONS_KEY] = dict(rec["options"])

    return schema, tuple(sorted(conflitos))


def annotated_json_schema(locale: str = DEFAULT_LOCALE) -> Dict[str, Any]:
    """O JSON Schema do contrato com `title`/`description` desta língua.

    Mesma forma do `model_json_schema()` — `$defs` e `$ref` intactos, o texto
    ao lado do `$ref` como já acontece com os marcadores `requires_*`. Um
    consumidor que só saiba ler JSON Schema recebe o catálogo sem saber que
    ele existe.
    """
    import copy

    return copy.deepcopy(_annotate(locale)[0])


def annotation_conflicts(locale: str = DEFAULT_LOCALE) -> Tuple[str, ...]:
    """Caminhos que ficaram por anotar por partilharem um `$def` com outro
    caminho de texto diferente. Hoje: os tokens de cor de `theme.light` e
    `theme.dark`, que são o mesmo modelo usado duas vezes. O texto deles
    continua acessível por `label_of()`/`help_of()`."""
    return _annotate(locale)[1]
