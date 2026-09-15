"""
custom_instructions_text.py — separar, dentro de `custom_instructions`, o que
é nosso do que é do cliente.

`custom_instructions` é UM campo de texto, mas leva três autores: a frota (o
prompt base, que não está aqui), o ADAPTADOR (os playbooks de
`core/agent/mcp/templates.py`, copiados para o perfil quando se liga um
servidor MCP e congelados lá) e o cliente. A única marca de proveniência que
o texto tem é o cabeçalho do playbook:

    ## Folhas de cálculo consultáveis (Tabular) [genesis-mcp-tabular-playbook-v8]

Um lint que não separe as duas coisas reporta como colisão do cliente o que é
a nossa própria cópia. Este módulo é a separação — e é aqui, no pacote, para
que o Studio e o backoffice do cliente cortem pelo mesmo sítio.

REGRAS DE CORTE (verificadas contra os 4 templates existentes)
──────────────────────────────────────────────────────────────
- O marcador é `[<familia>-v<N>]` no fim de uma linha que começa por `## `.
  A família termina em `playbook`; a versão é um inteiro.
- O bloco vai do seu cabeçalho até ao PRÓXIMO cabeçalho `## `, à primeira
  LINHA EM BRANCO, ou ao fim do texto — o que vier primeiro. Os quatro
  playbooks não têm linha em branco interna nem `## ` interno (têm `###` e
  listas), e o `mcp_console` cola cada bloco ao texto existente com uma linha
  em branco; por isso essa linha é a fronteira mais fiável, e é o que devolve ao
  cliente o texto que ele escreva por baixo do playbook.
- A família é o marcador sem a versão — a mesma noção que o core usa para a
  idempotência ("um perfil com v1 não recebe o v2 em anexo").

Nunca levanta. Texto vazio ou sem marcadores devolve tudo como texto do
cliente.
"""

import re
from typing import Dict, List

PLAYBOOK_MARKER_RE = re.compile(
    r"^##[^\n]*?\[(?P<family>genesis-mcp-[a-z0-9-]*?playbook)-v(?P<version>\d+)\][^\n]*$",
    re.MULTILINE,
)
_HEADING_RE = re.compile(r"^## ", re.MULTILINE)
_BLANK_RE = re.compile(r"\n[ \t]*\n")


def split_playbook_blocks(text: str) -> Dict[str, object]:
    """`{"playbook_blocks": [...], "client_text": str}`.

    Cada bloco: `{family, version, marker, text}` — `text` inclui o cabeçalho.
    `client_text` é o que sobra, com o espaço em branco à volta dos cortes
    reduzido a uma linha em branco.
    """
    if not isinstance(text, str) or not text:
        return {"playbook_blocks": [], "client_text": ""}

    blocks: List[Dict[str, object]] = []
    spans: List[tuple] = []
    for m in PLAYBOOK_MARKER_RE.finditer(text):
        start = m.start()
        candidates = [len(text)]
        nxt = _HEADING_RE.search(text, m.end())
        if nxt:
            candidates.append(nxt.start())
        blank = _BLANK_RE.search(text, m.end())
        if blank:
            candidates.append(blank.start())
        end = min(candidates)
        family = m.group("family")
        version = int(m.group("version"))
        blocks.append({
            "family": family,
            "version": version,
            "marker": f"[{family}-v{version}]",
            "text": text[start:end].strip(),
        })
        spans.append((start, end))

    if not spans:
        return {"playbook_blocks": [], "client_text": text.strip()}

    kept: List[str] = []
    cursor = 0
    for start, end in spans:
        kept.append(text[cursor:start])
        cursor = end
    kept.append(text[cursor:])
    client = re.sub(r"\n{3,}", "\n\n", "".join(kept)).strip()
    return {"playbook_blocks": blocks, "client_text": client}


def playbook_families(text: str) -> List[str]:
    """As famílias presentes, na ordem em que aparecem (com repetições)."""
    return [str(b["family"]) for b in split_playbook_blocks(text)["playbook_blocks"]]


def duplicate_playbook_families(text: str) -> List[str]:
    """Famílias que aparecem mais de uma vez — dois playbooks a contradizer-se."""
    seen: Dict[str, int] = {}
    for fam in playbook_families(text):
        seen[fam] = seen.get(fam, 0) + 1
    return [fam for fam, n in seen.items() if n > 1]
