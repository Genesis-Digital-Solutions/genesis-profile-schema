"""`agentic.packages` — pacotes de regras subscritos (A6-c do épico «Agente colega»)."""

import pytest
from pydantic import ValidationError

from genesis_profile_schema.agentic import ProfileAgentic
from genesis_profile_schema.agentic_packages import FILE_MAX, MAX_PACKAGES, AgenticPackage
from genesis_profile_schema import exposure as exp

FILES = {"manifest.json": "{}", "manifest.jws": "a.b.c", "rules.json": "{}", "SKILL.md": "x", "tests.json": "{}"}


def _pkg(**kw):
    base = {"ref": "genesis/pt-contactos@1.0.0", "files": dict(FILES)}
    base.update(kw)
    return base


def _approved(**kw):
    return _pkg(status="approved", approved_by="ana@genesis.pt", approved_at=1, **kw)


def test_por_omissao_por_rever_so_registar_e_no_principal():
    p = AgenticPackage(**_pkg())
    assert (p.status, p.mode, p.fronts, p.package_id) == ("proposed", "log_only", ["_base"], "genesis/pt-contactos")


@pytest.mark.parametrize("ref", ["genesis/pt-contactos", "Genesis/p@1.0.0", "genesis/p@1.0", "g/p@1.0.0.0",
                                 "g/p@١.0.0", "../p@1.0.0", "g/p@1.0.0 "])
def test_ref_invalida_recusa(ref):
    with pytest.raises(ValidationError):
        AgenticPackage(**_pkg(ref=ref))


def test_aprovado_exige_quem_e_quando():
    with pytest.raises(ValidationError, match="sem quem nem quando"):
        AgenticPackage(**_pkg(status="approved"))
    assert AgenticPackage(**_approved()).status == "approved"


@pytest.mark.parametrize("files", [
    {}, {"manifest.json": "{}"}, dict(FILES, **{"../x": "y"}), dict(FILES, **{"rules.json": "x" * (FILE_MAX + 1)}),
    {f"f{i}.json": "x" for i in range(9)},
])
def test_ficheiros_invalidos_recusam(files):
    with pytest.raises(ValidationError):
        AgenticPackage(**_pkg(files=files))


@pytest.mark.parametrize("fronts", [[], ["_base", "_base"], ["Mau"], ["*", "_base", "vendas"][:0]])
def test_frentes_invalidas_recusam(fronts):
    with pytest.raises(ValidationError):
        AgenticPackage(**_pkg(fronts=fronts))


def test_frentes_validas():
    assert AgenticPackage(**_pkg(fronts=["*"])).fronts == ["*"]
    assert AgenticPackage(**_pkg(fronts=["_base", "vendas"])).fronts == ["_base", "vendas"]


def test_modo_so_dois_valores():
    with pytest.raises(ValidationError):
        AgenticPackage(**_pkg(mode="permitir"))


def test_lista_uma_aprovada_por_pacote_e_sem_repetidos():
    ok = ProfileAgentic(packages=[_approved(), _pkg(ref="genesis/pt-contactos@1.1.0")])
    assert len(ok.packages) == 2
    with pytest.raises(ValidationError, match="mais do que uma versão aprovada"):
        ProfileAgentic(packages=[_approved(), _approved(ref="genesis/pt-contactos@1.1.0")])
    with pytest.raises(ValidationError, match="repetida"):
        ProfileAgentic(packages=[_pkg(), _pkg()])
    # o mesmo id de outro emissor é outro pacote
    assert ProfileAgentic(packages=[_approved(), _approved(ref="outro/pt-contactos@1.0.0")])


def test_tetos_da_lista():
    with pytest.raises(ValidationError, match="no máximo"):
        ProfileAgentic(packages=[_pkg(ref=f"genesis/p{i}@1.0.0") for i in range(MAX_PACKAGES + 1)])
    big = {k: ("x" * 200_000 if k == "rules.json" else v) for k, v in FILES.items()}
    with pytest.raises(ValidationError, match="somam mais"):
        ProfileAgentic(packages=[_pkg(ref=f"genesis/p{i}@1.0.0", files=big) for i in range(3)])


def test_sem_pacotes_nada_muda():
    assert ProfileAgentic().packages is None


def test_tudo_interno_e_classificado():
    for leaf in ("ref", "status", "mode", "fronts", "files", "imported_by", "imported_at", "approved_by",
                 "approved_at", "retired_at"):
        assert exp.EXPOSURE[f"agentic.packages.{leaf}"] == exp.INTERNAL
        assert not exp.is_client_visible(f"agentic.packages[0].{leaf}")
    assert not exp.is_client_visible("agentic.packages[0].files.rules.json")
    assert exp.unclassified_paths() == () and exp.orphan_entries() == ()


def test_teto_dos_ficheiros_em_bytes_como_o_core():
    acentos = "ç" * (FILE_MAX // 2 + 1)          # cabe em carateres, não em bytes UTF-8
    with pytest.raises(ValidationError, match="bytes"):
        AgenticPackage(**_pkg(files=dict(FILES, **{"SKILL.md": acentos})))


def test_pacote_a_aplicar_exige_regras_das_acoes_ligadas():
    from genesis_profile_schema.client_profile_schema import ClientProfileSchema
    base = {"client_id": "x", "agentic": {"enabled": True, "packages": [_approved(mode="enforce")]}}
    with pytest.raises(ValidationError, match="Regras das ações ligadas"):
        ClientProfileSchema(**base)
    with pytest.raises(ValidationError, match="Regras das ações ligadas"):
        ClientProfileSchema(**dict(base, actionRules={"enabled": False}))
    assert ClientProfileSchema(**dict(base, actionRules={"enabled": True, "rules": []})).agentic.packages
    # só registar, ou por aprovar, não precisa
    ClientProfileSchema(client_id="x", agentic={"packages": [_approved()]})
    ClientProfileSchema(client_id="x", agentic={"packages": [_pkg(mode="enforce")]})
