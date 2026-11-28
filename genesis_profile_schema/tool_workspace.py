"""
genesis_profile_schema/tool_workspace.py — `tools.config.workspace`, a tool `workspace` do assistente (v0.1.187,
28 Nov 2026; desenho «Assistente nos workspaces», §11).

A tool `workspace` nasce sozinha quando um módulo com adaptador está ligado (hoje a Verificação Documental) e só
entra num turno que venha de dentro do workspace. Este bloco liga UMA coisa a mais, de propósito fora do workspace:

- `chat_doc_verification`: o chat DESTA frente (o principal — o «Workspace IA» —, ou uma variante), sem nenhum caso
  aberto, chega aos casos da Verificação Documental que CADA PESSOA pode ver: o ponto de situação, a lista, a
  pesquisa na ficha dos casos e o detalhe de um caso. Só com login (nunca anónimos nem convidados); a autorização é a
  da VD a cada chamada (frente visível + `access` da frente do caso + papéis de leitura + visibilidade do caso).
  O índice da VD nunca se liga como base de conhecimento do chat.

`False` por omissão: nenhum cliente muda sem alguém o ligar (a CCDR tem a VD numa Partilhada e não pode passar a ver
casos no chat principal por acidente). Numa Partilhada o valor do principal herda-se, como o resto de `tools.config`.
Mora em `_KNOWN_TOOL_CONFIG_MODELS` do `client_profile_schema` (guarda de forma; o blob guarda o dict que chegou).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, StrictBool


class ProfileToolWorkspaceConfig(BaseModel):
    """tools.config.workspace — o assistente fora dos workspaces (§11 do desenho).

    - chat_doc_verification: o chat desta frente chega aos casos da Verificação Documental que cada pessoa pode ver
      (com login; autorização da VD a cada chamada). `False` = como sempre: os casos só no assistente da própria VD.
    """
    model_config = ConfigDict(extra="allow")

    # StrictBool: um "true" em texto é erro, nunca um «ligado» por engano (é uma decisão de acesso a dados).
    chat_doc_verification: StrictBool = False


__all__ = ["ProfileToolWorkspaceConfig"]
