"""
genesis_profile_schema/tool_doc_verification.py — `tools.config.verify_documents`,
a Verificação Documental (v0.1.100, 8 Out 2026 — épico Verificação Documental,
Fase 4; contrato 101).

Módulo próprio em vez de mais um bloco no `client_profile_schema.py`; o modelo
entra no `_KNOWN_TOOL_CONFIG_MODELS` de lá.

O que NÃO está aqui, de propósito:
  * o login. O genai-core exige-o em todas as rotas `/doc-verification/*`, seja
    qual for o `frontend.auth.mode` — um interruptor no perfil seria a porta para
    o desligar. O editor do Studio avisa quando o perfil não pede login;
  * os nomes dos papéis do Entra (`DOCVER_ROLE_NAMES`) e os tenants permitidos
    (`DOCVER_ALLOWED_TENANTS`): são segurança, e segurança vive na env do
    Container App, nunca no perfil;
  * a deteção de marcas de classificação: é o contrato do módulo, não opção.

Todos os campos são INTERNOS (custo, quota e o caso de uso vendido); a tabela de
exposição não os abre ao cliente.
"""

from __future__ import annotations

from typing import Annotated, Dict, List, Literal, Optional, Union

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr, field_validator

from .field_definition import I18nHelp

__all__ = ["DocVerificationDocumentTemplate", "DocVerificationLabels", "DocVerificationRuleOverride",
           "DocVerificationSchemeRules", "ProfileToolDocVerificationConfig", "MAX_LABEL_TEXT", "MAX_DOCUMENT_TEMPLATES",
           "MAX_RULE_OVERRIDES", "MAX_RULE_LIST_ITEMS"]

#: Um nome de ecrã (título, nome do caso, exemplo): curto. A frase do subtítulo cabe nisto também.
MAX_LABEL_TEXT = 200


def _short(value: Dict[str, str]) -> Dict[str, str]:
    for lang, text in value.items():
        if len(text) > MAX_LABEL_TEXT:
            raise ValueError(f"texto em {lang!r} com mais de {MAX_LABEL_TEXT} caracteres")
    return value


class DocVerificationLabels(BaseModel):
    """Os nomes do módulo no ecrã desta variante (28 Out 2026) — {língua: texto}, todos opcionais.

    Vazio (ou a língua em falta) = o texto neutro do ESQUEMA (`engine/schemes.py` do core, `display`), que
    nunca nomeia um cliente. Serve para um cliente chamar ao caso «candidatura», «processo», «pedido»…
    - title: o título do módulo («Análise de candidaturas»);
    - subtitle: a frase por baixo do título;
    - case_singular / case_plural: o nome do caso («candidatura» / «candidaturas»), em minúsculas — o
      ecrã põe a maiúscula onde precisa («Nova candidatura», «Candidaturas»);
    - name_example: o exemplo do campo do nome ao criar um caso (sem o «ex.:»)."""
    model_config = ConfigDict(extra="forbid")

    title: Annotated[I18nHelp, AfterValidator(_short)] = Field(default_factory=dict)
    subtitle: Annotated[I18nHelp, AfterValidator(_short)] = Field(default_factory=dict)
    case_singular: Annotated[I18nHelp, AfterValidator(_short)] = Field(default_factory=dict)
    case_plural: Annotated[I18nHelp, AfterValidator(_short)] = Field(default_factory=dict)
    name_example: Annotated[I18nHelp, AfterValidator(_short)] = Field(default_factory=dict)


#: A gramática do esquema (a mesma do `scheme` dos casos novos e do `create_case` do core).
SCHEME_PATTERN = r"^[a-z0-9][a-z0-9_.@-]{0,63}$"
#: Um por documento final de um esquema; a biblioteca tem dois esquemas com um documento cada (3 Nov 2026).
MAX_DOCUMENT_TEMPLATES = 20


class DocVerificationDocumentTemplate(BaseModel):
    """O MOLDE DO CLIENTE de um documento final (3 Nov 2026): o parecer no FEM, o relatório de conformidade nos
    concursos… O Word guarda-se no armazenamento do cliente pelo core (`PUT /admin/doc-verification/opinion-template`,
    que o valida e devolve a impressão); aqui fica só a referência que o core usa para o ir buscar.
    - scheme: o esquema do caso («fem», «concursos»; uma versão fixa «fem@2026.10» vale para o esquema base);
    - document: a chave do documento no esquema (`describe().documents[].key` do core, ex. «parecer»);
    - name: o nome do ficheiro no armazenamento (o mesmo contentor dos moldes do Intake, `intake-templates`);
    - sha256: a impressão do molde aprovado — outro conteúdo com o mesmo nome é recusado pelo core (503), nunca o
      molde base em silêncio."""
    model_config = ConfigDict(extra="forbid")

    scheme: str = Field(pattern=SCHEME_PATTERN)
    document: str = Field(pattern=r"^[a-z][a-z0-9_]{1,31}$")
    name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}\.docx$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


#: Regras de um esquema que o cliente mudou (F2 das regras configuráveis, 6 Nov 2026). O FEM tem 21; com folga.
MAX_RULE_OVERRIDES = 200
#: Os 90 municípios do FEM são a lista maior medida; com folga para outros avisos.
MAX_RULE_LIST_ITEMS = 1000
MAX_RULE_TEXT = 200


def _short_items(value: List[str]) -> List[str]:
    for x in value:
        if not x.strip() or len(x) > MAX_RULE_TEXT:
            raise ValueError(f"cada valor da lista tem de ter 1 a {MAX_RULE_TEXT} caracteres")
    return value


#: Um VALOR de uma regra: texto curto (datas ISO incluídas), número, ou lista de textos. Nunca expressões nem código —
#: o core sabe que parâmetros cada tipo de verificação deixa mudar e valida o tipo de cada um (o resto é ignorado e
#: dito no Studio). Estritos: `True` não passa por 1, `"1"` não passa por número.
RuleParamValue = Union[StrictInt, StrictFloat, Annotated[StrictStr, Field(min_length=1, max_length=MAX_RULE_TEXT)],
                       Annotated[List[StrictStr], Field(min_length=1, max_length=MAX_RULE_LIST_ITEMS),
                                 AfterValidator(_short_items)]]


class DocVerificationRuleOverride(BaseModel):
    """O que o cliente mudou numa regra do esquema (6 Nov 2026; `codigo/CONTEXT_PACK_regras_configuraveis_
    verificacao_documental.md`, camada 1). Campo ausente = o do esquema.
    - enabled: ligar/desligar a regra;
    - severity: «critical» (não cumpre) ou «attention» (por esclarecer);
    - params: os VALORES da regra (datas, limites, listas) — só os que o tipo de verificação deixa mudar; onde ler no
      formulário (folhas, colunas) nunca;
    - source: o artigo de onde vem, quando o regulamento muda."""
    model_config = ConfigDict(extra="forbid")

    enabled: Optional[bool] = None
    severity: Optional[Literal["critical", "attention"]] = None
    params: Dict[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")], RuleParamValue] = Field(
        default_factory=dict, max_length=20)
    source: Optional[str] = Field(default=None, min_length=1, max_length=400)


class DocVerificationSchemeRules(BaseModel):
    """As regras mudadas de UM esquema, por id da regra (`fem.territorio`, `fem.foto.local`…). Uma regra que o
    esquema não tem é ignorada pelo core e dita no Studio — nunca cria uma regra (isso é a camada 2)."""
    model_config = ConfigDict(extra="forbid")

    overrides: Dict[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.]{1,79}$")], DocVerificationRuleOverride] = Field(
        default_factory=dict, max_length=MAX_RULE_OVERRIDES)


class ProfileToolDocVerificationConfig(BaseModel):
    """tools.config.verify_documents — Verificação Documental.

    Os limites são os que o genai-core aplica (`tools/doc_verification/jobs/
    settings.py`): o schema diz o que o core honra, em vez de
    aceitar um valor que o core corta em silêncio.
    - scheme: o esquema dos casos NOVOS («concursos» ou «concursos@2026.10» para
      fixar a versão). Um caso guarda o seu ao nascer — mudar isto não mexe nos
      casos que já existem.
    - parallelism: lotes de cada peça lidos em paralelo pelo modelo. Medido a 8 Out
      2026: 226 páginas em 20 min com 1, 7,8 min com 4. Limitado pela quota de
      tokens por minuto do modelo do cliente.
    - deployment: vazio = o modelo do agente do container (não segue a variante).
    - labels: os nomes do módulo no ecrã desta variante (vazio = os do esquema).
    - document_templates: os moldes do cliente dos documentos finais, um por esquema e documento (vazio = o molde
      base da Genesis em todos). Voltar ao base = tirar a referência.
    - rules: as regras que o cliente mudou, por esquema base («fem»; a versão fixa «fem@2026.10» usa as do «fem»).
      Vazio = as regras do esquema tal como vêm do core. Cada candidatura fica com as regras do dia em que é
      processada pela 1.ª vez — mudar isto não mexe nas já analisadas (só com «Aplicar as regras atuais»)."""
    model_config = ConfigDict(extra="allow")

    # A mesma gramática que o core aceita ao criar um caso (`create_case`). Texto
    # com sugestões (`combobox`; os esquemas da biblioteca do core estão nas
    # `options` do ui_text), NUNCA `Literal`: um esquema novo escrito pelo Studio
    # (pin mais novo) partia o carregamento do perfil inteiro num core com o pin
    # antigo. O core, que conhece a biblioteca, usa o esquema por omissão e
    # regista quando não conhece o pedido.
    scheme: str = Field(default="concursos", pattern=SCHEME_PATTERN)
    parallelism: int = Field(default=4, ge=1, le=8)
    deployment: str = Field(default="", max_length=128)
    # Os nomes do módulo no ecrã (28 Out 2026). `None` (o que o blob gravado traz quando nunca se mexeu) =
    # os textos neutros do esquema.
    labels: Optional[DocVerificationLabels] = None
    # Os moldes do cliente dos documentos finais (3 Nov 2026). Lista, nunca `None`: o core lê `[]` como «o base».
    document_templates: List[DocVerificationDocumentTemplate] = Field(default_factory=list,
                                                                      max_length=MAX_DOCUMENT_TEMPLATES)
    # As regras mudadas pelo cliente (6 Nov 2026, F2). Dicionário, nunca `None`: o blob gravado traz `{}` e o core lê
    # «sem mudanças» (lição de 7 Out: um Optional novo aparece como `null` em toda a frota no save seguinte).
    rules: Dict[Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,31}$")], DocVerificationSchemeRules] = Field(
        default_factory=dict, max_length=20)

    @field_validator("document_templates")
    @classmethod
    def _one_per_document(cls, refs: List[DocVerificationDocumentTemplate]) -> List[DocVerificationDocumentTemplate]:
        """Um molde por documento de um esquema: dois para o mesmo deixavam o core escolher o primeiro em silêncio.
        A versão fixa conta como o esquema base (o core compara `fem@2026.10` com `fem`)."""
        seen = set()
        for r in refs:
            key = (r.scheme.split("@")[0], r.document)
            if key in seen:
                raise ValueError(f"dois moldes para o documento {r.document!r} do esquema {key[0]!r}")
            seen.add(key)
        return refs
