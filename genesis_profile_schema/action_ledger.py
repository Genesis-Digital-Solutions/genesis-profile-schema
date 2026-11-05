"""
action_ledger.py — registo durável das ações do assistente (`actionLedger`,
v0.1.115–116, 14 Out 2026; pack «Ações com regras, aprovação e registo», F3).

PORQUÊ
──────
Os bots agem (MCP com o ERP, pedidos, aprovações). Hoje a história de uma ação
está espalhada por quatro registos e ninguém a vê inteira. O F3 junta-a num
registo por cliente, uma entrada por evento (proposta, confirmação, regra,
aprovação, execução, resultado), encadeado por sha256 — o cliente pode
verificar que nada foi mudado nem tirado.

Decisões (Bruno, 13–14 Out 2026):
  • D3: contentor próprio no genai-core (`action_ledger`);
  • D4: a cadeia assenta no HASH dos valores — o apagamento RGPD apaga os
    valores e a cadeia continua válida (alinhado com as orientações do EDPB
    02/2025; nada de armazenamento imutável para os valores);
  • liga-se no Studio e no GAIBO, desligado por omissão; num cliente de ALTO
    RISCO o core regista SEMPRE (ignora o desligado) e, se não conseguir
    registar, a ação não corre;
  • retenção: alto risco → `compliance.high_risk.log_retention_days` (mínimo
    legal de 6 meses, AI Act arts. 19/26); os outros → `retention_days` deste
    bloco, 365 por omissão (uma auditoria anual).

`ledger_policy(profile)` é a regra ÚNICA (core, Studio e GAIBO usam esta):
«alto risco» = `compliance.classification.risk_level == "high"` OU
`compliance.high_risk.enabled` — a mesma do `compliance_context` do core.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, Iterable, List, Literal, Mapping, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_RETENTION_DAYS = 365
MIN_RETENTION_DAYS = 180          # AI Act: registos guardados pelo menos 6 meses
MAX_RETENTION_DAYS = 3650


class ProfileActionLedger(BaseModel):
    """`actionLedger` do perfil (só o BASE conta). Desligado por omissão."""
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    retention_days: int = Field(default=DEFAULT_RETENTION_DAYS, ge=MIN_RETENTION_DAYS, le=MAX_RETENTION_DAYS)
    # v0.1.156 (passo 5A do épico «Agente colega», decisão do Bruno a 5 Nov 2026):
    # «Testemunha selada». As cópias dos carimbos no storage do cliente (contentor
    # `ledger-witness`, só em produção) ficam em modo «Locked» até ao fim do prazo —
    # ninguém as apaga, nem a Genesis, e o storage do cliente só se pode apagar
    # depois. Desligado = «Unlocked» (protege contra erros e reescritas; quem tem a
    # chave da conta pode retirar a proteção). Só a Genesis liga (internal).
    witness_sealed: bool = False
    # v0.1.158 (5 Nov 2026, decisão do Bruno): carimbo temporal RFC 3161 de uma TSA
    # sobre o carimbo diário assinado (1 pedido por dia; só sai o hash). `public` =
    # uma TSA pública grátis, não qualificada; `qualified` = um prestador qualificado
    # eIDAS (a Genesis escolhe qual no código; enquanto não houver nenhum ativo usa-se
    # a pública e o ecrã diz); `off` = nenhum. None (omitido / null no blob) = `public`.
    # Só a Genesis escolhe (internal): o prestador qualificado tem contrato e custo.
    timestamping: Optional[Literal["public", "qualified", "off"]] = None


#: Os modos do carimbo temporal (`timestamping`), por ordem do ecrã.
TIMESTAMPING_MODES = ("public", "qualified", "off")
DEFAULT_TIMESTAMPING = "public"


def timestamping_mode(profile: Mapping[str, Any]) -> str:
    """`actionLedger.timestamping` do perfil BASE: `public` | `qualified` | `off`.
    Ausente, null ou desconhecido → `public` (v0.1.158). Nunca levanta."""
    try:
        block = (profile or {}).get("actionLedger") or {}
        mode = block.get("timestamping") if isinstance(block, Mapping) else None
        return mode if mode in TIMESTAMPING_MODES else DEFAULT_TIMESTAMPING
    except Exception:  # noqa: BLE001
        return DEFAULT_TIMESTAMPING


def witness_sealed(profile: Mapping[str, Any]) -> bool:
    """`actionLedger.witness_sealed` do perfil BASE é exatamente `True`? Nunca levanta."""
    try:
        block = (profile or {}).get("actionLedger") or {}
        return isinstance(block, Mapping) and block.get("witness_sealed") is True
    except Exception:  # noqa: BLE001
        return False


def is_high_risk(profile: Mapping[str, Any]) -> bool:
    """A mesma regra do `core/agent/compliance_context.py`. Nunca levanta."""
    try:
        comp = (profile or {}).get("compliance") or {}
        risk = str(((comp.get("classification") or {}).get("risk_level")) or "")
        return risk == "high" or bool((comp.get("high_risk") or {}).get("enabled"))
    except Exception:  # noqa: BLE001
        return False


def _int_in_range(value: Any, default: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    if isinstance(value, bool):
        return default
    return min(max(n, MIN_RETENTION_DAYS), MAX_RETENTION_DAYS)


def ledger_policy(profile: Mapping[str, Any]) -> Dict[str, Any]:
    """`{on, required, retention_days}`:
      on        — regista-se (ligado no perfil, ou cliente de alto risco);
      required  — alto risco: sem registo, a ação NÃO corre (falha fechada);
      retention_days — dias até o documento expirar (TTL).
    Nunca levanta; perfil estranho → desligado, 365 dias."""
    try:
        block = (profile or {}).get("actionLedger") or {}
        if not isinstance(block, Mapping):
            block = {}
        high = is_high_risk(profile)
        if high:
            hr = ((profile or {}).get("compliance") or {}).get("high_risk") or {}
            days = _int_in_range(hr.get("log_retention_days"), DEFAULT_RETENTION_DAYS)
        else:
            days = _int_in_range(block.get("retention_days"), DEFAULT_RETENTION_DAYS)
        return {"on": high or block.get("enabled") is True, "required": high, "retention_days": days}
    except Exception:  # noqa: BLE001
        return {"on": False, "required": False, "retention_days": DEFAULT_RETENTION_DAYS}


# ── A cadeia (a MESMA conta no core, que escreve, e em quem verifica) ────────

#: Os eventos da vida de uma ação. `started` (v0.1.116): escrito ANTES de
#: executar num cliente de alto risco — se não ficar escrito, a ação não corre
#: (a falha fechada prova-se por uma escrita, não por o contentor existir).
#: `checked` (v0.1.131, A2 do core agêntico): depois de uma escrita executada,
#: o core RELEU o sistema — `result.code` = `verified` | `unverified` |
#: `contradicted` (`ok` False só numa contradição: o que se escreveu não
#: aparece; a escrita nunca se repete). O motivo e a referência vão para
#: `detail` (apagável); a cadeia só leva o código.
#: `withdrawn` (v0.1.132): o pedido de aprovação, ainda pendente, foi RETIRADO
#: — por quem o pediu (`approver` vazio) ou por um operador ao parar a tarefa
#: no Studio (`approver` = «studio», nunca o email do operador); `actor` continua a ser
#: quem pediu, como nos outros eventos da aprovação. Nada corre depois dele.
EVENTS = ("proposed", "confirmed", "cancelled", "blocked_by_rule", "sent_for_approval", "approved",
          "rejected", "expired", "started", "executed", "failed", "checked", "withdrawn")

#: Os campos que entram no hash (lista FECHADA: um campo novo não muda a conta
#: das entradas antigas). NADA pessoal entra em claro: os valores (`params`) e
#: as identidades (quem pediu, quem aprovou) entram só como digest COM SAL
#: (`salted_digest`). O sal é por entrada e vive na parte apagável, ao lado dos
#: valores; apagar por RGPD tira os valores, as identidades e o sal — o digest
#: fica na cadeia mas deixa de se poder ligar à pessoa (um hash sem sal de
#: «total: 500» ou de um email adivinha-se; orientações do EDPB 02/2025).
#: `actor` = `{kind: user|agent|system, digest}`; `approver` = digest ou None;
#: `result` = `{ok, code}` — só um CÓDIGO curto (`RESULT_CODE`), nunca a
#: mensagem (um erro do ERP traz nomes e NIFs; a mensagem vai para `detail`,
#: apagável). v0.1.116: `expires_at` (quando esta entrada expira, monótono:
#: nunca antes da anterior) e `prev_expires_at` (quando a anterior expira) —
#: assim a verificação distingue uma entrada que EXPIROU de uma que foi TIRADA.
CHAIN_FIELDS = ("seq", "ts", "client_id", "variant_slug", "event", "action", "actor", "ref",
                "rule_id", "decision", "approver", "result", "params_digest",
                "expires_at", "prev_expires_at")

#: Cadeia v2 (v0.1.153, 4 Nov 2026 — passo 3 do épico «Agente colega», I2): cada
#: entrada NOVA leva `chain_v: 2` e `mission_s256` (o hash da missão aprovada de
#: uma ação do agente, `None` nas outras). A lista de campos de cada entrada
#: escolhe-se PELA VERSÃO dela: uma entrada antiga (sem `chain_v`) continua a
#: contar só os `CHAIN_FIELDS` — acrescentar um campo à lista v1 mudaria o hash de
#: todas as entradas já escritas (`entry.get(k)` → `null`) e partia a cadeia de
#: todos os clientes. O próprio `chain_v` entra no hash da v2: tirá-lo de uma
#: entrada (para a fazer passar por v1) parte-a.
CHAIN_FIELDS_V2 = CHAIN_FIELDS + ("chain_v", "mission_s256")

#: Cadeia v3 (v0.1.155, 5 Nov 2026 — passo 5A do épico «Agente colega», «quem fez
#: isto, porquê, e prova-o»): cada entrada NOVA leva também `effect_digest` (o
#: EFEITO que o sistema devolveu a uma escrita — o n.º da encomenda, da fatura, do
#: email) e `why_digest` (a justificação que o agente deu para a ação). Os dois são
#: digest COM SAL, como os `params` (um n.º de fatura de uma pessoa singular
#: identifica-a): o valor e o sal vivem na parte apagável (`effect`, `why`,
#: `salt.effect`, `salt.why`); o apagamento RGPD tira-os e a cadeia continua a
#: verificar-se. `None` quando a entrada não tem efeito ou justificação.
CHAIN_FIELDS_V3 = CHAIN_FIELDS_V2 + ("effect_digest", "why_digest")

#: Cadeia v4 (v0.1.158, 5 Nov 2026 — defesa contra prompt injection ao nível do
#: VALOR): cada entrada NOVA leva `provenance_digest` — digest COM SAL do registo de
#: proveniência de uma escrita do agente (`provenance_record`: que parâmetros
#: sensíveis só vieram de conteúdo não confiável ou de lado nenhum, de que origem,
#: e o que o core fez). O mesmo `params_digest` da entrada liga o VALOR; este campo
#: liga a ORIGEM e o motivo da aprovação. O registo e o sal vivem na parte apagável
#: (`provenance`, `salt.provenance`). `None` quando a entrada não tem achados.
CHAIN_V = 4
CHAIN_FIELDS_V4 = CHAIN_FIELDS_V3 + ("provenance_digest",)
_FIELDS_BY_VERSION = {None: CHAIN_FIELDS, 2: CHAIN_FIELDS_V2, 3: CHAIN_FIELDS_V3,
                      CHAIN_V: CHAIN_FIELDS_V4}

#: Todos os campos de cadeia de TODAS as versões — o que uma leitura com projeção
#: (verificar, provar) tem de pedir. Projetar com uma lista antiga parte as entradas
#: novas (`chain_v` em falta → contada como v1 → `hash_mismatch`; lição da v2).
CHAIN_FIELDS_ALL = tuple(dict.fromkeys(f for fs in _FIELDS_BY_VERSION.values() for f in fs))

#: O efeito guardado (valor na parte apagável): texto curto, normalizado por
#: `effect_norm` antes do digest e da pesquisa.
EFFECT_REF_MAX = 120
#: A justificação de uma ação do agente: curta e de uma linha.
WHY_MAX = 300

#: `mission_s256`: SHA-256 dos BYTES da missão, em base64url sem padding (AAuth,
#: draft-hardt-oauth-aauth-protocol-11 §8.2) — 43 caracteres.
MISSION_S256 = re.compile(r"[A-Za-z0-9_-]{43}")    # usar com `fullmatch`

#: Códigos aceites em `result.code` (o resto vira «error»).
RESULT_CODE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")

#: A parte apagável de cada entrada (nunca entra no hash). Os sais são POR
#: PAPEL (`salt.who`, `salt.approver`, `salt.params`): apagar quem só aprovou
#: não apaga os valores nem a identidade de quem pediu.
ERASABLE_FIELDS = ("params", "detail", "salt", "who", "effect", "why", "provenance")
ERASED = "[apagado]"

GENESIS_HASH = "0" * 64


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def salted_digest(salt: str, value: Any) -> str:
    """sha256(sal + canónico(valor)) — o que a cadeia guarda em vez de valores e
    identidades. Sem o sal (apagado), não se volta ao valor."""
    return hashlib.sha256((str(salt or "") + "|" + _canonical(value if value is not None else {}))
                          .encode("utf-8")).hexdigest()


def params_digest(params: Any, salt: str = "") -> str:
    """O digest dos valores da ação (com o sal da entrada)."""
    return salted_digest(salt, params if params is not None else {})


class UnknownChainVersion(ValueError):
    """Uma entrada com um `chain_v` que esta versão do schema não conhece."""


def chain_fields(entry: Mapping[str, Any]) -> Tuple[str, ...]:
    """Os campos que entram no hash DESTA entrada, pela versão dela."""
    v = entry.get("chain_v")
    if v not in _FIELDS_BY_VERSION or isinstance(v, bool):
        raise UnknownChainVersion(str(v))
    return _FIELDS_BY_VERSION[v]


def entry_hash(prev_hash: str, entry: Mapping[str, Any]) -> str:
    """sha256(prev_hash + canónico(campos da cadeia da versão da entrada))."""
    chained = {k: entry.get(k) for k in chain_fields(entry)}
    return hashlib.sha256((str(prev_hash or "") + "|" + _canonical(chained)).encode("utf-8")).hexdigest()


def mission_s256(mission_bytes: bytes) -> str:
    """O hash de uma missão (os bytes EXATOS que foram aprovados, nunca um
    objeto re-serializado)."""
    import base64
    digest = hashlib.sha256(bytes(mission_bytes)).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


#: O registo de proveniência guardado (forma fechada; o resto é descartado).
PROVENANCE_V = 1
PROVENANCE_MAX_FINDINGS = 20
PROVENANCE_ORIGINS = ("untrusted", "unknown")
PROVENANCE_OUTCOMES = ("logged", "approval", "blocked")
_PROV_TEXT = re.compile(r"[\x00-\x1f\x7f]")


def provenance_record(value: Any) -> Optional[Dict[str, Any]]:
    """A forma canónica do registo de proveniência de UMA ação (o que entra no
    `provenance_digest`), ou None sem achados. Cada achado: `param` (caminho do
    campo), `kind` (iban, bic, email, tax_id, phone, declared), `origin`
    (`untrusted` = visto só em conteúdo não confiável; `unknown` = em lado nenhum),
    `sources` (de onde: `item`, `item_email`, `attachment`, `mcp:<servidor>`,
    `event`) e `masked` (o valor mascarado — o valor exato está nos `params`, ligado
    pelo `params_digest` da mesma entrada). `outcome`: o que o core fez."""
    if not isinstance(value, Mapping):
        return None
    findings = value.get("findings")
    if not isinstance(findings, list):
        return None

    def txt(v: Any, n: int) -> str:
        return _PROV_TEXT.sub(" ", str(v or ""))[:n]

    out: List[Dict[str, Any]] = []
    for f in findings[:PROVENANCE_MAX_FINDINGS]:
        if not isinstance(f, Mapping) or f.get("origin") not in PROVENANCE_ORIGINS:
            continue
        srcs = f.get("sources") if isinstance(f.get("sources"), list) else []
        out.append({"param": txt(f.get("param"), 200), "kind": txt(f.get("kind"), 20),
                    "origin": str(f.get("origin")), "masked": txt(f.get("masked"), 80),
                    "sources": sorted({txt(x, 120) for x in srcs if str(x or "").strip()})[:10]})
    if not out:
        return None
    outcome = str(value.get("outcome") or "")
    return {"v": PROVENANCE_V, "outcome": outcome if outcome in PROVENANCE_OUTCOMES else "logged",
            "findings": out}


def effect_norm(value: Any) -> str:
    """A referência de um efeito, comparável: texto sem espaços nas pontas (até
    `EFFECT_REF_MAX`); só dígitos → sem zeros à esquerda (o SAP guarda o `VBELN`
    com zeros e a resposta pode não os trazer). '' quando não é um valor simples.
    O que entra no `effect_digest` e o que a pesquisa por efeito compara."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return ""
    s = str(value).strip()[:EFFECT_REF_MAX]
    return (s.lstrip("0") or "0") if s.isdigit() else s


def result_code(value: Any) -> str:
    """O código que pode entrar na cadeia (`RESULT_CODE`) ou «error»."""
    v = str(value or "").strip().lower()
    return v if RESULT_CODE.match(v) else ("error" if v else "")


def chain_start(first: Mapping[str, Any], now: float) -> Dict[str, Any]:
    """Onde começa a verificação de uma cadeia cuja 1.ª entrada existente é
    `first`: o início (seq 1), ou — se as anteriores já EXPIRARAM pela
    retenção (`prev_expires_at` ≤ agora, que está DENTRO da cadeia) — o elo
    que ela guarda. Uma entrada anterior em falta que ainda não devia ter
    expirado é uma entrada TIRADA. `{ok, start_prev, reason}`."""
    seq = int(first.get("seq") or 0)
    if seq <= 1:
        return {"ok": True, "start_prev": GENESIS_HASH, "reason": ""}
    pe = first.get("prev_expires_at")
    if isinstance(pe, (int, float)) and not isinstance(pe, bool) and pe <= now:
        return {"ok": True, "start_prev": str(first.get("prev_hash") or ""), "reason": ""}
    return {"ok": False, "start_prev": "", "reason": "missing_entry"}


def verify_chain(entries: Iterable[Mapping[str, Any]], *, start_prev: str = GENESIS_HASH,
                 expect_seq: Optional[int] = None) -> Dict[str, Any]:
    """Verifica entradas por ordem de `seq`. `{ok, checked, broken_at, reason, last_seq, last_hash}`:
    `broken_at` é o `seq` da 1.ª entrada que não bate (hash, elo ou buraco na
    sequência). `start_prev` + `expect_seq` deixam verificar por PÁGINAS (a
    página seguinte começa no `last_hash`/`last_seq + 1` da anterior).
    Os `params` apagados por RGPD não partem nada (só o digest conta)."""
    prev = start_prev
    expected_seq: Optional[int] = expect_seq
    checked = 0
    last_seq: Optional[int] = None
    rows: List[Mapping[str, Any]] = sorted(entries, key=lambda e: int(e.get("seq") or 0))
    for e in rows:
        seq = int(e.get("seq") or 0)
        if expected_seq is not None and seq != expected_seq:
            return {"ok": False, "checked": checked, "broken_at": expected_seq, "reason": "missing_entry",
                    "last_seq": last_seq, "last_hash": prev}
        if str(e.get("prev_hash") or "") != prev:
            return {"ok": False, "checked": checked, "broken_at": seq, "reason": "link_mismatch",
                    "last_seq": last_seq, "last_hash": prev}
        try:
            h = entry_hash(prev, e)
        except UnknownChainVersion:
            return {"ok": False, "checked": checked, "broken_at": seq, "reason": "unknown_chain_version",
                    "last_seq": last_seq, "last_hash": prev}
        if h != str(e.get("hash") or ""):
            return {"ok": False, "checked": checked, "broken_at": seq, "reason": "hash_mismatch",
                    "last_seq": last_seq, "last_hash": prev}
        prev, expected_seq, checked, last_seq = str(e.get("hash")), seq + 1, checked + 1, seq
    return {"ok": True, "checked": checked, "broken_at": None, "reason": "", "last_seq": last_seq,
            "last_hash": prev}
