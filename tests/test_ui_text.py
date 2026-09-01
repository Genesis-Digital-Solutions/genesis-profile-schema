"""
Gate do catálogo de texto (`genesis_profile_schema/ui_text/*.json`).

A promessa é de COBERTURA, não de qualidade da prosa: um campo novo no
contrato não pode chegar a um backoffice com o nome cru, e uma língua não pode
ficar para trás da outra em silêncio. As duas coisas aconteciam antes de este
catálogo existir.

A regra de `help` é deliberadamente estreita. Exige-se ajuda onde o rótulo não
chega — interruptores e números visíveis ao cliente, onde o nome não diz o que
acontece nem em que unidade. Não se exige em cores, nomes e textos, onde a
ajuda obrigatória só produziria enchimento ("Cor de fundo: a cor de fundo").
"""

import json
import os

import pytest

from genesis_profile_schema import exposure as exp
from genesis_profile_schema import ui_text as ui

KNOB_TYPES = ("boolean", "integer", "number")


def _leaf_kinds():
    """{caminho: 'knob' | 'enum' | 'outro'} para as folhas do schema."""
    enums = exp.enum_members()
    from genesis_profile_schema.client_profile_schema import ClientProfileSchema

    js = ClientProfileSchema.model_json_schema()
    defs = js.get("$defs", {})

    def resolve(node):
        seen = 0
        while isinstance(node, dict) and "$ref" in node and seen < 32:
            base = dict(defs.get(node["$ref"].split("/")[-1], {}))
            base.update({k: v for k, v in node.items() if k != "$ref"})
            node = base
            seen += 1
        return node

    kinds = {}
    for path in exp.leaf_paths():
        if path in enums:
            kinds[path] = "enum"
            continue
        node = js
        ok = True
        for seg in path.split("."):
            node = resolve(node)
            props = node.get("properties") or {}
            if seg in props:
                node = props[seg]
                continue
            item = resolve(resolve(node).get("items", {}))
            if seg in (item.get("properties") or {}):
                node = item["properties"][seg]
                continue
            ok = False
            break
        if not ok:
            kinds[path] = "outro"
            continue
        node = resolve(node)
        alts = [a for a in node.get("anyOf", []) + node.get("oneOf", [])
                if resolve(a).get("type") != "null"]
        shape = resolve(alts[0]) if alts else node
        kinds[path] = "knob" if shape.get("type") in KNOB_TYPES else "outro"
    return kinds


LEAF_KINDS = _leaf_kinds()


@pytest.mark.parametrize("locale", ui.LOCALES)
def test_catalogo_carrega_e_declara_a_propria_lingua(locale):
    path = os.path.join(os.path.dirname(ui.__file__), "ui_text", locale + ".json")
    assert os.path.exists(path), f"catálogo em falta: {path}"
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    assert payload.get("locale") == locale
    assert ui.catalogue(locale), "catálogo carregou vazio"


@pytest.mark.parametrize("locale", ui.LOCALES)
def test_toda_a_folha_tem_nome(locale):
    faltam = sorted(p for p in exp.leaf_paths() if not ui.label_of(p, locale))
    assert faltam == [], (
        f"{len(faltam)} campo(s) sem label em {locale}: {faltam[:12]}… "
        "Sem label, o backoffice mostra o caminho cru ao utilizador."
    )


@pytest.mark.parametrize("locale", ui.LOCALES)
def test_interruptores_e_numeros_visiveis_tem_ajuda(locale):
    faltam = sorted(
        p for p in exp.leaf_paths()
        if exp.is_client_visible(p) and LEAF_KINDS.get(p) == "knob"
        and not ui.help_of(p, locale)
    )
    assert faltam == [], (
        f"{len(faltam)} interruptor(es)/número(s) visível(eis) ao cliente sem ajuda "
        f"em {locale}: {faltam[:12]}…"
    )


@pytest.mark.parametrize("locale", ui.LOCALES)
def test_listas_fechadas_visiveis_tem_os_valores_nomeados(locale):
    """Nos DOIS sentidos: um membro novo no schema chumba aqui em vez de
    aparecer como opção sem nome, e um membro removido deixa de ter texto
    órfão a sugerir uma escolha que já não existe."""
    problemas = []
    for path, membros in exp.enum_members().items():
        if not exp.is_client_visible(path):
            continue
        nomeados = ui.options_of(path, locale)
        em_falta = [m for m in membros if m not in nomeados]
        a_mais = [m for m in nomeados if m not in membros]
        if em_falta or a_mais:
            problemas.append((path, {"sem nome": em_falta, "já não existem": a_mais}))
    assert problemas == [], f"opções desalinhadas com o schema em {locale}: {problemas}"


def test_as_duas_linguas_cobrem_os_mesmos_campos():
    pt = set(ui.catalogue("pt-PT"))
    en = set(ui.catalogue("en-GB"))
    assert pt == en, (
        f"só em pt-PT: {sorted(pt - en)[:10]} | só em en-GB: {sorted(en - pt)[:10]}"
    )


@pytest.mark.parametrize("locale", ui.LOCALES)
def test_catalogo_sem_entradas_mortas(locale):
    """Mesma regra do exposure: entrada válida é folha, antepassado de folha
    (os cartões de grupo) ou algo dentro de um mapa aberto."""
    leaves = set(exp.leaf_paths())
    maps = exp.open_map_paths()
    ancestors = {".".join(p.split(".")[:i]) for p in leaves for i in range(1, len(p.split(".")))}
    mortas = sorted(
        p for p in ui.catalogue(locale)
        if p not in leaves and p not in ancestors
        and not any(p.startswith(m + ".") for m in maps)
    )
    assert mortas == [], f"entradas que já não correspondem ao schema em {locale}: {mortas}"


@pytest.mark.parametrize("locale", ui.LOCALES)
def test_registos_bem_formados(locale):
    permitidas = set(ui.entry_keys())
    for path, rec in ui.catalogue(locale).items():
        assert isinstance(rec, dict), path
        extra = set(rec) - permitidas
        assert not extra, f"{path}: chaves não previstas {extra}"
        for key in ("label", "help", "note"):
            if key in rec:
                assert isinstance(rec[key], str) and rec[key].strip(), f"{path}.{key} vazio"
        if "options" in rec:
            assert isinstance(rec["options"], dict) and rec["options"], f"{path}.options vazio"
            for value, name in rec["options"].items():
                assert isinstance(name, str) and name.strip(), f"{path}.options.{value} vazio"


def test_ausencia_de_catalogo_nao_rebenta():
    """Texto de interface nunca derruba um serviço."""
    assert ui.catalogue("xx-YY") == {}
    assert ui.label_of("identity.assistant_name", "xx-YY") is None
    assert ui.options_of("caminho.que.nao.existe") == {}
    assert ui.text_for("caminho.que.nao.existe") == {}


def test_indices_normalizados_como_no_exposure():
    assert ui.label_of("retrieval.indexes.0.name") == ui.label_of("retrieval.indexes.name")


def test_campos_internos_nao_precisam_de_voz_de_cliente():
    """Não é uma regra de estilo: é a razão de `note` existir. Pelo menos os
    campos mais sensíveis têm nota de operador escrita."""
    for path in ("frontend.csp.extraScriptSrc", "retrieval.weak_grounding_ceiling",
                 "reviewQueues", "pricing.usd_to_eur"):
        for locale in ui.LOCALES:
            assert ui.note_of(path, locale), f"{path} sem nota de operador em {locale}"


# ─────────────────────────────────────────────────────────────────────────────
# Projecção para dentro do JSON Schema
#
# Existe porque um consumidor que só saiba ler `model_json_schema()` não vê o
# catálogo. Projectar mantém uma fonte única; escrever o texto também no
# modelo criava a segunda cópia que este catálogo veio eliminar.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("locale", ui.LOCALES)
def test_projeccao_poe_o_texto_no_esquema(locale):
    schema = ui.annotated_json_schema(locale)
    ident = schema["$defs"]["ProfileIdentity"]["properties"]
    assert ident["assistant_name"]["title"] == ui.label_of("identity.assistant_name", locale)
    assert ident["register"]["description"] == ui.help_of("identity.register", locale)
    assert ident["register"]["x-genesis-option-labels"] == ui.options_of("identity.register", locale)


def test_projeccao_nao_toca_no_esquema_original():
    """O contrato que o core valida tem de continuar a ser exactamente o mesmo."""
    from genesis_profile_schema.client_profile_schema import ClientProfileSchema

    ui.annotated_json_schema("pt-PT")
    raw = ClientProfileSchema.model_json_schema()
    com_texto = [
        (nome, prop)
        for nome, definicao in raw.get("$defs", {}).items()
        for prop, valor in (definicao.get("properties") or {}).items()
        if isinstance(valor, dict) and ("description" in valor or "x-genesis-option-labels" in valor)
    ]
    assert com_texto == [], f"a projecção sujou o esquema original: {com_texto[:5]}"


def test_projeccao_nao_mistura_linguas():
    pt = ui.annotated_json_schema("pt-PT")["$defs"]["ProfileIdentity"]["properties"]
    en = ui.annotated_json_schema("en-GB")["$defs"]["ProfileIdentity"]["properties"]
    assert pt["assistant_name"]["title"] != en["assistant_name"]["title"]


def test_quem_recebe_a_projeccao_nao_estraga_a_cache():
    schema = ui.annotated_json_schema("pt-PT")
    schema["$defs"]["ProfileIdentity"]["properties"]["assistant_name"]["title"] = "MEXIDO"
    de_novo = ui.annotated_json_schema("pt-PT")
    assert de_novo["$defs"]["ProfileIdentity"]["properties"]["assistant_name"]["title"] != "MEXIDO"


@pytest.mark.parametrize("locale", ui.LOCALES)
def test_nos_partilhados_ou_concordam_ou_ficam_por_anotar(locale):
    """`ProfileFrontendThemeMode` é o mesmo modelo em `theme.light` e
    `theme.dark`. Hoje os textos coincidem e por isso não há conflito — se
    alguém os diferenciar, aparecem aqui em vez de um sobrepor o outro."""
    conflitos = ui.annotation_conflicts(locale)
    schema = ui.annotated_json_schema(locale)
    tema = schema["$defs"].get("ProfileFrontendThemeMode", {}).get("properties", {})
    if conflitos:
        for path in conflitos:
            folha = path.split(".")[-1]
            assert "description" not in tema.get(folha, {}), (
                f"'{path}' está em conflito e mesmo assim foi anotado"
            )
    else:
        assert ui.label_of("frontend.branding.theme.light.bgPage", locale) == \
               ui.label_of("frontend.branding.theme.dark.bgPage", locale)


def test_a_nota_de_operador_nao_vai_na_projeccao():
    """O JSON Schema é servido a quem não deve ler detalhe interno."""
    import json

    despejo = json.dumps(ui.annotated_json_schema("pt-PT"), ensure_ascii=False)
    nota = ui.note_of("retrieval.weak_grounding_ceiling", "pt-PT")
    assert nota and nota not in despejo
