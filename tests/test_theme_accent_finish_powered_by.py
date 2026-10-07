"""v0.1.98: cor de destaque por modo (`theme.light|dark.accent/textOnAccent`),
acabamento fechado (`theme.finish`), `branding.showPoweredBy` (interno) e o
aviso de IA vazio por omissão (texto automático do frontend)."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from genesis_profile_schema import exposure
from genesis_profile_schema.client_profile_schema import (
    ProfileAiDisclosure, ProfileFrontendBranding, ProfileFrontendTheme, ProfileFrontendThemeMode,
)


def test_defaults_mantem_a_frota_como_esta():
    assert ProfileFrontendBranding().showPoweredBy is True
    assert ProfileFrontendTheme().finish == "flat"
    mode = ProfileFrontendThemeMode()
    assert mode.accent is None and mode.textOnAccent is None


def test_acabamento_so_aceita_opcoes_fechadas():
    for ok in ("flat", "gradient", "metallic", "glass"):
        assert ProfileFrontendTheme(finish=ok).finish == ok
    with pytest.raises(ValidationError):
        ProfileFrontendTheme(finish="url(javascript:alert(1))")


def test_destaque_por_modo_so_aceita_hex_completo():
    assert ProfileFrontendThemeMode(accent="#000000").accent == "#000000"
    for bad in ("#000", "red", "#00000g", "#000000;}"):
        with pytest.raises(ValidationError):
            ProfileFrontendThemeMode(accent=bad)


def test_exposicao_e_textos():
    assert exposure.exposure_of("frontend.branding.showPoweredBy") == exposure.INTERNAL
    for p in ("frontend.branding.theme.finish",
              "frontend.branding.theme.light.accent", "frontend.branding.theme.dark.accent",
              "frontend.branding.theme.light.textOnAccent", "frontend.branding.theme.dark.textOnAccent"):
        assert exposure.is_client_writable(p), p
    base = Path(exposure.__file__).parent / "ui_text"
    for loc in ("pt-PT", "en-GB"):
        campos = json.loads((base / f"{loc}.json").read_text(encoding="utf-8"))["fields"]
        for p in ("frontend.branding.showPoweredBy", "frontend.branding.theme.finish",
                  "frontend.branding.theme.light.accent", "frontend.branding.theme.dark.textOnAccent"):
            assert campos[p]["label"] and campos[p]["help"], (loc, p)


def test_aviso_de_ia_vazio_por_omissao_mas_ligado():
    d = ProfileAiDisclosure()
    assert d.enabled is True and d.text == ""
