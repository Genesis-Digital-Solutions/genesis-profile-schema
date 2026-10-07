"""v0.1.97: `frontend.widget.resizable` e `frontend.insightsPanel.clearable`,
ligados por omissão, editáveis pelo cliente (exposure _W) e com texto nas
duas línguas do ui_text."""
import json
from pathlib import Path

from genesis_profile_schema.client_profile_schema import (
    ProfileFrontendInsightsPanel, ProfileFrontendWidget,
)
from genesis_profile_schema import exposure


def test_ligados_por_omissao_e_desligaveis():
    assert ProfileFrontendWidget().resizable is True
    assert ProfileFrontendInsightsPanel().clearable is True
    assert ProfileFrontendWidget(resizable=False).resizable is False
    assert ProfileFrontendInsightsPanel(clearable=False).clearable is False


def test_editaveis_pelo_cliente_e_com_texto():
    src = Path(exposure.__file__).read_text(encoding="utf-8")
    assert '"frontend.widget.resizable": _W' in src
    assert '"frontend.insightsPanel.clearable": _W' in src
    base = Path(exposure.__file__).parent / "ui_text"
    for loc in ("pt-PT", "en-GB"):
        campos = json.loads((base / f"{loc}.json").read_text(encoding="utf-8"))["fields"]
        for p in ("frontend.widget.resizable", "frontend.insightsPanel.clearable"):
            assert campos[p]["label"] and campos[p]["help"], (loc, p)
