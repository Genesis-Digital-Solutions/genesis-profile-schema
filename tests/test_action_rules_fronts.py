"""v0.1.180 (F-S173 do Studio, 25 Nov 2026): «Só nestes assistentes» (`actionRules.rules[].variants`).

Uma frente mal escrita (`lojaa` em vez de `loja`) deixava a regra sem efeito em frente nenhuma — falha ABERTA (na
`loja` a ação ficava sem a aprovação que o cliente pôs). Agora é ERRO: forma inválida (`invalid_front`) ou slug que
não é variante do cliente (`unknown_front`, contra `multiProfile.slugs` + `disabledSlugs`)."""
from genesis_profile_schema import action_rules as ar


def _profile(variants, multi=None):
    p = {"actionRules": {"enabled": True, "rules": [
        {"id": "r1", "action": "create_ticket", "mode": "block", "variants": variants}]}}
    if multi is not None:
        p["multiProfile"] = multi
    return p


def _problems(profile, **kw):
    return [(p["rule_id"], p["code"], p["severity"]) for p in ar.action_rules_problems(profile, **kw)
            if p["code"] in (ar.INVALID_FRONT, ar.UNKNOWN_FRONT)]


MULTI = {"enabled": True, "slugs": ["loja", "rh"], "disabledSlugs": ["antiga"]}


def test_all_base_and_existing_slugs_are_valid():
    for v in ([], None, ["*"], ["_base"], ["loja"], ["LOJA "], ["rh", "_base"], ["antiga"]):
        assert _problems(_profile(v, MULTI)) == [], v


def test_misspelled_front_is_an_error():
    assert _problems(_profile(["lojaa"], MULTI)) == [("r1", ar.UNKNOWN_FRONT, ar.ERROR)]
    # várias mal escritas → um só problema por código e regra
    assert _problems(_profile(["lojaa", "rhh"], MULTI)) == [("r1", ar.UNKNOWN_FRONT, ar.ERROR)]


def test_bad_form_is_an_error_even_without_knowing_the_fronts():
    for v in (["Loja X"], ["loja,rh"], ["-loja"], ["base*"], [5], "loja", {"loja": 1}):
        assert _problems(_profile(v)) == [("r1", ar.INVALID_FRONT, ar.ERROR)], v


def test_slug_too_long_is_invalid():
    assert _problems(_profile(["a" * 41], MULTI)) == [("r1", ar.INVALID_FRONT, ar.ERROR)]
    assert _problems(_profile(["a" * 40], {"slugs": ["a" * 40]})) == []


def test_without_multiprofile_block_only_the_form_is_checked():
    # A camada de uma variante não traz `multiProfile`: «não sei» nunca vira «não existe».
    assert _problems(_profile(["loja"])) == []


def test_main_profile_without_variants_refuses_any_slug():
    # Bloco presente sem variantes (multi-perfil nunca ligado): só `_base`/`*`/vazio valem.
    multi = {"enabled": False, "slugs": [], "disabledSlugs": []}
    assert _problems(_profile(["_base"], multi)) == []
    assert _problems(_profile(["loja"], multi)) == [("r1", ar.UNKNOWN_FRONT, ar.ERROR)]


def test_known_fronts_argument_wins_over_the_profile():
    # Quem valida a camada de uma variante passa as frentes do principal.
    assert _problems(_profile(["loja"]), known_fronts=["loja"]) == []
    assert _problems(_profile(["lojaa"]), known_fronts=["loja"]) == [("r1", ar.UNKNOWN_FRONT, ar.ERROR)]
    assert _problems(_profile(["loja"], MULTI), known_fronts=[]) == [("r1", ar.UNKNOWN_FRONT, ar.ERROR)]


def test_known_fronts_of():
    assert ar.known_fronts_of({"multiProfile": MULTI}) == ["loja", "rh", "antiga"]
    assert ar.known_fronts_of({}) is None
    assert ar.known_fronts_of({"multiProfile": None}) is None
    assert ar.known_fronts_of({"multiProfile": {"slugs": "loja"}}) == []
    assert ar.known_fronts_of(None) is None


def test_never_raises_on_garbage():
    assert ar.known_fronts_of({"multiProfile": {"slugs": [None, 3, " Loja "]}}) == ["3", "loja"]
    ar.action_rules_problems({"actionRules": {"rules": [{"id": "r1", "action": "x", "variants": [object()]}]},
                              "multiProfile": MULTI})


def test_fleet_shapes_measured_on_25_nov_stay_valid():
    # Medido a 25 Nov 2026 (find_clients_by_profile): só demogenweb001-dev (variants []) e genpolar-dev
    # (variants ["_base"], multi-perfil desligado sem slugs) têm regras.
    assert _problems(_profile([], {"enabled": True, "slugs": ["triagemcv", "verdocs", "atas", "concursos"],
                                   "disabledSlugs": []})) == []
    assert _problems(_profile(["_base"], {"enabled": False, "slugs": [], "disabledSlugs": []})) == []


def test_help_fits_the_gaibo_popover():
    from genesis_profile_schema.ui_text import text_for
    for loc in ("pt-PT", "en-GB"):
        t = text_for("actionRules.rules.variants", loc)
        assert t and t.get("label") and 0 < len(t.get("help") or "") <= 240


def test_variant_layer_only_its_own_slug():
    # No core a lista `actionRules.rules` da camada SUBSTITUI a do principal e corre só com o slug dela:
    # `_base` e as outras frentes nunca se aplicariam lá.
    for v in ([], None, ["*"], ["loja"], ["LOJA"]):
        assert _problems(_profile(v), layer_slug="loja") == [], v
    for v in (["_base"], ["rh"], ["loja", "rh"], ["loja", "_base"]):
        assert _problems(_profile(v), layer_slug="loja") == [("r1", ar.UNKNOWN_FRONT, ar.ERROR)], v
    assert _problems(_profile(["Mau X"]), layer_slug="loja") == [("r1", ar.INVALID_FRONT, ar.ERROR)]
    # o slug da camada ganha à lista do principal
    assert _problems(_profile(["rh"], MULTI), known_fronts=["rh"], layer_slug="loja") == [
        ("r1", ar.UNKNOWN_FRONT, ar.ERROR)]


def test_front_problems_allow_base():
    assert ar.front_problems(["_base"], ["loja"]) == []
    assert ar.front_problems(["_base"], ["loja"], allow_base=False) == [ar.UNKNOWN_FRONT]
    assert ar.front_problems(["_base"], None, allow_base=False) == [ar.UNKNOWN_FRONT]
