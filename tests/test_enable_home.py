"""`frontend.features.enableHome` (v0.1.186) — o Início do cliente nasce desligado e só a Genesis o liga.

Um default `True` ligava o Início em toda a frota no save seguinte (o core funde o blob por cima do
DEFAULT_PROFILE); um nível de exposição editável deixava o GAIBO ligá-lo.
"""

from genesis_profile_schema import exposure as exp
from genesis_profile_schema import ui_text as ui
from genesis_profile_schema.client_profile_schema import ProfileFrontendFeatures


def test_nasce_desligado():
    assert ProfileFrontendFeatures().enableHome is False


def test_so_a_genesis_liga():
    assert exp.exposure_of("frontend.features.enableHome") == exp.CLIENT_READ
    assert exp.is_client_visible("frontend.features.enableHome")
    assert not exp.is_client_writable("frontend.features.enableHome")


def test_tem_texto_nas_duas_linguas():
    for locale in ui.LOCALES:
        assert ui.help_of("frontend.features.enableHome", locale)
