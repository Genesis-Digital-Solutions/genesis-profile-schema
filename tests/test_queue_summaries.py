"""v0.1.157 — `reviewQueues.<fila>.summaryTables`/`summaryTotals`, `actions[].to == "@same"`
e `ingest.internal_domains`. O caso de referência é a forma REAL gravada no perfil
`salmon-comercial-dev` (lida a 5 Nov 2026), que tem de continuar a passar."""

import copy
import unittest

from pydantic import ValidationError

from genesis_profile_schema import ClientProfileSchema, exposure_of, i18n_field_paths
from genesis_profile_schema.client_profile_schema import ProfileIngest, ProfileReviewQueue
from genesis_profile_schema.queue_summaries import SAME_STATE

SALMON_TABLE = {
    "carry": ["taxa_extra_pct"],
    "columnLabels": {"codigo_transporte": {"en": "Service", "pt": "Serviço"},
                     "preco_custo_extra": {"en": "Price/t", "pt": "Preço/t"},
                     "taxa_extra_pct": {"en": "Extra %", "pt": "% extra"},
                     "toneladas": {"en": "Tonnes", "pt": "Toneladas"},
                     "transportador_id": {"en": "Carrier", "pt": "Transportador"},
                     "valor": {"en": "Value (€)", "pt": "Valor (€)"}},
    "editable": ["preco_custo_extra", "taxa_extra_pct"],
    "groupBy": ["codigo_transporte", "preco_custo_extra"],
    "header": ["transportador_id"],
    "hideSourceColumns": ["preco_custo_extra", "taxa_extra_pct"],
    "key": "transporte",
    "label": {"en": "Transport", "pt": "Transporte"},
    "multiply": "preco_custo_extra",
    "requires": ["transportador_id"],
    "source": "artigos",
    "sum": "toneladas",
    "sumWhenSingle": "total_toneladas",
    "valueLabels": {"codigo_transporte": {"920306": "920306 Granel", "920307": "920307 Embalados"}},
}
SALMON_TOTAL = {
    "add": [{"column": "valor", "label": {"en": "Materials", "pt": "Materiais"}, "source": "artigos"},
            {"label": {"en": "Transport", "pt": "Transporte"}, "summary": "transporte"}],
    "field": "valor_total",
    "key": "total_estimado",
}


def _queue(**kw):
    node = {"summaryTables": [copy.deepcopy(SALMON_TABLE)], "summaryTotals": [copy.deepcopy(SALMON_TOTAL)]}
    node.update(kw)
    return node


class SummaryTablesTest(unittest.TestCase):
    def test_forma_real_da_salmon_passa_e_volta_igual(self):
        q = ProfileReviewQueue.model_validate(_queue())
        out = q.model_dump(mode="json", exclude_none=True)
        self.assertEqual(out["summaryTables"][0], SALMON_TABLE)
        self.assertEqual(out["summaryTotals"][0]["add"], SALMON_TOTAL["add"])

    def test_null_e_ausente_sao_nenhum(self):
        # Forma do blob gravado pelo core (to_blob_dict não omite nulos).
        q = ProfileReviewQueue.model_validate({"summaryTables": None, "summaryTotals": None})
        self.assertIsNone(q.summaryTables)
        self.assertIsNone(ProfileReviewQueue.model_validate({}).summaryTotals)

    def test_blob_com_nulos_internos_volta_a_passar(self):
        # Depois do 1.º save validado, as opções vazias ficam a null dentro da entrada.
        q = ProfileReviewQueue.model_validate(_queue())
        again = ProfileReviewQueue.model_validate(q.model_dump(mode="json"))
        self.assertEqual(again.summaryTables[0].key, "transporte")

    def test_obrigatorios(self):
        for k in ("key", "source", "groupBy", "sum"):
            t = copy.deepcopy(SALMON_TABLE)
            t.pop(k)
            with self.assertRaises(ValidationError, msg=k):
                ProfileReviewQueue.model_validate(_queue(summaryTables=[t], summaryTotals=None))

    def test_chave_invalida_e_recusada(self):
        t = copy.deepcopy(SALMON_TABLE)
        t["groupBy"] = ["código transporte"]
        with self.assertRaises(ValidationError):
            ProfileReviewQueue.model_validate(_queue(summaryTables=[t], summaryTotals=None))

    def test_keys_repetidas_e_limite(self):
        with self.assertRaises(ValidationError):
            ProfileReviewQueue.model_validate(
                _queue(summaryTables=[SALMON_TABLE, SALMON_TABLE], summaryTotals=None))
        many = []
        for i in range(6):
            t = copy.deepcopy(SALMON_TABLE)
            t["key"] = f"t{i}"
            many.append(t)
        with self.assertRaises(ValidationError):
            ProfileReviewQueue.model_validate(_queue(summaryTables=many, summaryTotals=None))

    def test_editable_so_groupby_ou_carry(self):
        t = copy.deepcopy(SALMON_TABLE)
        t["editable"] = ["toneladas"]
        with self.assertRaises(ValidationError):
            ProfileReviewQueue.model_validate(_queue(summaryTables=[t], summaryTotals=None))

    def test_rotulo_longo_e_recusado_nao_cortado(self):
        t = copy.deepcopy(SALMON_TABLE)
        t["label"] = "x" * 81
        with self.assertRaises(ValidationError):
            ProfileReviewQueue.model_validate(_queue(summaryTables=[t], summaryTotals=None))


class SummaryTotalsTest(unittest.TestCase):
    def test_parte_summary_tem_de_nomear_tabela(self):
        with self.assertRaises(ValidationError):
            ProfileReviewQueue.model_validate(_queue(summaryTables=None))

    def test_parte_ambigua(self):
        tot = copy.deepcopy(SALMON_TOTAL)
        tot["add"] = [{"source": "artigos", "column": "valor", "summary": "transporte"}]
        with self.assertRaises(ValidationError):
            ProfileReviewQueue.model_validate(_queue(summaryTotals=[tot]))
        tot["add"] = [{"source": "artigos"}]
        with self.assertRaises(ValidationError):
            ProfileReviewQueue.model_validate(_queue(summaryTotals=[tot]))

    def test_after_ou_field(self):
        tot = copy.deepcopy(SALMON_TOTAL)
        tot.pop("field")
        with self.assertRaises(ValidationError):
            ProfileReviewQueue.model_validate(_queue(summaryTotals=[tot]))
        tot["after"] = "artigos"
        ProfileReviewQueue.model_validate(_queue(summaryTotals=[tot]))

    def test_field_interno_recusado(self):
        tot = copy.deepcopy(SALMON_TOTAL)
        tot["field"] = "_total"
        with self.assertRaises(ValidationError):
            ProfileReviewQueue.model_validate(_queue(summaryTotals=[tot]))

    def test_references(self):
        tot = copy.deepcopy(SALMON_TOTAL)
        tot["references"] = [{"field": "valor_total_cliente", "label": "Total no pedido"}]
        q = ProfileReviewQueue.model_validate(_queue(summaryTotals=[tot]))
        self.assertEqual(q.summaryTotals[0].references[0].field, "valor_total_cliente")


class SameStateTest(unittest.TestCase):
    def test_same_aceite_no_to(self):
        self.assertEqual(SAME_STATE, "@same")
        q = ProfileReviewQueue.model_validate({
            "states": [{"id": "new", "kind": "open"}, {"id": "done", "kind": "final"}],
            "actions": [{"id": "recheck", "from": ["new"], "to": "@same"},
                        {"id": "close", "from": ["new"], "to": "done"}]})
        self.assertEqual(q.actions[0].to, "@same")


class InternalDomainsTest(unittest.TestCase):
    def test_normaliza_como_o_core(self):
        ing = ProfileIngest.model_validate({"internal_domains": ["@Salmon.PT.", "salmon.pt", " grupo.salmon.pt "]})
        self.assertEqual(ing.internal_domains, ["salmon.pt", "grupo.salmon.pt"])

    def test_invalido_recusado(self):
        for bad in (["salmon"], ["sal mon.pt"], "salmon.pt", ["https://salmon.pt"]):
            with self.assertRaises(ValidationError, msg=bad):
                ProfileIngest.model_validate({"internal_domains": bad})

    def test_acentos_e_sublinhado_passam_como_no_core(self):
        ing = ProfileIngest.model_validate({"internal_domains": ["câmara.pt", "a_b.empresa.pt"]})
        self.assertEqual(ing.internal_domains, ["câmara.pt", "a_b.empresa.pt"])

    def test_null(self):
        self.assertIsNone(ProfileIngest.model_validate({"internal_domains": None}).internal_domains)

    def test_exposicao_interna(self):
        self.assertEqual(exposure_of("ingest.internal_domains"), "internal")


class I18nTest(unittest.TestCase):
    def test_rotulos_sao_multilingues_e_mapas_de_colunas_nao(self):
        paths = i18n_field_paths()
        self.assertIn("reviewQueues.*.summaryTables.label", paths)
        self.assertIn("reviewQueues.*.summaryTotals.label", paths)
        self.assertIn("reviewQueues.*.summaryTotals.add.label", paths)
        self.assertNotIn("reviewQueues.*.summaryTables.columnLabels", paths)


class FullProfileTest(unittest.TestCase):
    def test_perfil_completo(self):
        ClientProfileSchema.model_validate({
            "reviewQueues": {"encomendas_venda": _queue()},
            "ingest": {"internal_domains": ["salmon.pt"], "sources": []}})


if __name__ == "__main__":
    unittest.main()
