"""v0.1.106 (13 Out 2026): o destino da transferência de chamada.

O número do cliente aceita só telefone; destinos SIP só no campo interno."""
from genesis_profile_schema import transfer_target as tt
from genesis_profile_schema.client_profile_schema import ClientProfileSchema
from genesis_profile_schema.exposure import EXPOSURE


def test_phone_forms():
    assert tt.phone_target("+351210000000") == ("tel:+351210000000", None)
    assert tt.phone_target(" +351 21 000 00 00 ") == ("tel:+351210000000", None)
    assert tt.phone_target("tel:+351-21-000-0000") == ("tel:+351210000000", None)
    assert tt.phone_target("500") == ("tel:500", None)                  # extensão
    assert tt.phone_target("(21) 000.0000") == ("tel:210000000", tt.NO_PLUS)
    assert tt.phone_target("") == ("", None)
    assert tt.phone_target(None) == ("", None)


def test_phone_refuses_sip_and_garbage():
    assert tt.phone_target("sip:500@evil.example") == ("", tt.SIP_STUDIO_ONLY)
    assert tt.phone_target("SIP:500@evil.example") == ("", tt.SIP_STUDIO_ONLY)
    for bad in ("+0123456789", "+351", "1", "abc", "+351210000000;x=1",
                "tel:+351210000000?h=1", "+3512100000001234567", "sips:1@a.b"):
        assert tt.phone_target(bad) == ("", tt.INVALID), bad


def test_sip_grammar_is_an_allowlist():
    ok = ["sip:500@pbx.cliente.pt", "sip:500@pbx.cliente.pt;transport=tls",
          "sip:pbx.cliente.pt:5061", "sip:+351210000000@10.0.0.4;user=phone;transport=tcp",
          "SIP:500@pbx.cliente.pt"]
    for v in ok:
        uri, problem = tt.sip_target(v)
        assert problem is None and uri.startswith("sip:"), v
    for v in ("sip:500@pbx;transport=tls", "sip:500@pbx.cliente.pt?Replaces=x",
              "sip:500@pbx.cliente.pt;maddr=evil.example", "sip:a b@pbx.cliente.pt",
              "tel:+351210000000", "https://pbx.cliente.pt", "sip:@pbx.cliente.pt"):
        assert tt.sip_target(v) == ("", tt.INVALID_SIP), v


def test_only_ascii_and_real_ranges():
    """Revisão M2: dígitos e letras não-ASCII recusados (o espelho JS também
    os recusa); octetos e porta dentro dos limites."""
    assert tt.phone_target("\u0665\u0660\u0660") == ("", tt.INVALID)          # ٥٠٠
    assert tt.sip_target("sip:500@pbx.cliente.\u212apt") == ("", tt.INVALID_SIP)  # K Kelvin
    assert tt.sip_target("sip:500@\u0661\u0660.0.0.4") == ("", tt.INVALID_SIP)
    assert tt.sip_target("sip:500@10.0.0.256") == ("", tt.INVALID_SIP)
    assert tt.sip_target("sip:500@pbx.cliente.pt:65536") == ("", tt.INVALID_SIP)
    assert tt.sip_target("sip:500@pbx.cliente.pt:0") == ("", tt.INVALID_SIP)
    assert tt.sip_target("sip:500@10.0.0.255:5061")[1] is None


def test_sip_wins_and_bad_sip_falls_back_to_the_number():
    assert tt.voice_transfer_target({"transfer_number": "+351210000000",
                                     "transfer_sip_uri": "sip:500@pbx.cliente.pt"}) == \
        ("sip:500@pbx.cliente.pt", None, "sip")
    assert tt.voice_transfer_target({"transfer_number": "+351210000000",
                                     "transfer_sip_uri": "sip:500@pbx"}) == \
        ("tel:+351210000000", tt.INVALID_SIP, "number")
    assert tt.voice_transfer_target({"transfer_number": "sip:1@evil.example"}) == \
        ("", tt.SIP_STUDIO_ONLY, "")
    assert tt.voice_transfer_target({}) == ("", None, "")
    # também sobre o modelo
    v = ClientProfileSchema.model_validate({"voice": {"transfer_number": "500"}}).voice
    assert tt.voice_transfer_target(v) == ("tel:500", None, "number")


def test_fields_and_exposure():
    v = ClientProfileSchema().voice
    assert v.transfer_number == "" and v.transfer_sip_uri == ""
    # um valor mau nunca impede o perfil de carregar
    bad = ClientProfileSchema.model_validate({"voice": {"transfer_number": "sip:x@y.z",
                                                        "transfer_sip_uri": "lixo"}})
    assert bad.voice.transfer_sip_uri == "lixo"
    assert EXPOSURE["voice.transfer_number"] == "client_write"
    assert EXPOSURE["voice.transfer_sip_uri"] == "internal"


# ── v0.1.107: vários destinos ─────────────────────────────────────────────

def _t(**kw):
    base = {"id": "faturacao", "label": "Faturação", "description": "faturas e pagamentos",
            "number": "+351210000001"}
    base.update(kw)
    return base


def test_targets_resolve_and_one_default():
    v = {"transfer_targets": [_t(), _t(id="tecnico", label="Técnico", number="500", default=True)]}
    targets, problems = tt.voice_transfer_targets(v)
    assert [(t["id"], t["uri"], t["default"]) for t in targets] == [
        ("faturacao", "tel:+351210000001", False), ("tecnico", "tel:500", True)]
    assert problems == []
    # sem nenhum marcado: o primeiro; com dois marcados: só o primeiro marcado
    targets, _ = tt.voice_transfer_targets({"transfer_targets": [_t(), _t(id="b", number="501")]})
    assert [t["default"] for t in targets] == [True, False]
    targets, _ = tt.voice_transfer_targets({"transfer_targets": [_t(default=True), _t(id="b", number="501", default=True)]})
    assert [t["default"] for t in targets] == [True, False]


def test_sip_per_target_is_internal_and_wins():
    v = {"transfer_targets": [_t()], "transfer_sip_uris": {"faturacao": "sip:500@pbx.cliente.pt",
                                                           "fantasma": "sip:1@pbx.cliente.pt"}}
    targets, problems = tt.voice_transfer_targets(v)
    assert targets[0]["uri"] == "sip:500@pbx.cliente.pt"
    assert ("voice.transfer_sip_uris.fantasma", tt.ORPHAN_SIP) in problems
    # SIP inválido cai para o número
    v = {"transfer_targets": [_t()], "transfer_sip_uris": {"faturacao": "sip:500@pbx"}}
    targets, problems = tt.voice_transfer_targets(v)
    assert targets[0]["uri"] == "tel:+351210000001"
    assert ("voice.transfer_sip_uris.faturacao", tt.INVALID_SIP) in problems


def test_bad_entries_are_dropped_with_a_reason():
    v = {"transfer_targets": [_t(id="Fatura ção"), _t(id="a"), _t(id="a", number="502"),
                              _t(id="b", number="sip:1@evil.example"), _t(id="c", number="")]}
    targets, problems = tt.voice_transfer_targets(v)
    assert [t["id"] for t in targets] == ["a"]
    codes = [c for _w, c in problems]
    assert codes.count(tt.INVALID_ID) == 1 and codes.count(tt.DUPLICATE_ID) == 1
    assert tt.SIP_STUDIO_ONLY in codes and codes.count(tt.NO_TARGET) == 2


def test_limits_are_reported_never_silent():
    many = {"transfer_targets": [_t(id=f"d{i}", number=f"5{i:02d}") for i in range(12)]}
    targets, problems = tt.voice_transfer_targets(many)
    assert len(targets) == tt.MAX_TARGETS and ("voice.transfer_targets", tt.TOO_MANY) in problems
    long_ = {"transfer_targets": [_t(description="x " * 300, label="y\n" * 80)]}
    targets, problems = tt.voice_transfer_targets(long_)
    assert len(targets[0]["description"]) <= tt.DESCRIPTION_MAX and "\n" not in targets[0]["label"]
    assert ("voice.transfer_targets[0]", tt.TEXT_TOO_LONG) in problems


def test_legacy_single_number_is_the_implicit_target():
    assert tt.voice_transfer_targets({"transfer_number": "+351210000000"}) == (
        [{"id": "geral", "label": "", "description": "", "uri": "tel:+351210000000", "default": True}], [])
    assert tt.voice_transfer_targets({}) == ([], [])
    # lista válida ganha ao número único, e diz-se
    targets, problems = tt.voice_transfer_targets({"transfer_number": "+351210000000",
                                                   "transfer_targets": [_t()]})
    assert [t["id"] for t in targets] == ["faturacao"]
    assert ("voice.transfer_number", tt.IGNORED_BY_TARGETS) in problems
    # lista toda inválida: vale o número único
    targets, _ = tt.voice_transfer_targets({"transfer_number": "500", "transfer_targets": [_t(id="X X")]})
    assert targets[0]["id"] == "geral"


def test_targets_on_the_model_and_exposure():
    v = ClientProfileSchema.model_validate({"voice": {"transfer_targets": [_t()]}}).voice
    assert tt.voice_transfer_targets(v)[0][0]["id"] == "faturacao"
    assert EXPOSURE["voice.transfer_targets.number"] == "client_write"
    assert EXPOSURE["voice.transfer_sip_uris"] == "internal"


def test_legacy_problems_are_reported_field_by_field():
    _t, problems = tt.voice_transfer_targets({"transfer_number": "210000000", "transfer_sip_uri": "sip:500@pbx"})
    assert problems == [("voice.transfer_sip_uri", tt.INVALID_SIP), ("voice.transfer_number", tt.NO_PLUS)]
    _t, problems = tt.voice_transfer_targets({"transfer_number": "sip:x@y.z",
                                              "transfer_sip_uri": "sip:500@pbx.cliente.pt"})
    assert problems == []                         # SIP válido: o número nem é usado


def test_invisible_characters_never_reach_the_model():
    v = {"transfer_targets": [_t(label="Fatu​ra‮ção", description="a\u0000b⁦c")]}
    t = tt.voice_transfer_targets(v)[0][0]
    assert t["label"] == "Faturação" and t["description"] == "abc"


def test_ignored_points_at_the_field_that_is_set():
    _x, problems = tt.voice_transfer_targets({"transfer_sip_uri": "sip:5@pbx.cliente.pt",
                                              "transfer_targets": [_t()]})
    assert ("voice.transfer_sip_uri", tt.IGNORED_BY_TARGETS) in problems


def test_default_is_chosen_among_the_valid_ones():
    v = {"transfer_targets": [_t(id="a", number="", default=True), _t(id="b", number="501"),
                              _t(id="c", number="502")]}
    targets, _ = tt.voice_transfer_targets(v)
    assert [(t["id"], t["default"]) for t in targets] == [("b", True), ("c", False)]
