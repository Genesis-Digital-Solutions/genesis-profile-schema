"""v0.1.176 (21 Nov 2026, login L2): `frontend.auth.resource`, `redirectPath` e `postLogoutPath`."""

import pytest
from pydantic import ValidationError

from genesis_profile_schema.client_profile_schema import (
    OIDC_PATH_MAX_CHARS, ProfileFrontendAuth, is_oidc_return_path,
)
from genesis_profile_schema.exposure import exposure_of


def test_defaults_vazios_sao_o_comportamento_de_sempre():
    a = ProfileFrontendAuth()
    assert a.resource == "" and a.redirectPath == "" and a.postLogoutPath == ""


@pytest.mark.parametrize("path", ["/", "/auth/callback", "/auth/callback/", "/a.b_c~d-e", "/x/y/z"])
def test_caminhos_aceites(path):
    assert is_oidc_return_path(path)
    assert ProfileFrontendAuth(redirectPath=path, postLogoutPath=path).redirectPath == path


@pytest.mark.parametrize("path", [
    "auth", "//evil.com", "/a//b", "https://evil.com/cb", "/a/../b", "/./a", "/..", "/a?x=1", "/a#x",
    "/a b", "/a\\b", "/a%2f", "/é", "\\\\evil.com", "/a@b", "/a:b", " /a",
    "/" + "a" * OIDC_PATH_MAX_CHARS,
])
def test_caminhos_recusados(path):
    assert not is_oidc_return_path(path)
    with pytest.raises(ValidationError):
        ProfileFrontendAuth(redirectPath=path)
    with pytest.raises(ValidationError):
        ProfileFrontendAuth(postLogoutPath=path)


@pytest.mark.parametrize("res", ["https://api.empresa.pt", "urn:genesis:api", "microsoft:identityserver:abc"])
def test_resource_aceite(res):
    assert ProfileFrontendAuth(resource=res).resource == res


@pytest.mark.parametrize("res", ["com espaço", "a\nb", "a\tb", "x" * 513, "ção"])
def test_resource_recusado(res):
    with pytest.raises(ValidationError):
        ProfileFrontendAuth(resource=res)


def test_nao_e_validado_um_tipo_que_nao_seja_texto():
    assert not is_oidc_return_path(None)
    assert not is_oidc_return_path(["/a"])


@pytest.mark.parametrize("field", ["resource", "redirectPath", "postLogoutPath"])
def test_so_a_genesis_os_ve(field):
    assert exposure_of(f"frontend.auth.{field}") == "internal"
