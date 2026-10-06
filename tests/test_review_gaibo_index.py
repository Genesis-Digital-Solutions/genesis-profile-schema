"""
Revisão independente (6 Out 2026) do contrato `gaibo_index` — provas.

Eram `xfail(strict=True)` antes da correção; corrigidos, ficam como testes
normais.
"""
import json

import pytest

from genesis_profile_schema import gaibo_index as gi

KEY = "j-abcdefgh"
SRC = f"gaibo/{KEY}/Relatorio.pdf"
URL = "https://stcliente.blob.core.windows.net/gaibo-sources/j-abcdefgh/Relatorio.pdf"


def _doc(drop=(), **over):
    meta = {"source": SRC, "page": 1, "url": URL, "document_title": "Relatório",
            "document_type": "pdf", "parent_doc_id": gi.parent_doc_id(SRC),
            "global_chunk_index": 0, "origin": "gaibo"}
    doc = {"id": gi.chunk_id(SRC, 1, 0), "content": "t", "metadata": json.dumps(meta),
           "source_file": SRC, "page": 1, "document_title": "Relatório", "url": URL,
           "parent_doc_id": gi.parent_doc_id(SRC), "global_chunk_index": 0,
           "origin": "gaibo", "origin_ref": "run-1", "doc_version": "b" * 64}
    for k in drop:
        doc.pop(k)
    doc.update(over)
    return doc


def test_global_chunk_index_de_topo_obrigatorio():
    assert gi.chunk_problems(_doc(drop=("global_chunk_index",)))


@pytest.mark.parametrize("url", [
    "https://stcliente.blob.core.windows.net/gaibo-sources/../attached-docs/x.pdf",
    "https://stcliente.blob.core.windows.net/gaibo-sources/%2e%2e/attached-docs/x.pdf",
])
def test_url_com_segmentos_de_subida_recusado(url):
    meta = json.loads(_doc()["metadata"])
    meta["url"] = url
    assert gi.chunk_problems(_doc(url=url, metadata=json.dumps(meta)))


@pytest.mark.parametrize("name", ["fatura‮fdp.exe", "a​b.pdf", "x\u0085.pdf"])
def test_nome_com_caracteres_invisiveis_ou_bidi_recusado(name):
    assert gi.file_name_problems(name)


def test_nome_com_ponto_final_recusado():
    # O Blob Storage desaconselha nomes que acabam em '.'.
    assert gi.file_name_problems("relatorio.")
    assert gi.file_name_problems("...")


def test_nome_nao_nfc_recusado():
    assert gi.file_name_problems("Relatório.pdf")       # NFD
    assert gi.file_name_problems("Relatório.pdf") == []


def test_valores_nao_hasheaveis_reportados_sem_rebentar():
    assert gi.chunk_problems(_doc(id=["x"], content_type={"a": 1}))


def test_datas_sem_fuso_recusadas():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        gi.RunReport.model_validate({"run_id": "run-abcdefgh12", "origin_ref": "r",
                                     "started_at": "2026-10-06T10:00:00", "status": "failed"})
