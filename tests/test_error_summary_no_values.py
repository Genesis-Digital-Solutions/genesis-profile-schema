"""
tests/test_error_summary_no_values.py — Finding 62 do core / F-S56 do Studio
(12 Nov 2026): um erro de validação do schema nunca leva os valores recusados.

O `_validate_known_tool_configs` metia o `str()` do `ValidationError` interno
na mensagem (`input_value=<valor>` de cada campo) e encadeava-o com `from e`.
A config de uma tool pode ter segredos, e o core, o Studio, o GAIBO e o
genesis-mcp mostram/registam a `msg`. O que protege:
  1. o canário não aparece na `msg`, em `str(ValidationError)`, no `ctx` nem
     na cadeia de exceções; a mensagem continua a dizer qual campo falhou;
  2. uma guarda AST sobre o pacote inteiro: dentro de um `except`, todo o
     `raise X(...)` leva `from None` e o erro apanhado (`as x`) não aparece no
     corpo, a não ser em `error_summary_without_values(x)` ou na allowlist com
     a razão — o padrão que deixou o valor sair não volta.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError, field_validator

import genesis_profile_schema
from genesis_profile_schema.client_profile_schema import ClientProfileSchema
from genesis_profile_schema.error_summary import (
    MAX_SUMMARY_ERRORS,
    error_summary_without_values,
)

CANARY = "CANARY-sk-live-9f8e7d6c5b4a"


def _fail(profile: dict) -> ValidationError:
    with pytest.raises(ValidationError) as ei:
        ClientProfileSchema.model_validate(profile)
    return ei.value


def test_canario_nao_sai_na_msg_nem_no_str():
    err = _fail({"client_id": "c", "tools": {"config": {"run_code": {"timeout_s": CANARY}}}})
    msgs = [e["msg"] for e in err.errors()]
    assert any("tools.config.run_code inválido" in m for m in msgs)
    assert any("timeout_s" in m for m in msgs), msgs          # diz qual campo falhou
    assert all(CANARY not in m and "input_value" not in m for m in msgs)
    # O `str(ValidationError)` exterior traz depois o `input_value` do bloco
    # `tools` inteiro — é o Pydantic, não o schema, e o core e o Studio cortam
    # a mensagem antes do primeiro `input_value` (validation_errors). O que o
    # schema garante: a parte da mensagem antes desse ponto já não o tem.
    assert CANARY not in str(err).split("input_value", 1)[0]
    assert CANARY not in json.dumps(err.errors(include_input=False, include_url=False), default=str)


def test_ctx_e_cadeia_sem_o_valor():
    err = _fail({"client_id": "c", "tools": {"config": {"run_code": {"timeout_s": CANARY}}}})
    found = 0
    for e in err.errors():
        inner = (e.get("ctx") or {}).get("error")
        if isinstance(inner, BaseException):
            found += 1
            assert CANARY not in str(inner)
            assert inner.__cause__ is None                     # `from None`
            assert inner.__suppress_context__ is True
    assert found, "o ctx['error'] desapareceu — este teste deixava de verificar alguma coisa"


def test_varios_campos_resumo_com_corte_anunciado():
    # seis campos tipados do run_code inválidos → 5 mostrados e o corte anunciado
    cfg = {k: [CANARY] for k in ("deployment", "timeout_s", "max_runs_per_turn", "memory",
                                 "max_output_files", "allow_attachments")}
    err = _fail({"client_id": "c", "tools": {"config": {"run_code": cfg}}})
    msgs = " ".join(e["msg"] for e in err.errors())
    assert CANARY not in msgs
    assert "(+1 erro(s) não mostrado(s))" in msgs, msgs


class _Many(BaseModel):
    a: int
    b: int
    c: int
    d: int
    e: int
    f: int
    g: int


def test_resumo_corta_e_diz_quantos_ficaram_de_fora():
    with pytest.raises(ValidationError) as ei:
        _Many.model_validate({k: CANARY for k in "abcdefg"})
    s = error_summary_without_values(ei.value)
    assert CANARY not in s and "input" not in s
    assert s.count(":") >= MAX_SUMMARY_ERRORS
    assert f"(+{7 - MAX_SUMMARY_ERRORS} erro(s) não mostrado(s))" in s
    assert s.startswith("a: ")


def test_excecao_que_nao_e_validation_error_da_so_o_nome():
    assert error_summary_without_values(RuntimeError(CANARY)) == "RuntimeError"
    assert error_summary_without_values(TypeError(CANARY)) == "TypeError"


class _Echo(BaseModel):
    x: str

    @field_validator("x")
    @classmethod
    def _boom(cls, v):
        raise TypeError(v)  # um TypeError não é convertido pelo Pydantic


def test_validador_interno_com_excecao_crua_nao_ecoa(monkeypatch):
    from genesis_profile_schema import client_profile_schema as cps

    monkeypatch.setitem(cps._KNOWN_TOOL_CONFIG_MODELS, "eco_canario", _Echo)
    err = _fail({"client_id": "c", "tools": {"config": {"eco_canario": {"x": CANARY}}}})
    msgs = " ".join(e["msg"] for e in err.errors())
    assert "tools.config.eco_canario inválido: TypeError" in msgs
    assert CANARY not in msgs


# ── guarda AST: o padrão que deixou o valor sair não volta ao pacote ─────────

#: Usos do erro apanhado que não o levam para uma exceção (ficheiro, função → razão).
NAME_USE_ALLOWLIST = {
    ("field_values.py", "validate_answers"):
        "guarda o texto de um ValueError do próprio field_values, cujas mensagens nunca têm o valor",
    ("field_checks.py", "regex_risk"):
        "o texto de re.error só diz o motivo e a posição, nunca o padrão",
}


def _is_summary_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and getattr(
        node.func, "id", getattr(node.func, "attr", None)) == "error_summary_without_values"


def _handlers_with_function(tree: ast.AST):
    """(handler, nome da função mais interior que o contém, ou None)."""
    owner = {}
    for h in ast.walk(tree):
        if isinstance(h, ast.ExceptHandler):
            owner.setdefault(id(h), (h, None))
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for h in ast.walk(fn):
                if isinstance(h, ast.ExceptHandler):
                    owner[id(h)] = (h, fn.name)  # ast.walk vai de fora para dentro: fica a mais interior
    return owner.values()


def _offending_raises(tree: ast.AST, rel: str = "<teste>"):
    """Dentro de um `except`:
      - todo o `raise X(...)` leva `from None` (sem ele, o `__context__` implícito
        leva a exceção apanhada — e o texto dela — agarrada ao erro novo); só o
        `raise` sozinho e o `raise <nome>` (re-levantar) ficam de fora;
      - num `except ... as x`, `x` não aparece em lado nenhum do corpo, a não ser
        como argumento de `error_summary_without_values` (ou na allowlist)."""
    for handler, func in _handlers_with_function(tree):
        body = ast.Module(body=handler.body, type_ignores=[])
        for node in ast.walk(body):
            if isinstance(node, ast.Raise) and node.exc is not None:
                from_none = isinstance(node.cause, ast.Constant) and node.cause.value is None
                reraise = node.cause is None and isinstance(node.exc, ast.Name)
                if not (from_none or reraise):
                    yield node.lineno, "raise dentro de except sem `from None`"
        name = handler.name
        if not name or (rel, func) in NAME_USE_ALLOWLIST:
            continue
        safe = {id(arg) for call in ast.walk(body) if _is_summary_call(call) for arg in call.args}
        for node in ast.walk(body):
            if isinstance(node, ast.Name) and node.id == name and id(node) not in safe:
                yield node.lineno, f"usa `{name}` (o texto do erro pode trazer os valores)"


def test_guarda_ast_nenhum_raise_embrulha_a_excecao_apanhada():
    pkg = Path(genesis_profile_schema.__file__).parent
    bad = []
    for py in sorted(pkg.rglob("*.py")):
        rel = py.relative_to(pkg).as_posix()
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for lineno, why in _offending_raises(tree, rel):
            bad.append(f"{rel}:{lineno} — {why}")
    assert not bad, (
        "Dentro de um `except`, o erro apanhado não entra na exceção nova (o texto de um "
        "ValidationError traz os valores): usar `error_summary_without_values(x)` e `from None`:\n"
        + "\n".join(bad)
    )


def test_allowlist_continua_viva():
    pkg = Path(genesis_profile_schema.__file__).parent
    for (rel, func), why in NAME_USE_ALLOWLIST.items():
        tree = ast.parse((pkg / rel).read_text(encoding="utf-8"))
        assert any(f == func and h.name for h, f in _handlers_with_function(tree)), (rel, func, why)


def _check(handler_src: str) -> int:
    src = "try:\n    pass\n" + handler_src
    return len(list(_offending_raises(ast.parse(src))))


def test_guarda_ast_apanha_os_padroes_conhecidos():
    # o padrão antigo e os desvios que a primeira versão da guarda deixava passar
    assert _check("except Exception as e:\n    raise ValueError(f'tools.config.x inválido: {e}') from e\n") >= 1
    assert _check("except Exception as e:\n    m = str(e)\n    raise ValueError(m) from None\n") == 1
    assert _check("except Exception as e:\n    raise ValueError('x') from e.__cause__\n") >= 1
    assert _check("except Exception:\n    raise ValueError('x')\n") == 1
    assert _check("except Exception as e:\n    raise ValueError(f'{error_summary_without_values(e)} {e}') from None\n") == 1
    assert _check("except Exception as e:\n    raise e\n") == 1          # re-levantar é com `raise` sozinho
    # o que é aceite
    assert _check("except Exception as e:\n    raise ValueError(f'x: {error_summary_without_values(e)}') from None\n") == 0
    assert _check("except Exception:\n    raise\n") == 0
    assert _check("except ValueError:\n    raise ValueError('x') from None\n") == 0
