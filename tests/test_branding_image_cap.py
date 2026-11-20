"""v0.1.175: teto de tamanho nas imagens do branding (`logoLight`, `logoDark`,
`logoRail`, `favicon`) — o mesmo do ícone da bolha do widget.

As quatro saem no /client-config público, que cada visitante descarrega em
cada página (app e widget). A 20 Nov 2026 a DGAEP servia 605 KB por página,
com um `logoLight` de 427 298 caracteres. O teto trava isso no save; o maior
valor do resto da frota (74 050) passa com folga."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from genesis_profile_schema import exposure
from genesis_profile_schema.client_profile_schema import (
    PUBLIC_IMAGE_MAX_CHARS, ClientProfileSchema, ProfileFrontendBranding, ProfileFrontendWidget,
)

CAMPOS = ("logoLight", "logoDark", "logoRail", "favicon")
PREFIXO = "data:image/png;base64,"


def _uri(total: int) -> str:
    return PREFIXO + "A" * (total - len(PREFIXO))


def test_teto_e_o_mesmo_do_icone_da_bolha():
    assert PUBLIC_IMAGE_MAX_CHARS == 220_000
    assert ProfileFrontendWidget.model_fields["bubble_icon_url"].metadata[0].max_length == PUBLIC_IMAGE_MAX_CHARS


@pytest.mark.parametrize("campo", CAMPOS)
def test_no_teto_passa_acima_recusa(campo):
    assert len(getattr(ProfileFrontendBranding(**{campo: _uri(PUBLIC_IMAGE_MAX_CHARS)}), campo)) == PUBLIC_IMAGE_MAX_CHARS
    with pytest.raises(ValidationError):
        ProfileFrontendBranding(**{campo: _uri(PUBLIC_IMAGE_MAX_CHARS + 1)})


@pytest.mark.parametrize("campo", CAMPOS)
def test_perfil_inteiro_recusa_no_save(campo):
    """O caminho real do save (core e GAIBO validam o perfil inteiro)."""
    with pytest.raises(ValidationError):
        ClientProfileSchema.model_validate({"frontend": {"branding": {campo: _uri(427_298)}}})


def test_o_maximo_do_gaibo_passa():
    """O upload do GAIBO aceita até 160 KiB descodificados (`LOGO_MAX_DECODED_BYTES`,
    PNG ou SVG): em base64 com o prefixo mais comprido são 218 482 caracteres."""
    import base64
    uri = "data:image/svg+xml;base64," + base64.b64encode(b"x" * 160 * 1024).decode()
    assert len(uri) == 218_482
    assert ProfileFrontendBranding(logoLight=uri).logoLight == uri


def test_valores_de_hoje_continuam_validos():
    """Vazio, URL https e o maior data URI da frota fora da DGAEP (74 050)."""
    b = ProfileFrontendBranding(
        logoLight=_uri(74_050), logoDark="https://exemplo.blob.core.windows.net/branding/x/logo-dark.png",
        logoRail="", favicon=_uri(13_250),
    )
    assert b.logoRail == "" and b.logoDark.startswith("https://")
    assert ProfileFrontendBranding().logoLight == ""


def test_ajuda_diz_o_limite_nas_duas_linguas():
    base = Path(exposure.__file__).parent / "ui_text"
    for loc, marca in (("pt-PT", "220 000"), ("en-GB", "220,000")):
        campos = json.loads((base / f"{loc}.json").read_text(encoding="utf-8"))["fields"]
        for c in CAMPOS:
            ajuda = campos[f"frontend.branding.{c}"]["help"]
            assert marca in ajuda and "Console" not in ajuda, (loc, c)


BONS = (
    "",
    "https://stx.blob.core.windows.net/branding/x/logo-light.png",
    "https://www.iefp.pt/image/company_logo?img_id=12309448&t=1779470011880",
    "data:image/png;base64,iVBORw0KGgo=",
    "data:image/svg+xml;base64,PD94bWwg",
    "data:image/webp;base64,UklGR",
    "data:image/x-icon;base64,AAAB",
    "assets/logo-rail.svg",
)
MAUS = (
    "javascript:alert(1)",
    "JAVASCRIPT:alert(1)",
    "http://exemplo.pt/logo.png",
    "//exemplo.pt/logo.png",
    "data:text/html;base64,PGh0bWw+",
    "data:image/svg+xml;utf8,<svg onload=alert(1)>",
    "data:image/png;base64,ab cd",
    'https://x.pt/a.png" onerror="x',
    "ftp://x.pt/a.png",
)


@pytest.mark.parametrize("valor", BONS)
def test_formatos_aceites(valor):
    for campo in CAMPOS:
        assert getattr(ProfileFrontendBranding(**{campo: valor}), campo) == valor
    assert ProfileFrontendWidget(bubble_icon_url=valor).bubble_icon_url == valor


@pytest.mark.parametrize("valor", MAUS)
def test_formatos_recusados(valor):
    """Campo servido ao público: só https, data URI de imagem em base64 ou `assets/`."""
    for campo in CAMPOS:
        with pytest.raises(ValidationError):
            ProfileFrontendBranding(**{campo: valor})
    with pytest.raises(ValidationError):
        ProfileFrontendWidget(bubble_icon_url=valor)
