"""Contrato da indexação pelo GAIBO (v0.1.92)."""

import json
import re
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from genesis_profile_schema import gaibo_index as gi

KEY = "j-abcdefgh"
SRC = f"gaibo/{KEY}/Relatorio 2025.pdf"
URL = "https://stcliente.blob.core.windows.net/gaibo-sources/j-abcdefgh/Relatorio%202025.pdf#page=3"


def _doc(**over):
    meta = {
        "source": SRC, "page": 3, "url": URL, "document_title": "Relatório 2025",
        "document_type": "pdf", "parent_doc_id": gi.parent_doc_id(SRC),
        "global_chunk_index": 0, "origin": "gaibo",
    }
    doc = {
        "id": gi.chunk_id(SRC, 3, 0), "content": "texto", "metadata": json.dumps(meta),
        "source_file": SRC, "page": 3, "document_title": "Relatório 2025",
        "url": URL, "parent_doc_id": gi.parent_doc_id(SRC), "global_chunk_index": 0,
        "origin": "gaibo", "origin_ref": "run-1", "doc_version": "a" * 64,
    }
    doc.update(over)
    return doc


def test_conforming_chunk_has_no_problems():
    assert gi.chunk_problems(_doc()) == []


def test_source_file_round_trip_and_display():
    assert gi.source_file_for(KEY, "Relatorio 2025.pdf") == SRC
    assert gi.parse_source_file(SRC) == (KEY, "Relatorio 2025.pdf")
    assert gi.display_name(SRC) == "Relatorio 2025.pdf"
    assert gi.display_name("pasta/Studio.pdf") == "pasta/Studio.pdf"
    assert not gi.is_gaibo_source("Relatorio 2025.pdf")


@pytest.mark.parametrize("key", ["j-2026abcd", "abcdefgh", "j-ABCDEFGH", "j-abc", "j-abcdefg1"])
def test_bad_doc_keys(key):
    assert not gi.is_valid_doc_key(key)


def test_doc_key_alphabet_cannot_look_like_a_year():
    # base32 minúsculo sem 0/1/8/9 → nenhuma sequência 19xx/20xx é possível
    alphabet = "abcdefghijklmnopqrstuvwxyz234567"
    assert not re.search(r"(19|20)\d\d", alphabet)
    assert not set("0189") & set(alphabet)


@pytest.mark.parametrize("name", ["a/b.pdf", "a\\b.pdf", "50%.pdf", " x.pdf", "..", "x" * 201, ""])
def test_bad_file_names(name):
    assert gi.file_name_problems(name)


def test_chunk_id_is_studio_formula_with_prefix():
    import hashlib
    assert gi.chunk_id(SRC, 3, 0) == "gaibo_" + hashlib.md5(f"{SRC}_3_0".encode()).hexdigest()


@pytest.mark.parametrize("over,needle", [
    ({"metadata": None}, "metadata"),
    ({"metadata": "{"}, "metadata"),
    ({"origin": None}, "origin"),
    ({"id": "genesis_meta"}, "id"),
    ({"source_file": "Relatorio.pdf"}, "source_file"),
    ({"content_type": "dataset_catalog"}, "content_type"),
    ({"document_title": ""}, "document_title"),
    ({"url": URL.replace("#page=3", "?sv=x&sig=y")}, "SAS"),
    ({"url": URL.replace("gaibo-sources", "input")}, "contentor"),
    ({"migrated_from": "x"}, "campos não permitidos"),
    ({"doc_version": "abc"}, "doc_version"),
    ({"doc_version": None}, "doc_version"),
])
def test_problems_detected(over, needle):
    problems = gi.chunk_problems(_doc(**over))
    assert any(needle in p for p in problems), problems


def test_metadata_must_mirror_top_level():
    meta = json.loads(_doc()["metadata"])
    meta["source"] = "Relatorio 2025.pdf"
    problems = gi.chunk_problems(_doc(metadata=json.dumps(meta)))
    assert any("metadata.source" in p for p in problems)
    meta = json.loads(_doc()["metadata"])
    meta["tier"] = "internal"
    assert any("tier" in p for p in gi.chunk_problems(_doc(metadata=json.dumps(meta))))


def _req(**over):
    data = {
        "request_id": "pr-abcdefgh12", "client_id": "genesis-ai-dev",
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "requested_by_ref": "audit-123",
        "items": [
            {"source_file": SRC, "action": "publish", "origin_ref": "run-1", "chunk_count": 4},
            {"source_file": f"gaibo/{KEY}x/Velho.pdf", "action": "remove"},
        ],
    }
    data.update(over)
    return data


def test_publish_request_valid():
    req = gi.PublishRequest.model_validate(_req())
    assert len(req.items) == 2 and req.schema_version == 1


@pytest.mark.parametrize("items", [
    [{"source_file": SRC, "action": "publish", "chunk_count": 4}],                  # sem origin_ref
    [{"source_file": SRC, "action": "publish", "origin_ref": "run-1"}],            # sem chunk_count
    [{"source_file": SRC, "action": "remove", "origin_ref": "run-1"}],             # remove com ref
    [{"source_file": "Relatorio.pdf", "action": "remove"}],                         # não é do GAIBO
    [{"source_file": SRC, "action": "remove"}, {"source_file": SRC, "action": "remove"}],
    [],
])
def test_publish_request_invalid(items):
    with pytest.raises(ValidationError):
        gi.PublishRequest.model_validate(_req(items=items))


def test_unknown_fields_refused():
    with pytest.raises(ValidationError):
        gi.PublishRequest.model_validate(_req(extra=1))


def test_blob_paths_validate_ids():
    assert gi.request_blob("pr-abcdefgh12") == "requests/pr-abcdefgh12.json"
    assert gi.result_blob("pr-abcdefgh12") == "results/pr-abcdefgh12.json"
    assert gi.run_blob("run-abcdefgh12") == "runs/run-abcdefgh12.json"
    for bad in ("../x", "pr-ABC", ""):
        with pytest.raises(ValueError):
            gi.request_blob(bad)


def test_settings_defaults_off_and_extensions_normalised():
    s = gi.GaiboSettings()
    assert s.enabled is False and s.auto_approve is False
    s = gi.GaiboSettings(allowed_extensions=[".PDF", ".pdf", ".docx"])
    assert s.allowed_extensions == [".pdf", ".docx"]
    with pytest.raises(ValidationError):
        gi.GaiboSettings(allowed_extensions=["pdf"])
    ent = gi.TIER_DEFAULTS["enterprise"]
    assert ent["enabled"] is True and ent["max_documents"] is None
    assert ent["max_documents_per_month"] is None and ".pdf" in ent["allowed_extensions"]


def test_settings_core_urls_are_https_origins():
    s = gi.GaiboSettings()
    assert s.dev_core_url == "" and s.prod_core_url == ""
    s = gi.GaiboSettings(dev_core_url="https://Core-Dev.example.azurecontainerapps.io/",
                         prod_core_url="https://core.example.io:8443")
    assert s.dev_core_url == "https://core-dev.example.azurecontainerapps.io"
    assert s.prod_core_url == "https://core.example.io:8443"
    for bad in ("http://core.example.io", "https://core.example.io/api",
                "https://core.example.io/?x=1", "https://core.example.io#f",
                "https://user@core.example.io", "https://", "core.example.io",
                "https://" + "a" * 260 + ".io"):
        with pytest.raises(ValidationError):
            gi.GaiboSettings(dev_core_url=bad)
    # Fechado: um campo desconhecido continua a ser recusado.
    with pytest.raises(ValidationError):
        gi.GaiboSettings(core_url="https://core.example.io")


def test_run_report():
    rep = gi.RunReport.model_validate({
        "run_id": "run-abcdefgh12", "origin_ref": "run-abcdefgh12",
        "started_at": "2026-10-06T10:00:00Z", "status": "succeeded",
        "documents": [{"source_file": SRC, "action": "indexed", "chunks": 4}],
        "di_pages_layout": 12, "embedding_tokens": 3000,
    })
    assert rep.di_pages_layout == 12


def test_package_data_and_subpackage_declared():
    # o subpacote tem de ir no wheel (packages explícitos no pyproject)
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    assert "genesis_profile_schema.gaibo_index" in text


def test_monthly_limit_and_unlock_v0_1_101():
    s = gi.GaiboSettings(max_documents_per_month=100, extra_documents=40,
                         extra_documents_month="2026-10")
    assert s.monthly_allowance("2026-10") == 140      # desbloqueio vale só nesse mês
    assert s.monthly_allowance("2026-11") == 100      # caduca sozinho
    assert gi.GaiboSettings().monthly_allowance("2026-10") is None   # sem limite
    with pytest.raises(ValidationError):
        gi.GaiboSettings(extra_documents_month="2026-13")
    with pytest.raises(ValidationError):
        gi.GaiboSettings(extra_documents=-1)


def test_client_resource_endpoints_are_https_origins():
    s = gi.GaiboSettings(aoai_endpoint="https://oai-x.cognitiveservices.azure.com/",
                         di_endpoint="https://oai-x.cognitiveservices.azure.com",
                         enrichment_deployment="gpt-4.1-mini")
    assert s.aoai_endpoint == s.di_endpoint == "https://oai-x.cognitiveservices.azure.com"
    with pytest.raises(ValidationError):
        gi.GaiboSettings(di_endpoint="http://x.cognitiveservices.azure.com")


def test_internal_plans_defaults():
    td = gi.TIER_DEFAULTS
    assert td["demo"]["max_documents"] == td["starter"]["max_documents"] == 100
    assert td["pilot"]["max_documents"] == td["professional"]["max_documents"] == 1000
    assert td["internal"]["max_documents"] is None and td["internal"]["max_documents_per_month"] is None
    for name, d in td.items():
        assert "max_documents_per_month" in d, name


def test_di_model_by_plan_and_extraction():
    td = gi.TIER_DEFAULTS
    assert td["starter"]["di_model"] == td["demo"]["di_model"] == "read"
    for name in ("professional", "pilot", "internal", "enterprise"):
        assert td[name]["di_model"] == "layout", name
    for name, d in td.items():
        gi.GaiboSettings(**d)  # todos os defaults validam no modelo
    # settings.json antigo, sem o campo → Layout (o comportamento de antes)
    assert gi.GaiboSettings().di_model == "layout"
    with pytest.raises(ValidationError):
        gi.GaiboSettings(di_model="ocr")
    read = gi.GaiboSettings(di_model="read")
    assert read.extraction_for(".PDF") == "prebuilt-read"
    assert read.extraction_for(".png") == "prebuilt-read"
    assert read.extraction_for(".docx") == "prebuilt-read"
    assert read.extraction_for(".md") == "text"
    layout = gi.GaiboSettings()
    assert layout.extraction_for(".pdf") == "prebuilt-layout"
    assert layout.extraction_for(".docx") == "prebuilt-read"
    with pytest.raises(ValueError):
        layout.extraction_for(".exe")
    with pytest.raises(ValueError):
        gi.extraction_for(".pdf", "ocr")


def test_v0_1_103_validators_settings_keys_and_reindexed():
    assert gi.is_valid_origin_ref("run_1-A") and not gi.is_valid_origin_ref("a b")
    assert not gi.is_valid_origin_ref("x" * 65) and not gi.is_valid_origin_ref(None)
    assert gi.is_valid_request_id("pr-abcdefgh01") and not gi.is_valid_request_id("pr-ABCDEFGH01")
    assert gi.is_valid_run_id("run-abcdefgh01") and not gi.is_valid_run_id("pr-abcdefgh01")
    full = gi.GaiboSettings().model_dump(mode="json")
    assert gi.settings_missing_keys(full) == []           # o modelo inteiro (o que o Studio grava)
    del full["max_documents"]
    assert gi.settings_missing_keys(full) == ["max_documents"]
    assert gi.settings_missing_keys(None) == list(gi.REQUIRED_SETTINGS_KEYS)
    doc = gi.RunDocument(source_file=gi.source_file_for("j-abcdefgh", "a.pdf"), action="reindexed")
    assert doc.action == "reindexed"
