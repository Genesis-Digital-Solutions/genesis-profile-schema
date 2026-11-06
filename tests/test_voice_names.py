"""Os valores de frontend.ttsVoiceMap e voices.by_locale são nomes de voz da Azure (v0.1.159)."""
import pytest
from pydantic import ValidationError

from genesis_profile_schema import ClientProfileSchema
from genesis_profile_schema.voice_names import is_valid_voice_name

REAIS = ["pt-PT-RaquelNeural", "en-US-Ava:DragonHDLatestNeural", "en-us-Adam:DragonHDLatestNeural",
         "zh-CN-shaanxi-XiaoniNeural", "wuu-CN-XiaotongNeural", "en-US-AvaMultilingualNeural",
         "en-US-Ava:DragonHDOmniLatestNeural", "sr-Latn-RS-NicholasNeural", "en-US-Ethan:MAI-Voice-2"]
MAUS = ['pt-PT-X"><audio src="u"/><voice name="y', "pt-PT-Raquel<Neural", "pt PT Raquel",
        "RaquelNeural", "pt-" + "-".join(["a" * 40] * 3)]


@pytest.mark.parametrize("v", REAIS)
def test_nomes_reais_passam(v):
    assert is_valid_voice_name(v)
    ClientProfileSchema.model_validate({"frontend": {"ttsVoiceMap": {"pt": v}}, "voices": {"by_locale": {"pt-PT": v}}})


@pytest.mark.parametrize("v", MAUS)
@pytest.mark.parametrize("where", ["frontend", "voices"])
def test_valor_que_nao_e_voz_e_recusado(v, where):
    body = ({"frontend": {"ttsVoiceMap": {"pt": v}}} if where == "frontend"
            else {"voices": {"by_locale": {"pt-PT": v}}})
    with pytest.raises(ValidationError):
        ClientProfileSchema.model_validate(body)


def test_os_defaults_passam_e_vazio_fica():
    ClientProfileSchema()   # o `en` HD por omissão é válido
    ClientProfileSchema.model_validate({"frontend": {"ttsVoiceMap": {"pt": ""}}})


def test_espacos_nas_pontas_gravam_sem_eles():
    p = ClientProfileSchema.model_validate({"frontend": {"ttsVoiceMap": {"pt": " pt-PT-RaquelNeural "}},
                                            "voices": {"by_locale": {"pt-PT": "  "}}})
    assert p.frontend.ttsVoiceMap["pt"] == "pt-PT-RaquelNeural"
    assert p.voices.by_locale["pt-PT"] == ""
