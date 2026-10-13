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
