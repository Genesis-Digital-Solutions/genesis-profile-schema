"""
tool_configs.py — acesso PÚBLICO aos modelos tipados de `tools.config.<tool>`.

`tools.config` é um mapa aberto no `ClientProfileSchema`; os blocos que têm
modelo vivem no mapa `_KNOWN_TOOL_CONFIG_MODELS` do `client_profile_schema`,
que é privado. Os consumidores que precisam de percorrer TODOS os campos do
perfil (o teste de cobertura das sugestões do Studio, por exemplo) dependiam
desse nome privado. Daqui sai uma cópia, sem mudar nada no mapa original.

⚠️ O nome privado FICA: o gaibo importa-o
(`safe_subset_manifest.load_tool_config_models`) para que um rename falhe
alto. Renomeá-lo parte o gaibo.
"""

from typing import Dict, Type

from pydantic import BaseModel

from .client_profile_schema import _KNOWN_TOOL_CONFIG_MODELS

__all__ = ["tool_config_models"]


def tool_config_models() -> Dict[str, Type[BaseModel]]:
    """`{nome da tool: modelo}` dos blocos tipados de `tools.config`.

    Devolve uma CÓPIA do mapa: mexer no resultado não regista nem retira
    modelos do pacote."""
    return dict(_KNOWN_TOOL_CONFIG_MODELS)
