"""v0.1.175: `frontend.widget.bubble_shape` («Imagem livre») e
`frontend.widget.bubble_opacity_pct` (bolha translúcida).

Os dois nascem no comportamento de sempre (círculo, opaca): um default novo é
comportamento em produção. Valores fechados (opções do Literal, 40–100 em
inteiro estrito), editáveis pelo cliente como o resto do widget (_W), com
texto e opções nas duas línguas do ui_text."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from genesis_profile_schema import exposure
from genesis_profile_schema.client_profile_schema import ProfileFrontendWidget


def test_defaults_sao_o_comportamento_de_sempre():
    w = ProfileFrontendWidget()
    assert w.bubble_shape == "circle"
    assert w.bubble_opacity_pct == 100
    antigo = ProfileFrontendWidget.model_validate({"enabled": True, "bubble_icon_fit": "full"})
    assert (antigo.bubble_shape, antigo.bubble_opacity_pct) == ("circle", 100)


def test_valores_validos():
    w = ProfileFrontendWidget(bubble_shape="image", bubble_opacity_pct=40)
    assert (w.bubble_shape, w.bubble_opacity_pct) == ("image", 40)


@pytest.mark.parametrize("valor", ["square", "IMAGE", "", None, 1])
def test_forma_so_as_opcoes(valor):
    with pytest.raises(ValidationError):
        ProfileFrontendWidget(bubble_shape=valor)


@pytest.mark.parametrize("valor", [39, 0, -1, 101, 255, "80", 80.5, None, True])
def test_opacidade_inteira_entre_40_e_100(valor):
    with pytest.raises(ValidationError):
        ProfileFrontendWidget(bubble_opacity_pct=valor)


def test_editaveis_pelo_cliente_e_com_texto():
    for p in ("frontend.widget.bubble_shape", "frontend.widget.bubble_opacity_pct"):
        assert exposure.EXPOSURE[p] == exposure.EXPOSURE["frontend.widget.bubble_icon_fit"], p
        assert exposure.is_client_visible(p), p
    base = Path(exposure.__file__).parent / "ui_text"
    for loc in ("pt-PT", "en-GB"):
        campos = json.loads((base / f"{loc}.json").read_text(encoding="utf-8"))["fields"]
        for p in ("frontend.widget.bubble_shape", "frontend.widget.bubble_opacity_pct"):
            assert campos[p]["label"] and campos[p]["help"], (loc, p)
        assert set(campos["frontend.widget.bubble_shape"]["options"]) == {"circle", "image"}, loc


def test_icone_com_teto_de_tamanho():
    """O data URI do ícone vai no /client-config público (cada visitante, cada
    página): teto de 220 000 caracteres (PUBLIC_IMAGE_MAX_CHARS), acima do maior da frota (32 634)."""
    assert ProfileFrontendWidget(bubble_icon_url="data:image/png;base64," + "A" * 199_000).bubble_icon_url
    with pytest.raises(ValidationError):
        ProfileFrontendWidget(bubble_icon_url="data:image/png;base64," + "A" * 220_000)
