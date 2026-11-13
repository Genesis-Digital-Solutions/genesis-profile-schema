"""
Dígitos só ASCII nas datas, meses, portas e números de página (v0.1.168, 13 Nov 2026).

Em Python o `\\d` sobre `str` casa QUALQUER dígito decimal Unicode, e o `\\d` do
`Field(pattern=)` também: `٢٠٢٦-٠١-٠١` passava como data e depois não batia com
`2026-01-01` (ou rebentava no `date.fromisoformat` de quem lê). Onde há escrita
humana, os dígitos de outras escritas NORMALIZAM-SE para ASCII (o valor fica
canónico e um perfil gravado nunca deixa de carregar); onde é verificação de
contrato (fragmento `#page=N`, porta de uma origem), recusa-se.

O último teste é o canário: parte se aparecer um `\\d` novo numa regex do pacote.
"""

import ast
import pathlib

import pytest
from pydantic import ValidationError

import genesis_profile_schema
from genesis_profile_schema import field_checks as fc
from genesis_profile_schema import gaibo_index as gi
from genesis_profile_schema.client_profile_schema import ProfileCalendar
from genesis_profile_schema.custom_instructions_text import playbook_families
from genesis_profile_schema.digits import ascii_digits, ascii_digits_before
from genesis_profile_schema.field_values import iso_value
from genesis_profile_schema.gaibo_index.index_fields import _url_problems
from genesis_profile_schema.intake_schema import (
    IntakeDocumentTemplate, IntakeMethodology, IntakeReferenceCase, MethodologyApproval,
)

ARABIC = "٢٠٢٦-٠١-٠١"            # árabe-oriental (U+0660–0669)
PERSIAN = "۲۰۲۶-۰۱-۰۱"           # persa (U+06F0–06F9)
FULLWIDTH = "２０２６-０１-０１"   # largura total
DEVANAGARI = "२०२६-०१-०१"


# ── a conversão ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw", [ARABIC, PERSIAN, FULLWIDTH, DEVANAGARI])
def test_ascii_digits_converte_todas_as_escritas(raw):
    assert ascii_digits(raw) == "2026-01-01"


def test_ascii_digits_nao_inventa_numeros_nem_mexe_no_resto():
    assert ascii_digits("m² e ½") == "m² e ½"          # não são dígitos decimais
    assert ascii_digits("easter+٣٩") == "easter+39"
    assert ascii_digits("") == ""
    assert ascii_digits_before(5) == 5 and ascii_digits_before(None) is None


# ── calendar.holidays ──────────────────────────────────────────────────────

def test_feriado_com_digitos_de_outra_escrita_fica_canonico_e_sem_repetidos():
    cal = ProfileCalendar(holidays=[ARABIC, "2026-01-01", "٠٦-١٣", "EASTER+٣٩", FULLWIDTH])
    assert cal.holidays == ["2026-01-01", "06-13", "easter+39"]


@pytest.mark.parametrize("bad", ["2026-01-01\n2026", "٢٠٢٦-١٣-٠١", "easter+١٢١", "2026-1-1"])
def test_feriado_invalido_continua_recusado(bad):
    with pytest.raises(ValidationError):
        ProfileCalendar(holidays=[bad])


# ── datas do Intake (Field(pattern=)) ──────────────────────────────────────

def _molde(**over):
    m = {"key": "anexo_ii", "kind": "questionnaire", "title": {"pt": "Anexo II", "en": "Annex II"},
         "template": "anexo_ii_v1.docx", "sha256": "a" * 64, "version": "1.0", "effective_from": ARABIC}
    m.update(over)
    return IntakeDocumentTemplate.model_validate(m)


def test_datas_do_intake_normalizam_e_a_comparacao_de_texto_bate():
    assert MethodologyApproval(by="Compliance", at=PERSIAN).at == "2026-01-01"
    case = IntakeReferenceCase.model_validate(
        {"key": "c1", "answers": {}, "reference_date": FULLWIDTH, "expected": {"outcome": "ok"}})
    assert case.reference_date == "2026-01-01"
    assert "effective_from" in IntakeMethodology.model_fields     # o campo da metodologia usa o mesmo tipo
    assert IntakeMethodology.model_fields["effective_from"].annotation ==         IntakeDocumentTemplate.model_fields["revoked_from"].annotation
    doc = _molde(revoked_from="٢٠٢٧-٠١-٠١")
    assert (doc.effective_from, doc.revoked_from) == ("2026-01-01", "2027-01-01")
    # `revoked_from <= effective_from` compara texto: só bate com os dois em ASCII.
    with pytest.raises(ValidationError):
        _molde(revoked_from="2025-12-31")


@pytest.mark.parametrize("bad", ["2026-01-01\n", "26-01-01", "abc", 20260101])
def test_datas_do_intake_invalidas_continuam_recusadas(bad):
    with pytest.raises(ValidationError):
        MethodologyApproval(by="x", at=bad)


def test_json_schema_das_datas_tem_o_padrao_ascii():
    """O editor do Studio e o gerador do GAIBO leem o padrão do JSON Schema."""
    node = MethodologyApproval.model_json_schema()["properties"]["at"]
    assert node["pattern"] == "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"


# ── valores de campos de data (field_values) ───────────────────────────────

def test_valor_de_data_com_digitos_arabes_fica_canonico():
    assert iso_value(ARABIC, "date") == "2026-01-01"
    assert iso_value("٢٠٢٦-٠١-٠١T١٠:٣٠", "datetime") == "2026-01-01T10:30:00"
    for bad in ("2026-01-01\n", "2026-02-30"):
        with pytest.raises(ValueError):
            iso_value(bad, "date")


# ── GAIBO: mês do desbloqueio, fragmento #page=N, porta do core ────────────

def test_mes_do_desbloqueio_normaliza_e_bate_com_o_mes_corrente():
    s = gi.GaiboSettings(max_documents_per_month=10, extra_documents=5,
                         extra_documents_month="٢٠٢٦-١١")
    assert s.extra_documents_month == "2026-11"
    assert s.monthly_allowance("2026-11") == 15
    with pytest.raises(ValidationError):
        gi.GaiboSettings(extra_documents_month="2026-13")


def test_fragmento_de_pagina_so_com_digitos_ascii():
    base = "https://stcliente.blob.core.windows.net/gaibo-sources/j-abcdefgh/a.pdf"
    assert _url_problems(base + "#page=12") == []
    assert _url_problems(base + "#page=١٢")              # nenhum visor de PDF o lê


@pytest.mark.parametrize("url,ok", [
    ("https://core.example.io:8443", True),
    ("https://core.example.io:65535", True),
    ("https://core.example.io:1", True),
    ("https://core.example.io:0", False),
    ("https://core.example.io:65536", False),
    ("https://core.example.io:99999", False),
    ("https://core.example.io:080", False),
    ("https://core.example.io:٨٠", False),
])
def test_porta_do_core_do_gaibo_entre_1_e_65535(url, ok):
    if ok:
        assert gi.GaiboSettings(dev_core_url=url).dev_core_url == url
    else:
        with pytest.raises(ValidationError):
            gi.GaiboSettings(dev_core_url=url)


# ── origens do CSP: porta 1..65535 ─────────────────────────────────────────

@pytest.mark.parametrize("token,ok", [
    ("https://a.cliente.pt:443", True),
    ("https://a.cliente.pt:65535", True),
    ("localhost:4200", True),
    ("capacitor://app.cliente.pt:8080", True),
    ("https://a.cliente.pt:0", False),
    ("https://a.cliente.pt:65536", False),
    ("https://a.cliente.pt:99999", False),
    ("https://a.cliente.pt:0443", False),
    ("localhost:0", False),
    ("capacitor://app.cliente.pt:70000", False),
])
def test_porta_das_origens_csp_entre_1_e_65535(token, ok):
    assert fc.is_valid_csp_source(token) is ok


# ── marcador dos playbooks ─────────────────────────────────────────────────

def test_marcador_de_playbook_so_com_versao_ascii():
    assert playbook_families("## X [genesis-mcp-erp-playbook-v12]\ntexto") == ["genesis-mcp-erp-playbook"]
    assert playbook_families("## X [genesis-mcp-erp-playbook-v١٢]\ntexto") == []


# ── `fullmatch`: um `\n` no fim já não passa nos ids ───────────────────────

@pytest.mark.parametrize("fn,good", [
    (gi.request_blob, "pr-abcdefgh"),
    (gi.result_blob, "pr-abcdefgh"),
    (gi.run_blob, "run-abcdefgh"),
    (gi.invite_blob, "inv-abcdefgh"),
    (gi.removal_blob, "gr-abcdefgh"),
])
def test_ids_com_quebra_de_linha_no_fim_nao_montam_nomes_de_blob(fn, good):
    """Com `.match` e `$` passava `pr-abcdefgh\\n` → `requests/pr-abcdefgh\\n.json`."""
    assert fn(good).endswith(f"{good}.json")
    with pytest.raises(ValueError):
        fn(good + "\n")


def test_validadores_de_forma_recusam_quebra_de_linha_no_fim():
    assert gi.is_valid_doc_key("j-abcdefgh") and not gi.is_valid_doc_key("j-abcdefgh\n")
    assert not gi.is_valid_request_id("pr-abcdefgh\n") and not gi.is_valid_run_id("run-abcdefgh\n")
    assert not gi.is_valid_invite_id("inv-abcdefgh\n") and not gi.is_valid_notice_id("gr-abcdefgh\n")


# ── datas do Intake que não existem ────────────────────────────────────────

@pytest.mark.parametrize("bad", ["2026-02-30", "2026-13-01", "٢٠٢٦-١٣-٠١"])
def test_data_do_intake_inexistente_recusada(bad):
    with pytest.raises(ValidationError):
        MethodologyApproval(by="x", at=bad)


def test_feriados_e_valores_enormes_recusados_sem_percorrer_tudo():
    with pytest.raises(ValidationError):
        ProfileCalendar(holidays=["2026-01-01"] * 1001)
    assert ProfileCalendar(holidays=["2026-01-01"] * 1000).holidays == ["2026-01-01"]
    with pytest.raises(ValidationError):
        ProfileCalendar(holidays=["٢" * 100_000])
    with pytest.raises(ValueError):
        iso_value("٢" * 100_000, "date")


# ── canário: regex do pacote só com dígitos ASCII e `fullmatch` ────────────

PKG = pathlib.Path(genesis_profile_schema.__file__).parent

# `\d`, `\w` e `\p{N…}` casam dígitos de qualquer escrita (`٢٠٢٦`), em `re` e no
# motor do `Field(pattern=)`.
UNICODE_DIGIT_CLASSES = ("\\d", "\\w", "\\p{N")

# Exceções conscientes. Cada uma diz porquê; acrescentar aqui exige o mesmo.
ALLOWED_VALUES = {
    # `retrieval.latest_version.year_segment_regex`: default de CONFIGURAÇÃO (não
    # validação) que o core compila e aplica a caminhos de fontes
    # (`tools/knowledge_base/source_priority.py`), com `int()` sobre o grupo — que
    # também lê dígitos de outras escritas, por isso não há divergência. Mudar o
    # default mudava o valor dos perfis que ainda não o têm gravado (45 da frota já
    # o têm, 13 Nov 2026), sem ganho.
    r"/(19\d{2}|20\d{2})/",
}


def _docstring_ids(tree):
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            ids.add(id(node.value))
    return ids


def _package_trees():
    for path in sorted(PKG.rglob("*.py")):
        yield path.relative_to(PKG).as_posix(), ast.parse(path.read_text(encoding="utf-8"))


def test_canario_nenhuma_regex_do_pacote_usa_classes_de_digitos_unicode():
    offenders = []
    for rel, tree in _package_trees():
        docstrings = _docstring_ids(tree)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and id(node) not in docstrings and node.value not in ALLOWED_VALUES
                    and any(c in node.value for c in UNICODE_DIGIT_CLASSES)):
                offenders.append(f"{rel}:{node.lineno}: {node.value[:60]!r}")
    assert not offenders, (
        "`\\d`/`\\w` casam dígitos de qualquer escrita (`٢٠٢٦`). Usar `[0-9]` / "
        "`[A-Za-z0-9_]`:\n" + "\n".join(offenders))


def test_canario_nenhum_match_no_pacote():
    """`.match` com `$` aceita um `\\n` no fim (`pr-abcdefgh\\n` montava um nome de
    blob). Validação é sempre `fullmatch`."""
    offenders = [f"{rel}:{node.lineno}: {ast.unparse(node.func)}"
                 for rel, tree in _package_trees() for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                 and node.func.attr == "match"]
    assert not offenders, "usar `fullmatch`:\n" + "\n".join(offenders)
