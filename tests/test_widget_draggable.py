"""v0.1.175: `frontend.widget.draggable` — mover a bolha do widget à mão.

Desligado por omissão (um default novo é comportamento em produção: nenhum
cliente muda sem decisão), só booleano verdadeiro (um "true" em texto não liga
nada às escondidas), editável pelo cliente (exposure _W, como o `resizable`)
e com texto nas duas línguas do ui_text."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from genesis_profile_schema import exposure
from genesis_profile_schema.client_profile_schema import ProfileFrontendWidget


def test_desligado_por_omissao_e_ligavel():
    assert ProfileFrontendWidget().draggable is False
    assert ProfileFrontendWidget(draggable=True).draggable is True


def test_perfil_antigo_sem_o_campo_fica_desligado():
    assert ProfileFrontendWidget.model_validate({"enabled": True, "resizable": True}).draggable is False


@pytest.mark.parametrize("valor", ["true", "1", 1, "yes", None, [], {}])
def test_so_booleano(valor):
    with pytest.raises(ValidationError):
        ProfileFrontendWidget(draggable=valor)


def test_editavel_pelo_cliente_e_com_texto():
    assert exposure.EXPOSURE["frontend.widget.draggable"] == exposure.EXPOSURE["frontend.widget.resizable"]
    assert exposure.is_client_visible("frontend.widget.draggable")
    base = Path(exposure.__file__).parent / "ui_text"
    for loc in ("pt-PT", "en-GB"):
        campos = json.loads((base / f"{loc}.json").read_text(encoding="utf-8"))["fields"]
        assert campos["frontend.widget.draggable"]["label"], loc
        assert campos["frontend.widget.draggable"]["help"], loc
