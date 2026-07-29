"""
client_profile_schema.py — Schema Pydantic do ClientProfile (contrato partilhado).

FONTE DE VERDADE ÚNICA do perfil de cliente (backend + frontend num só JSON).
Deste schema derivam: (a) o perfil base (`ClientProfileSchema().to_blob_dict()`),
(b) o conversor da migração, (c) o editor de perfis do Console (via
`model_json_schema()`). NUNCA manter uma 2ª cópia à mão — gera-se tudo daqui.

Pacote partilhado: importado pelo genai-core (data plane) e pelo Console
backend (control plane). Auto-contido — só depende de `pydantic` e `typing`.

Filosofia:
  - 1 modelo único e plano, fiel ao JSON real do Blob.
  - `extra='allow'` em todos os submodels (evolução sem migrações).
  - Sem max_length em textos livres e sem max_items em listas.
  - Sem limites superiores (le) em knobs de qualidade/contexto — na dúvida,
    aumentar; nunca cortar por poupança.
  - Defaults seguros: um perfil vazio validado é um perfil funcional.

v0.1.38 (Jul 2026) — captura: `notify_language` (língua do email de aviso — a
do CLIENTE que o recebe, não a do visitante).

v0.1.37 (Jul 2026) — captura: `notify_emails` / `notify_subject` (notificação
ao consultor quando entra uma captura completa).

v0.1.36 (Jul 2026) — épico Capture: `tools.config.record_contact_details`
(ProfileToolCaptureConfig) com campos fechados, base legal obrigatória e
recusa de campos avaliativos / categorias especiais no próprio contrato.

Convenção de metadata para o editor (json_schema_extra):
  - "requires_tool": <nome>   → feature/flag só coerente com essa tool ligada.
  - "requires_field": <path>  → flag depende de outro campo estar preenchido.
  O editor lê estes hints para avisar e impedir combinações incoerentes.
"""

import warnings

# Suprimir warning Pydantic do campo `register` em ProfileIdentity — o nome
# do campo é fixado pelo JSON do Blob (compat com client_profile.py legacy),
# não pode ser renomeado. Não afecta funcionamento.
warnings.filterwarnings(
    "ignore",
    message=r'Field name "register".*shadows an attribute in parent "BaseModel"',
    category=UserWarning,
)

from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, model_validator


# ─────────────────────────────────────────────────────────────────────────────
# Defaults reutilizáveis
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_TONE_INSTRUCTIONS: Dict[str, str] = {
    "professional": (
        "Professional, helpful, natural tone. Clear and precise without "
        "being robotic. Adapt to the user's level — technical when they "
        "are, simple when they are."
    ),
    "formal": (
        "Strictly formal and neutral. Corporate customer-support style. "
        "No emojis. No colloquial language."
    ),
    "friendly": (
        "Friendly and approachable, still professional. Warm and "
        "conversational."
    ),
    "technical": (
        "Technical and precise. Use correct terminology. Assume domain "
        "expertise. Include specifications and references when available."
    ),
    "commercial": (
        "Solution-oriented and persuasive. Highlight benefits, "
        "practical applications, differentiators."
    ),
}

_DEFAULT_LANGUAGE_FALLBACK = "Portuguese (European Portuguese - pt-PT)"
_DEFAULT_LANGUAGE_ALIASES: Dict[str, str] = {"pt-BR": "pt-PT"}

# Tools ligadas por defeito num cliente "normal" (bot RAG documental).
# Backend é agente, RAG-agnostic — projetos atípicos mudam isto no editor.
# `request_clarification` é auto-incluída pelo backend quando há outras tools.
_DEFAULT_TOOLS_ENABLED: List[str] = [
    "search_knowledge_base",
    "recall_past_conversations",
    "render_diagram",
    "render_chart",
    "render_table",
    "render_formula",
]

# Vozes Azure Speech por locale (default). O editor mostra um dropdown do
# catálogo real de vozes; estes são os pontos de partida.
_DEFAULT_VOICES_BY_LOCALE: Dict[str, str] = {
    "pt-PT": "pt-PT-FernandaNeural",
    "pt-BR": "pt-BR-FranciscaNeural",
    "en-US": "en-US-JennyNeural",
    "en-GB": "en-GB-SoniaNeural",
    "es-ES": "es-ES-ElviraNeural",
    "fr-FR": "fr-FR-DeniseNeural",
}

_DEFAULT_AI_DISCLOSURE = "Está a comunicar com um assistente de inteligência artificial."

# Mapa i18n data-driven: { "pt": "...", "en": "...", "fr": "..." }. As chaves
# sao codigos de lingua; para suportar uma nova lingua basta acrescentar a chave.
I18nMap = Dict[str, str]


# ─────────────────────────────────────────────────────────────────────────────
# Sub-modelos: lado backend
# ─────────────────────────────────────────────────────────────────────────────

class ProfileIdentity(BaseModel):
    model_config = ConfigDict(extra="allow", protected_namespaces=())

    company_name: str = "Genesis Digital Solutions"
    assistant_name: str = "Genesis AI"
    default_language: str = "auto"
    timezone: str = "Europe/Lisbon"
    logo_url: str = ""
    register: Literal["formal", "informal", "mirror"] = "formal"


class ProfilePersonality(BaseModel):
    model_config = ConfigDict(extra="allow")

    tone: Literal["professional", "formal", "friendly", "technical", "commercial"] = "professional"
    tone_instructions: Dict[str, str] = Field(default_factory=lambda: dict(_DEFAULT_TONE_INSTRUCTIONS))
    response_length: Literal["short", "balanced", "detailed"] = "balanced"


class ProfileDomain(BaseModel):
    model_config = ConfigDict(extra="allow")

    description: str = ""


class ProfileResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    show_sources: bool = True
    show_images: bool = True
    # Gate REAL dos follow-ups (a flag frontend `enableFollowupSuggestions` era
    # morta — o componente nunca a lia). Off por defeito.
    suggest_followups: bool = False
    followup_count: int = Field(default=3, ge=0)
    extractive_mode: bool = False
    # Explainability summary (EU AI Act — transparência/Art. 13 p/ deployments
    # de risco; diferenciador de confiança nos restantes): fase opcional
    # pós-geração em que o INTERNAL_MODEL consome o pipeline_trace e explica em
    # 2-3 frases como a resposta foi produzida. Emitido por SSE separado
    # ({"explainability": ...}) — não atrasa a resposta. Off por defeito.
    explainability_summary: bool = False


class ProfileGuardrails(BaseModel):
    model_config = ConfigDict(extra="allow")

    competitor_brands: List[str] = Field(default_factory=list)
    blocked_words: List[str] = Field(default_factory=list)
    allow_general_knowledge: bool = False


class ProfileProductIdentification(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    patterns: List[str] = Field(default_factory=list)
    stopwords: List[str] = Field(default_factory=list)
    internal_prefixes: List[str] = Field(default_factory=list)
    strict_mode: bool = True


class ProfileBrandSafety(BaseModel):
    model_config = ConfigDict(extra="allow")

    blocked_brands: List[str] = Field(default_factory=list)
    level: Literal["soft_redirect", "hard_block", "post_filter"] = "soft_redirect"
    redirect_to: str = ""


# ── Configs tipadas de tools conhecidas (v0.1.26) ────────────────────────────
# `tools.config` continua um Dict aberto (cada tool define o seu — nunca
# restringimos tools novas), mas as tools com config CONHECIDA ganham um model
# tipado, usado pelo validator de ProfileTools para apanhar formatos errados
# no /admin/profile/validate ANTES de irem para o Blob. extra="allow" em todos:
# campos novos de versões futuras do genai-core passam sem migração.

class ProfileToolSearchWebConfig(BaseModel):
    """tools.config.search_web — agente de pesquisa web (Azure AI Foundry)."""
    model_config = ConfigDict(extra="allow")

    project_endpoint: str = ""
    web_agent_id: str = ""
    web_agent_name: str = ""
    mode: Literal["agent", "native", ""] = "agent"  # "" tolerado (editor antigo); native = web_search da Responses API
    temperature: Union[float, str] = ""            # "" = default do agente
    allowed_domains: List[str] = Field(default_factory=list)


class ProfileToolGenerateImageConfig(BaseModel):
    """tools.config.generate_image — modelo de geração de imagem por cliente."""
    model_config = ConfigDict(extra="allow", protected_namespaces=())

    model: str = ""                                # ex: "gpt-image-1"; "" = default do core


class ProfileLegalExtractFieldSpec(BaseModel):
    """Um campo do schema de extração legal: label (cartão) + hint (instrução
    de extração para o LLM). A key é a chave do dict em `schema`.

    v0.1.27 (i18n das tools): o label aceita string simples OU mapa
    multilingue {lang: texto} (ex: {"pt": "Partes", "ar": "الأطراف"}) — o
    genai-core resolve pela língua detetada do utilizador com fallback
    lang → en → pt → primeiro valor."""
    model_config = ConfigDict(extra="allow")

    label: Union[str, Dict[str, str]] = ""
    hint: str = ""


class ProfileToolLegalExtractConfig(BaseModel):
    """tools.config.extract_legal_terms — motor de extração documental com
    schema por perfil (épico BOQ+Legal, Jul 2026). Cada campo é extraído com
    saída {value, reference} (referência de página/cláusula — padrão ADIC).

    `schema` aceita, por campo, o objeto {label, hint} OU a forma abreviada
    string (só o hint) — normalizada pelo genai-core. Vazio = schema default
    da tool (termos de contrato).

    Overlay de domínio (tool_playbooks): prompt_preset (preset do produto) +
    prompt_custom (instruções livres do cliente), APENDADOS ao contrato base do
    LLM legal — nunca o substituem.
    """
    model_config = ConfigDict(extra="allow")

    title: str = ""                                # título do cartão; "" = default da tool
    field_schema: Dict[str, Union[ProfileLegalExtractFieldSpec, str]] = Field(
        default_factory=dict,
        alias="schema",
        json_schema_extra={"requires_tool": "extract_legal_terms"},
    )
    prompt_preset: str = ""                         # "" | "contracts" (catálogo tool_playbooks)
    prompt_custom: str = ""                         # instruções de domínio livres (apendadas)


class ProfileToolBoqRateRule(BaseModel):
    """Uma regra da tabela de preços do BOQ (tools.config.generate_boq.rates).
    Casa linhas SEM preço da fonte: se `match` (substring, case-insensitive)
    ocorre na descrição da linha e (se indicada) `unit` coincide, aplica `price`.
    Fonte explícita de custos — o genai-core nunca inventa preços."""
    model_config = ConfigDict(extra="allow")

    match: str = ""
    unit: str = ""
    price: Union[float, str] = ""                   # "" tolerado (linha em branco no editor)
    label: str = ""


class ProfileToolBoqScale(BaseModel):
    """tools.config.generate_boq.scale — travões de plausibilidade da calibração
    de escala do parser PDF (épico BOQ v2, passo 3b). São afinações de
    COMPORTAMENTO por cliente (não env): raramente se tocam — no fluxo normal a
    escala é confirmada pelo carimbo/cadeia de cotagem e a afinação caso-a-caso
    faz-se por calibração ao agente. Só fazem sentido para clientes com desenhos
    sistematicamente atípicos (obras civis de vários km → subir max_drawing_span_mm;
    pormenores de peças pequenas → descer min_drawing_span_mm; PDFs sempre muito
    reescalados com cotas fiáveis → subir max_corrob_printed_ratio). Vazio/ausente
    = defaults do genai-core. extra=allow → round-trip byte-fiel."""
    model_config = ConfigDict(extra="allow")

    max_corrob_printed_ratio: Optional[float] = None  # divergência máx. cotas/carimbo p/ descartar o carimbo (default 2.5)
    min_drawing_span_mm: Optional[float] = None        # extensão real mínima plausível do desenho, em mm (default 500 = 0,5 m)
    max_drawing_span_mm: Optional[float] = None        # extensão real máxima plausível do desenho, em mm (default 2 000 000 = 2 km)


class ProfileToolBoqConfig(BaseModel):
    """tools.config.generate_boq — Bill of Quantities (épico BOQ v2, Jul 2026).
    - prompt_preset: norma de medição (overlay tool_playbooks): "" | "pronic_pt" | "pomi_gcc" | "cesmm_civil" | "nrm2_building".
    - prompt_custom: instruções de domínio livres do cliente (apendadas ao contrato base).
    - rates: tabela de preços editável pelo cliente (fonte explícita de custos).
    - scale: travões de plausibilidade da escala (avançado; vazio = defaults).
    Vazio = tool no comportamento default. extra=allow → round-trip byte-fiel."""
    model_config = ConfigDict(extra="allow")

    prompt_preset: str = ""
    prompt_custom: str = ""
    rates: List[ProfileToolBoqRateRule] = Field(
        default_factory=list,
        json_schema_extra={"requires_tool": "generate_boq"},
    )
    scale: Optional[ProfileToolBoqScale] = None


# ── Captura estruturada (v0.1.36 — épico Capture, Jul 2026) ─────────────────
# Regra central do épico: CAMPOS FECHADOS, MOMENTO ABERTO. O schema que o modelo
# vê tem EXACTAMENTE os campos configurados aqui; o LLM decide QUANDO preencher,
# nunca O QUÊ. É isto que torna a minimização de dados declarável — o aviso de
# privacidade pode listar os campos porque são finitos e conhecidos.

# Tokens proibidos em `key`/`label` de um campo de captura. Os dois grupos têm
# fundamentos distintos e ambos são ERRO (não aviso), porque o custo de os
# deixar passar não é técnico:
#
#  • AVALIAÇÃO — a tool CAPTURA, nunca AVALIA. Pontuar/classificar/ranquear
#    candidatos faz o sistema entrar no anexo de emprego do AI Act (alto risco).
#    Um perfil de recrutamento com um campo "score" muda o enquadramento
#    regulatório do deployment inteiro. Se um dia houver scoring: tool separada,
#    avaliação de risco separada, decisão própria.
#  • CATEGORIAS ESPECIAIS (RGPD Art. 9) — não há base legal montada para as
#    tratar num formulário de contacto. Bloqueadas no contrato E na tool
#    (defesa em profundidade: o Studio não deixa configurar, o core não grava).
_CAPTURE_FORBIDDEN_EVALUATIVE = (
    "score", "scoring", "rating", "ranking", "rank", "probability",
    "likelihood", "propensity", "fit", "suitability", "qualification_level",
    "classification", "grade", "tier", "priority_level",
    "pontuacao", "pontuação", "classificacao", "classificação",
    "avaliacao", "avaliação", "probabilidade", "adequacao", "adequação",
)

_CAPTURE_FORBIDDEN_SPECIAL_CATEGORY = (
    "health", "medical", "diagnosis", "disability", "ethnicity", "ethnic",
    "race", "racial", "religion", "religious", "belief", "political",
    "party", "union", "sexual", "sexuality", "orientation", "biometric",
    "genetic", "criminal", "conviction", "pregnan",
    "saude", "saúde", "medico", "médico", "diagnostico", "diagnóstico",
    "deficiencia", "deficiência", "etnia", "raca", "raça", "religiao",
    "religião", "politic", "sindicato", "sindical", "orientacao_sexual",
    "orientação_sexual", "biometric", "genetic", "criminal", "gravidez",
)


class ProfileCaptureField(BaseModel):
    """Um campo configurado da captura.

    `key` é o nome técnico (EN, snake_case) — é a chave gravada em `fields` no
    Cosmos e o nome do parâmetro que o modelo vê. `label` é o rótulo humano
    (string ou mapa i18n {lang: texto}) para a lista no Studio e para o aviso
    de privacidade. `hint` é a instrução de preenchimento dada ao LLM.

    `required` NÃO bloqueia a gravação (uma captura parcial vale mais do que
    nenhuma) — só entra no cálculo de `completeness` do registo.
    """
    model_config = ConfigDict(extra="allow")

    key: str = ""
    label: Union[str, Dict[str, str]] = ""
    hint: str = ""
    required: bool = False


class ProfileToolCaptureConfig(BaseModel):
    """tools.config.record_contact_details — captura estruturada via tool.

    Desacoplada do Guião de propósito: apanha tanto a resposta a uma pergunta
    de qualificação como a oferta espontânea de dados ("sou o João, 91x xxx xxx,
    quero vender um T3"). Serve chat, voz e widget sem código por canal.

    INERTE por defeito: sem `fields` ou sem `legal_basis` a tool não chega a
    aparecer ao modelo (is_available False) — padrão da casa.
    """
    model_config = ConfigDict(extra="allow")

    # Tipo de negócio do registo. FIXO por perfil/variante (não escolhido pelo
    # modelo — menos não-determinismo). Distingue `lead_venda` de `candidatura`
    # de `pedido_orcamento`: custo zero agora, evita uma tabela chamada "leads"
    # cheia de candidaturas de recrutamento.
    capture_type: str = ""

    # Base legal do tratamento — decisão do CLIENTE (responsável pelo
    # tratamento), nunca do código. Guarda-se o valor SEMÂNTICO e não o rótulo
    # de UI ("interno"/"externo") para não obrigar a migração quando aparecer o
    # terceiro caso: uma candidatura é de gente externa mas com base diferente
    # de uma lead comercial, e um portal de fornecedores é externo e recolhe ao
    # abrigo de contrato.
    #   consent             → a tool PEDE consentimento e respeita a recusa.
    #   contract            → recolhe sem pedir; informa no disclaimer.
    #   legitimate_interest → idem.
    # NOTA (contexto laboral): `consent` é normalmente a base ERRADA para
    # colaboradores — o desequilíbrio de poder faz com que o consentimento não
    # seja "livremente prestado". Pedir a um trabalhador é pior do que não
    # pedir: cria escolha ilusória e, se recusar, fica-se sem base legal.
    legal_basis: Literal["", "consent", "contract", "legitimate_interest"] = ""

    # Quem escolheu a base legal e quando (preenchido pelo Studio ao gravar).
    # Protege a Genesis (subcontratante) e é argumento de venda: a plataforma
    # obriga a documentar a decisão.
    legal_basis_set_by: str = ""
    legal_basis_set_at: str = ""

    # Finalidade ESPECÍFICA, na voz do cliente. Entra no pedido de
    # consentimento. "Recolher dados para melhorar a sua experiência" NÃO é
    # finalidade válida e mina a base legal; "para que um consultor o contacte
    # sobre a venda do seu imóvel" é. Aceita mapa i18n.
    purpose: Union[str, Dict[str, str]] = ""

    # Os campos. Vazio = tool inerte.
    fields: List[ProfileCaptureField] = Field(
        default_factory=list,
        json_schema_extra={"requires_tool": "record_contact_details"},
    )

    # Retenção do registo, em dias. "" / 0 = sem expiração (o container tem
    # DefaultTimeToLive=-1, logo o `ttl` por documento é que decide).
    # ATENÇÃO à semântica: o Cosmos conta o TTL a partir da ÚLTIMA
    # modificação, e a captura faz upsert incremental por conversa — a
    # retenção é "N dias após o último contacto", não após a criação.
    retention_days: Union[int, str] = ""

    # Notificar por email quando entra uma captura. Enviada UMA vez por
    # conversa, quando o registo fica completo (todos os campos essenciais
    # preenchidos) — não a cada campo novo, senão o consultor recebe três
    # emails para a mesma pessoa. Ver core/managers/captures_notify.py.
    notify_on_capture: bool = False
    # Destinatários. Vazio com notify_on_capture=True → nada é enviado (fica
    # registado no audit_log). Não se reutiliza `ingest.alerts.email`: aquele é
    # para alertas operacionais da fila e tem outro dono.
    notify_emails: List[str] = Field(default_factory=list)
    # Assunto do email. {capture_type} e {client} são substituídos.
    notify_subject: str = ""
    # Língua do EMAIL de aviso — a do CLIENTE, não a do visitante: quem lê é o
    # consultor que vai ligar de volta. Vazio = usa `language.fallback` do
    # perfil. Um visitante árabe num cliente português gera email em português
    # com os dados em árabe.
    notify_language: Literal["", "pt", "en", "es", "ar"] = ""

    @model_validator(mode="after")
    def _validate_capture(self) -> "ProfileToolCaptureConfig":
        fields = list(self.fields or [])
        if not fields:
            return self          # inerte — nada a validar

        # A base legal é OBRIGATÓRIA a partir do momento em que há campos.
        # Sem ela não há como declarar o tratamento, e a tool ficaria a
        # recolher dados pessoais sem fundamento documentado.
        if not (self.legal_basis or "").strip():
            raise ValueError(
                "legal_basis é obrigatório quando há campos configurados "
                "(consent | contract | legitimate_interest)"
            )
        # Notificação ligada sem destinatários é uma armadilha silenciosa:
        # o cliente pensa que está a ser avisado e não está.
        if self.notify_on_capture and not [
            e for e in (self.notify_emails or []) if (e or "").strip()
        ]:
            raise ValueError(
                "notify_on_capture=True exige pelo menos um endereço em "
                "notify_emails"
            )
        # `consent` sem finalidade específica = aviso vago = base minada.
        if self.legal_basis == "consent" and not self.purpose:
            raise ValueError(
                "legal_basis='consent' exige `purpose` — a finalidade "
                "específica que é apresentada ao utilizador"
            )

        seen = set()
        for f in fields:
            key = (f.key or "").strip()
            if not key:
                raise ValueError("campo de captura sem `key`")
            if key in seen:
                raise ValueError(f"campo de captura duplicado: '{key}'")
            seen.add(key)

            haystack = f"{key} {f.label if isinstance(f.label, str) else ' '.join((f.label or {}).values())}".lower()
            for token in _CAPTURE_FORBIDDEN_EVALUATIVE:
                if token in haystack:
                    raise ValueError(
                        f"campo '{key}': a captura registra o que o utilizador "
                        f"disse, nunca juízos do modelo ('{token}'). Pontuar ou "
                        f"classificar candidatos torna o sistema alto risco no "
                        f"AI Act — exige tool e avaliação de risco próprias."
                    )
            for token in _CAPTURE_FORBIDDEN_SPECIAL_CATEGORY:
                if token in haystack:
                    raise ValueError(
                        f"campo '{key}': categoria especial de dados (RGPD "
                        f"Art. 9, '{token}') não pode ser recolhida por esta "
                        f"tool."
                    )
        return self


# Mapa key de tools.config → model tipado. Tools fora deste mapa passam sem
# validação estrutural (estrutura aberta, como sempre).
_KNOWN_TOOL_CONFIG_MODELS: Dict[str, Any] = {
    "search_web": ProfileToolSearchWebConfig,
    "generate_image": ProfileToolGenerateImageConfig,
    "extract_legal_terms": ProfileToolLegalExtractConfig,
    "generate_boq": ProfileToolBoqConfig,
    "record_contact_details": ProfileToolCaptureConfig,
}


class ProfileTools(BaseModel):
    model_config = ConfigDict(extra="allow")

    # Baseline RAG documental. O catálogo vivo do backend (/tools) é a lista
    # completa; o editor pré-seleciona estas e mostra as restantes como toggles.
    enabled: List[str] = Field(default_factory=lambda: list(_DEFAULT_TOOLS_ENABLED))
    # config por tool — estrutura aberta (cada tool define o seu)
    config: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_known_tool_configs(self) -> "ProfileTools":
        """Valida os blocos de tools.config com model conhecido, SEM alterar o
        conteúdo gravado (o Blob mantém exatamente o que o editor enviou —
        round-trip byte-fiel; o model tipado serve só de guarda de formato)."""
        for key, model in _KNOWN_TOOL_CONFIG_MODELS.items():
            raw = (self.config or {}).get(key)
            if raw is None:
                continue
            try:
                model.model_validate(raw)
            except Exception as e:
                raise ValueError(f"tools.config.{key} inválido: {e}") from e
        return self


class ProfileSourcePriority(BaseModel):
    """
    Priorização de fontes por nível de autoridade (interno → legal → externo),
    montando o contexto por prioridade de tier em vez de só por score. OFF por
    defeito (paridade total com a frota actual).

    Como se obtém o tier de cada chunk — `strategy`:
      - "field": lê um campo de metadados do índice (`tier_field`, ex.: "tier").
                 Via limpa para clientes novos que etiquetam autoridade na
                 ingestão. Degrada em segurança se o campo não existir (sem-tier).
      - "path":  deriva o tier do caminho da fonte (campo `source`) — `internal_markers`
                 marcam interno; `legal_allowlist` marca legal; o resto é externo.
                 NÃO exige reindexação (lê o `source` que já está no índice). É a
                 via usada por clientes legacy migrados sem mexer no índice.

    O motor a jusante (reordenação por tier) é o MESMO nas duas estratégias; só
    muda a forma de obter o tier de cada chunk. Preferir peso suave a filtro duro:
    o externo é deprioritizado, não removido.
    """
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    strategy: Literal["field", "path"] = "field"

    # strategy="field"
    tier_field: str = "tier"            # campo de metadados que traz o nível de autoridade

    # strategy="path"
    internal_markers: List[str] = Field(default_factory=list)      # ex.: ["/01_documentos/", "/02_modelos/"]
    legal_allowlist: List[str] = Field(default_factory=list)       # caminhos/prefixos de fontes legais/reguladoras
    label_overrides: Dict[str, str] = Field(default_factory=dict)  # entrada da allowlist → rótulo legível

    # Salvaguarda de relevância (escala reranker 0–4): fontes de nível superior
    # com score abaixo do piso são adiadas para depois das de nível inferior que
    # estejam acima do piso. None/0 = desativado. Sem limite superior (na dúvida, subir).
    reranker_floor: Optional[float] = Field(default=None, ge=0.0)


class ProfileLatestVersion(BaseModel):
    """
    Routing "última versão de X" — para perguntas pela versão mais recente de
    uma família de documentos (ex.: "qual o último RASARP?"), restringe o
    contexto à versão mais recente em vez de misturar anos. OFF por defeito.

    Como se determina a data/versão — `strategy`:
      - "field": lê um campo datetime/string do índice (`date_field`/`version_field`).
                 O indexer do Studio já escreve `source_last_modified` e
                 `doc_version`, pelo que esta via funciona sem trabalho de ingestão
                 adicional. "A mais recente" é resolvida deterministicamente pelo
                 retrieval — o modelo NÃO adivinha datas.
      - "path":  deriva o ano do caminho da fonte via `year_segment_regex`
                 (ex.: "/2025/"). Via para clientes legacy cuja estrutura de
                 pastas codifica o ano; não exige reindexação.

    `intent_patterns` deteta a intenção de "última versão" na pergunta (regex,
    qualquer estratégia). `family_field` (strategy="field") agrupa por família de
    documento; vazio = derivar da própria pergunta/categoria.
    """
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    strategy: Literal["field", "path"] = "field"

    intent_patterns: List[str] = Field(default_factory=list)   # ex.: "últim[oa]s?", "mais recentes?", "latest"

    # strategy="field"
    date_field: str = "source_last_modified"   # campo datetime no índice (já escrito pelo indexer)
    version_field: str = "doc_version"         # campo de versão no índice (já escrito pelo indexer)
    family_field: str = ""                     # campo de família/série; vazio = derivar

    # strategy="path"
    year_segment_regex: str = r"/(19\d{2}|20\d{2})/"   # extrai o ano de um segmento do caminho


class ProfileNeighborExpansion(BaseModel):
    """
    Expansão de vizinhos por cliente (antes só env vars de frota:
    KB_EXPAND_NEIGHBORS/KB_NEIGHBOR_*). Traz os chunks adjacentes
    (chunk_index ±window) das melhores âncoras, para respostas que
    atravessam fronteiras de chunk (tabelas, cláusulas, procedimentos).
    Campos a None = fallback às envs (comportamento de frota intacto).
    Alto valor em contratos/manuais/tabelas; ruído potencial em FAQs curtas.
    """
    model_config = ConfigDict(extra="allow")

    enabled: Optional[bool] = None      # None = env KB_EXPAND_NEIGHBORS (default ON)
    window: Optional[int] = Field(default=None, ge=1)       # KB_NEIGHBOR_WINDOW (1)
    top_anchors: Optional[int] = Field(default=None, ge=1)  # KB_NEIGHBOR_TOP_ANCHORS (5)
    max_added: Optional[int] = Field(default=None, ge=0)    # KB_NEIGHBOR_MAX_ADDED (12)


class ProfileRetrievalIndex(BaseModel):
    """Config por-índice (multi-índice). Rede de segurança: lista vazia →
    comportamento atual (todos os índices tratados igual). `weight` escala o
    reranker_score dos chunks do índice no merge (corrige a incomparabilidade
    de scores entre índices heterogéneos e permite preferir o autoritativo);
    `rerank_mode` decide se os chunks desse índice tornam o GPT rerank elegível
    (`llm`) ou se basta o reranker semântico do Azure (`semantic_only`).
    Índice não listado = `llm` (default)."""
    model_config = ConfigDict(extra="allow")

    name: str
    weight: float = Field(default=1.0, ge=0.0)
    rerank_mode: Literal["llm", "semantic_only"] = "llm"


class ProfileRetrieval(BaseModel):
    """
    Knobs de RAG/retrieval por cliente. Antes só env vars (KB_*, RAG_*) — logo
    invisíveis e não-afináveis por cliente no Console. Agora no perfil.

    Regra: qualidade acima de custo. Sem limites superiores — na dúvida, subir.
    """
    model_config = ConfigDict(extra="allow")

    # Índices AI Search por perfil (Épico Multi-Perfil — Julho 2026, v0.1.34).
    # Lista de nomes de índices; vazia → fallback às envs AZURE_SEARCH_INDEX_NAMES/
    # AZURE_SEARCH_INDEX_NAME (comportamento da frota, byte a byte). Perfil-primeiro
    # permite: (a) índice próprio por VARIANTE multi-perfil; (b) mudar o índice de
    # qualquer cliente via Studio com efeito em ≤TTL, sem redeploy do CA.
    search_index_names: List[str] = Field(default_factory=list)

    top_k: int = Field(default=20, ge=1)                       # KB_TOP_K
    # Corte final de contexto: nº de chunks (ordenados por reranker_score,
    # determinístico) que passam ao modelo ANTES da expansão de vizinhos.
    # 0 = OFF (passa todos, comportamento histórico). Opt-in por cliente para
    # matar variância por excesso de contexto. Distinto de top_k (recall) e
    # rerank_top_k (cap do GPT rerank, só em force_diversity).
    context_top_k: int = Field(default=0, ge=0)                # KB_CONTEXT_TOP_K
    # Injeta no contexto de cada chunk as linhas Source:/Url:/Page:/Tier:/
    # Entity: (estilo legacy format_docs), ANTES do Content:. Alimenta as
    # custom_instructions do cliente que formatam o CAMINHO da fonte como
    # link (ex.: Indaqua). False = contexto da frota intacto (comportamento
    # histórico). Opt-in por cliente. Tier/Entity vêm do classify_source
    # (mesma lógica do source_priority).
    context_include_source_fields: bool = False               # KB_CONTEXT_SOURCE_FIELDS
    min_score: float = Field(default=0.15, ge=0.0, le=1.0)     # KB_MIN_SCORE
    enable_rerank: bool = True                                  # KB_ENABLE_RERANK
    chars_per_chunk: int = Field(default=5000, ge=0)           # KB_CHARS_PER_CHUNK
    rerank_chars_per_source: int = Field(default=3000, ge=0)   # RAG_PHASE1_CHARS_PER_SOURCE
    topicality_gate: bool = True                               # KB_TOPICALITY_GATE
    force_diversity: bool = False                              # KB_FORCE_DIVERSITY
    # GPT re-rank largo (só em broad/diversity): um LLM re-ordena os candidatos
    # por relevância antes do corte. Custo extra por query; ganho de qualidade
    # em corpora ruidosos. Antes só env — agora por cliente e afinável.
    gpt_rerank_broad: bool = False                             # RAG_ENABLE_GPT_RERANK_BROAD
    fuzzy_correction: bool = False                             # KB_FUZZY_CORRECTION_ENABLED
    faithfulness_overlap_skip: float = Field(default=0.65, ge=0.0, le=1.0)  # FAITHFULNESS_JUDGE_OVERLAP_SKIP

    # Expansão de vizinhos por cliente. Campos None = envs de frota.
    neighbor_expansion: ProfileNeighborExpansion = Field(
        default_factory=ProfileNeighborExpansion,
        json_schema_extra={"requires_tool": "search_knowledge_base"},
    )

    # Priorização por tier e routing de "última versão" — capacidades de
    # retrieval por cliente, OFF por defeito (paridade com a frota). Só
    # coerentes com a tool de KB ligada.
    source_priority: ProfileSourcePriority = Field(
        default_factory=ProfileSourcePriority,
        json_schema_extra={"requires_tool": "search_knowledge_base"},
    )
    latest_version: ProfileLatestVersion = Field(
        default_factory=ProfileLatestVersion,
        json_schema_extra={"requires_tool": "search_knowledge_base"},
    )
    # Config por-índice (multi-índice). Vazio = comportamento atual (rede de
    # segurança): todos os índices com peso 1.0 e rerank elegível.
    indexes: List[ProfileRetrievalIndex] = Field(
        default_factory=list,
        json_schema_extra={"requires_tool": "search_knowledge_base"},
    )


class ProfileOrchestration(BaseModel):
    """Estratégia de orquestração de tools por cliente.

    Traduzida em texto pelo prompt_builder (`_build_tools_guidance_block`),
    SEMPRE por capability (grounded source / web) — nunca por nome de tool.
    `grounded_first` = comportamento histórico (KB primeiro, web fallback);
    é o default, garante paridade com perfis que não definam esta secção.
    """
    model_config = ConfigDict(extra="allow")

    # grounded_first: KB primeiro, web só como fallback/temporal (default)
    # web_first:      web primeiro, KB a complementar (ex. cliente de notícias)
    # parallel:       KB e web em paralelo, resultados combinados
    retrieval_strategy: Literal["grounded_first", "web_first", "parallel"] = "grounded_first"

    # Permite a tool de web na orquestração. False = web nunca entra no guidance.
    allow_web: bool = True

    # Planner leve: um passo pré-loop classifica pedidos multi-passo e gera um
    # plano curto (3-6 passos) injetado no prompt. OFF por defeito. Custo de 1
    # internal-LLM call quando dispara. Antes só env — agora por cliente.
    agent_planner: bool = False                                 # AGENT_PLANNER_ENABLED
    # Execução paralela de tools quando o batch tem 2+ chamadas independentes.
    # OFF por defeito. Reduz latência multi-tool; validar por cliente. Antes só env.
    parallel_tools: bool = False                                # AGENT_PARALLEL_TOOLS


class ProfileRuntime(BaseModel):
    """Runtime do agente. Antes env vars (AGENT_*, SUMMARY_*)."""
    model_config = ConfigDict(extra="allow")

    max_turns: int = Field(default=5, ge=1)                    # AGENT_MAX_TURNS
    model_timeout_s: int = Field(default=60, ge=1)            # AGENT_MODEL_TIMEOUT
    max_history_items: int = Field(default=20, ge=0)          # AGENT_MAX_HISTORY_ITEMS
    summary_every_n_turns: int = Field(default=10, ge=0)      # SUMMARY_EVERY_N_TURNS

    # ── Modelos servidos pelo perfil (substituem AGENT_MODEL / INTERNAL_MODEL) ──
    # Resolução no genai-core: perfil → env → default. Vazio = comportamento
    # actual intacto (lê das env vars). Os nomes TÊM de corresponder a
    # deployments reais no OpenAI/Foundry do cliente (o Console garante isso).
    # Embeddings NUNCA são geridos aqui (parte o índice AI Search).
    agent_model: str = ""        # deployment GPT-5.x do agent (ex.: "gpt-5.4"); AGENT_MODEL
    internal_model: str = ""     # deployment do mini interno (ex.: "gpt-5.4-mini"); INTERNAL_MODEL

    # Esforço de raciocínio DEFAULT do agent, usado quando o request não traz
    # um modo do LLM picker. Mapeado no genai-core para reasoning_effort (GPT-5):
    #   fast → floor (none p/ 5.1+, minimal p/ 5.0) · balanced → medium · thinking → high
    # "auto": reservado para Azure Model Router — pressupõe que `agent_model` é
    # um deployment de router; o genai-core passa-lhe um effort base e deixa o
    # router escolher o modelo subjacente. Só aplicável ao agent (o interno é
    # sempre tratado como "fast").
    agent_mode: Literal["auto", "fast", "balanced", "thinking"] = "balanced"


class ProfileMemory(BaseModel):
    """Memória de utilizador (factos). Antes env vars (USER_MEMORY_*)."""
    model_config = ConfigDict(extra="allow")

    enabled: bool = True                                       # USER_MEMORY_ENABLED
    max_facts: int = Field(default=30, ge=0)                  # USER_MEMORY_MAX_FACTS


class ProfileToolLimits(BaseModel):
    """
    Limites de input/output. Sempre visíveis (nunca esconder/baixar limites).
    Os caps de render (diagram/chart/table/formula) juntam-se a este bloco com
    os defaults reais de código quando essas tools forem ligadas ao perfil.
    """
    model_config = ConfigDict(extra="allow")

    max_user_prompt_chars: int = Field(default=12000, ge=0)   # MAX_USER_PROMPT_CHARS
    max_attached_doc_chars: int = Field(default=250000, ge=0) # MAX_ATTACHED_DOC_CHARS


class ProfileQueryCache(BaseModel):
    """
    Cache de RESPOSTAS (semântico). Off por defeito — pode servir respostas
    menos afinadas. (O cache de resultados de tools e o prompt caching do
    Azure OpenAI são sempre-on internos, não vivem no perfil.)
    """
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    # Auditoria Jul 2026: lido pelo backend (chave de invalidação do cache de
    # queries — bump manual invalida tudo sem apagar docs).
    index_version: int = 1
    ttl_seconds: int = Field(default=86400, ge=0)


class ProfileAiDisclosure(BaseModel):
    """
    Aviso de IA — Art. 50(1) do EU AI Act (transparência, aplicável 02/08/2026):
    o utilizador tem de saber que comunica com um sistema de IA. On por defeito.
    Renderização (início da conversa / rodapé) é detalhe do frontend.
    """
    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    text: str = _DEFAULT_AI_DISCLOSURE
    textI18n: I18nMap = Field(default_factory=dict)   # mapa {lang:texto}; prevalece sobre `text`


# ─────────────────────────────────────────────────────────────────────────────
# Audio — Configuração da tool transcribe_audio por cliente
# ─────────────────────────────────────────────────────────────────────────────

class ProfileAudio(BaseModel):
    """Configuração da tool `transcribe_audio` por cliente (STT)."""
    model_config = ConfigDict(extra="allow")

    phrase_list: List[str] = Field(default_factory=list)
    phrase_bias: float = Field(default=5.0, ge=1.0, le=20.0)
    glossary: List[str] = Field(default_factory=list)
    disfluency_removal: bool = True
    max_speakers: int = Field(default=10, ge=1, le=36)
    max_duration_min: int = Field(default=120, ge=1, le=240)
    speech_locale: str = Field(default="pt-PT")


# ─────────────────────────────────────────────────────────────────────────────
# MCP — Model Context Protocol
# ─────────────────────────────────────────────────────────────────────────────

class ProfileMCPAuth(BaseModel):
    """Auth strategy de um MCP server. Segredos por NOME de env var / KV — nunca
    literais no perfil (env-agnostic, promove dev→prod sem expor segredos)."""
    model_config = ConfigDict(extra="allow")

    type: Literal["none", "bearer", "oauth2"] = "none"

    # Bearer
    token_env: Optional[str] = None  # preferido: nome de env var / secret KV
    token: Optional[str] = None      # apenas dev — literal (evitar)

    # OAuth 2.1 + PKCE
    client_id: Optional[str] = None
    client_id_env: Optional[str] = None
    client_secret: Optional[str] = None
    client_secret_env: Optional[str] = None
    scopes: List[str] = Field(default_factory=list)
    authorize_url: Optional[str] = None
    token_url: Optional[str] = None
    revocation_url: Optional[str] = None
    issuer: Optional[str] = None
    audience: Optional[str] = None       # Atlassian-specific
    per_user: bool = False               # default per-tenant


class ProfileMCPServer(BaseModel):
    """Um MCP server configurado no profile do cliente."""
    model_config = ConfigDict(extra="allow")

    name: str = Field(..., min_length=1, max_length=50)
    url: str = Field(..., min_length=1)
    auth: ProfileMCPAuth = Field(default_factory=ProfileMCPAuth)
    tool_prefix: Optional[str] = None  # default = name
    timeout_seconds: int = Field(default=30, ge=5, le=300)
    enabled: bool = True
    # trusted — o operador declara confiança neste server. A spec MCP trata
    # descrições/annotations do server como não-confiáveis salvo server de
    # confiança; quando True, a description de cada tool é exposta ao modelo
    # (higienizada); quando False (default seguro), usa-se descrição neutra.
    # Consumido no genai-core (tool_loader) ao construir as MCPTool.
    trusted: bool = False
    # erp — metadata OPCIONAL: declara que este server desempenha o papel de
    # ERP para uma fila (ex.: {"lookup_tool": "erp_get_customer_history"}). Lido
    # pelo resolver/gates; forma livre (extra="allow") enquanto estabiliza.
    erp: Optional[Dict[str, Any]] = None


class ProfileMCP(BaseModel):
    """Secção 'mcp' — lista de servers + cache de discovery. OFF por default."""
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    discovery_cache_ttl_seconds: int = Field(default=3600, ge=60, le=86400)
    servers: List[ProfileMCPServer] = Field(default_factory=list)
    # Auditoria Jul 2026 (fase 2/B do Multi-Perfil, já em produção no backend):
    # numa VARIANTE, desliga por NOME servers herdados do base (listas
    # substituem, não subtraem — isto resolve "o base tem, a persona não quer").
    disabledServers: List[str] = Field(default_factory=list)
    # Gate de confirmação de ações MCP (write/destructive). Lido pelo runtime
    # do genai-core (_confirm_actions_policy). "all_writes" = pede confirmação em
    # qualquer tool não-readonly; "destructive_only" = só nas marcadas destrutivas;
    # "never" = sem gate. Default no lado seguro.
    confirm_actions: Literal["all_writes", "destructive_only", "never"] = "all_writes"


class ProfileLanguage(BaseModel):
    model_config = ConfigDict(extra="allow")

    strategy: Literal["auto_detect", "restricted", "frontend_locked"] = "auto_detect"
    allowed: List[str] = Field(default_factory=lambda: ["*"])
    aliases: Dict[str, str] = Field(default_factory=lambda: dict(_DEFAULT_LANGUAGE_ALIASES))
    fallback: str = _DEFAULT_LANGUAGE_FALLBACK


class ProfileVoices(BaseModel):
    """
    Vozes TTS por locale (Azure Speech). Antes env vars (TTS_VOICE_*) — logo
    não-afináveis por cliente. O editor mostra um dropdown do catálogo real.
    """
    model_config = ConfigDict(extra="allow")

    by_locale: Dict[str, str] = Field(default_factory=lambda: dict(_DEFAULT_VOICES_BY_LOCALE))
    max_tts_chars: int = Field(default=8000, ge=0)   # MAX_TTS_CHARS
    phonetic_map: Dict[str, str] = Field(default_factory=dict)  # TTS_PHONETIC_MAP


# ─────────────────────────────────────────────────────────────────────────────
# Sub-modelos: lado frontend (consumido pelo endpoint /client-config)
# ─────────────────────────────────────────────────────────────────────────────

_HEX_COLOR_REGEX = r"^#[0-9A-Fa-f]{6}$"


class ProfileFrontendThemeMode(BaseModel):
    """Sub-tema light ou dark. Cores em hex `#RRGGBB`."""
    model_config = ConfigDict(extra="allow")

    bgPage: Optional[str] = Field(default=None, pattern=_HEX_COLOR_REGEX)
    bgSurface: Optional[str] = Field(default=None, pattern=_HEX_COLOR_REGEX)
    bgSubtle: Optional[str] = Field(default=None, pattern=_HEX_COLOR_REGEX)
    textPrimary: Optional[str] = Field(default=None, pattern=_HEX_COLOR_REGEX)
    textSecondary: Optional[str] = Field(default=None, pattern=_HEX_COLOR_REGEX)
    textTertiary: Optional[str] = Field(default=None, pattern=_HEX_COLOR_REGEX)
    userBubble: Optional[str] = Field(default=None, pattern=_HEX_COLOR_REGEX)
    codeBg: Optional[str] = Field(default=None, pattern=_HEX_COLOR_REGEX)
    codeText: Optional[str] = Field(default=None, pattern=_HEX_COLOR_REGEX)

    # ── Tokens de COMPONENTE (override fino; None = herda do semântico) ──
    headerBg: Optional[str] = Field(default=None, pattern=_HEX_COLOR_REGEX)
    inputBg: Optional[str] = Field(default=None, pattern=_HEX_COLOR_REGEX)
    traceBubbleBg: Optional[str] = Field(default=None, pattern=_HEX_COLOR_REGEX)
    sourcesBubbleBg: Optional[str] = Field(default=None, pattern=_HEX_COLOR_REGEX)
    sourceCardBg: Optional[str] = Field(default=None, pattern=_HEX_COLOR_REGEX)
    welcomeCardBg: Optional[str] = Field(default=None, pattern=_HEX_COLOR_REGEX)
    bgSidebarCollapsed: Optional[str] = Field(default=None, pattern=_HEX_COLOR_REGEX)
    iconSidebarColor: Optional[str] = Field(default=None, pattern=_HEX_COLOR_REGEX)
    iconHeaderColor: Optional[str] = Field(default=None, pattern=_HEX_COLOR_REGEX)
    iconInputColor: Optional[str] = Field(default=None, pattern=_HEX_COLOR_REGEX)

    bgSidebar: Optional[str] = Field(default=None, pattern=_HEX_COLOR_REGEX)
    bgSidebarSubtle: Optional[str] = Field(default=None, pattern=_HEX_COLOR_REGEX)
    textSidebarPrimary: Optional[str] = Field(default=None, pattern=_HEX_COLOR_REGEX)
    textSidebarSecondary: Optional[str] = Field(default=None, pattern=_HEX_COLOR_REGEX)
    textSidebarTertiary: Optional[str] = Field(default=None, pattern=_HEX_COLOR_REGEX)


class ProfileFrontendTheme(BaseModel):
    """Tema completo: sidebar (aplica a ambos os modos) + light + dark."""
    model_config = ConfigDict(extra="allow")

    bgSidebar: Optional[str] = Field(default=None, pattern=_HEX_COLOR_REGEX)
    bgSidebarSubtle: Optional[str] = Field(default=None, pattern=_HEX_COLOR_REGEX)
    textSidebarPrimary: Optional[str] = Field(default=None, pattern=_HEX_COLOR_REGEX)
    textSidebarSecondary: Optional[str] = Field(default=None, pattern=_HEX_COLOR_REGEX)
    textSidebarTertiary: Optional[str] = Field(default=None, pattern=_HEX_COLOR_REGEX)

    light: ProfileFrontendThemeMode = Field(default_factory=ProfileFrontendThemeMode)
    dark: ProfileFrontendThemeMode = Field(default_factory=ProfileFrontendThemeMode)


class ProfileFrontendBranding(BaseModel):
    model_config = ConfigDict(extra="allow")

    productName: str = ""
    subtitle: str = ""
    primaryColor: Optional[str] = Field(default=None, pattern=_HEX_COLOR_REGEX)
    primaryTextColor: Optional[str] = Field(default=None, pattern=_HEX_COLOR_REGEX)
    # logos/favicon: URL no container `branding` (upload via Console).
    logoLight: str = ""
    logoDark: str = ""
    logoRail: str = ""
    favicon: str = ""
    # Texto ao lado do logo no header (ex.: "Antonius"). Multilingue (data-driven);
    # cor/tamanho opcionais (vazios = default do tema).
    headerText: I18nMap = Field(default_factory=dict)
    headerTextColor: Optional[str] = Field(default=None, pattern=_HEX_COLOR_REGEX)
    headerTextSize: str = ""   # ex.: "20px" / "1.25rem"
    disclaimer: str = ""   # rodapé geral (≠ ai_disclosure, que é o aviso legal)
    disclaimerI18n: I18nMap = Field(default_factory=dict)   # mapa {lang:texto}; prevalece sobre `disclaimer`
    theme: ProfileFrontendTheme = Field(default_factory=ProfileFrontendTheme)


class ProfileFrontendQuickInsightQuestion(BaseModel):
    """Pergunta dentro de um quick insight expansível (accordion).
    `prompt` omitido → a label é enviada como pergunta."""
    model_config = ConfigDict(extra="allow")

    label: Union[str, I18nMap] = ""
    prompt: Optional[Union[str, I18nMap]] = None


class ProfileFrontendQuickInsight(BaseModel):
    """Atalho fixo do painel de insights. Dois modos:
    `prompt` = atalho direto (1 clique); `questions` = card expansível
    com perguntas dentro (mockup Live Insights). i18n em label/prompt."""
    model_config = ConfigDict(extra="allow")

    id: str = ""
    label: Union[str, I18nMap] = ""
    prompt: Optional[Union[str, I18nMap]] = None
    questions: List[ProfileFrontendQuickInsightQuestion] = Field(default_factory=list)
    icon: str = ""


class ProfileFrontendProviderBadge(BaseModel):
    """Pill de provider no header do painel (ex.: "Xero · Ligado").
    Estado é CONFIGURADO (a integração existe no perfil), não health-check —
    evolução para estado real-time anotada no fecore. `label` i18n; `icon`
    opcional (emoji). Fecha a dívida declarada da sessão Xero (v0.1.25)."""
    model_config = ConfigDict(extra="allow")

    label: Union[str, I18nMap] = ""
    icon: Optional[str] = None


class ProfileFrontendInsightsPanel(BaseModel):
    """Painel de insights (épico "Painel como dashboard", Jul 2026).

    `panelTypes` é lido pelo BACKEND (política de placement: visuais destes
    tipos são projetados no painel em vez de inline); o resto é consumido
    pelo fecore via /client-config. Secção pensada para crescer com os
    agentes de ERP (Xero/PHC/SAP)."""
    model_config = ConfigDict(extra="allow")

    title: Union[str, I18nMap] = ""
    openOnLoad: bool = False
    panelTypes: List[str] = Field(default_factory=list)
    quickInsights: List[ProfileFrontendQuickInsight] = Field(default_factory=list)
    providerBadge: Optional[ProfileFrontendProviderBadge] = None


class ProfileFrontendLanguage(BaseModel):
    model_config = ConfigDict(extra="allow")

    default: str = "pt"
    enabled: List[str] = Field(default_factory=lambda: ["pt", "en"])


class ProfileFrontendFeatures(BaseModel):
    """
    Flags do frontend. `extra='allow'` — features futuras adicionadas ao schema
    aparecem no editor automaticamente (schema-driven), sem mexer no editor.

    Dependências declaradas em json_schema_extra → o editor avisa e impede
    combinações incoerentes (ex.: upload on sem a tool de leitura).
    """
    model_config = ConfigDict(extra="allow")

    enableLlmSelector: bool = Field(
        default=False,
        json_schema_extra={"requires_field": "frontend.llmModels"},
    )
    enableShare: bool = False
    enableDocumentUpload: bool = Field(
        default=False,
        json_schema_extra={"requires_tool": "read_attached_document"},
    )
    enableTTS: bool = False
    turnOnVoiceRecorder: bool = Field(
        default=False,
        json_schema_extra={"requires_tool": "transcribe_audio"},
    )
    enableVoiceLoop: bool = Field(
        default=False,
        json_schema_extra={"requires_tool": "transcribe_audio"},
    )
    enablePdfExport: bool = True
    enableSourcePreview: bool = True
    # Ação ao clicar numa fonte (substitui o all-or-nothing do enableSourcePreview):
    #   inline → painel de preview embebido (default; equivale a enableSourcePreview=true)
    #   newtab → abre a fonte em nova tab (browser decide preview/download pelo Content-Type)
    #   none   → fontes visíveis mas NÃO clicáveis (equivale a enableSourcePreview=false)
    # enableSourcePreview é mantido em sincronia pelo validator abaixo, para builds
    # antigos do fecore que ainda leem o booleano.
    sourceClickAction: Literal["inline", "newtab", "none"] = "inline"
    enableInlineCitations: bool = True
    enablePipelineTrace: bool = True   # on: transparência + resumo de explainability
    showHistory: bool = True
    enableStarterPrompts: bool = True
    enableDarkMode: bool = False
    # Fila de revisão human-in-the-loop (Jul 2026) — rota /fila do fecore.
    # Ativa-se por esta flag no perfil (+ container Cosmos `review_queue`). A env
    # REVIEW_QUEUE_ENABLED no genai-core é só kill-switch opcional (força on/off).
    # Default false: só liga onde for contratado.
    reviewQueue: bool = False
    # Modo "só fila" (Jul 2026): esconde a navegação de volta ao chat na rota
    # /fila E redireciona o chat para /fila — para perfis de operadores que
    # devem usar APENAS a fila de revisão (ex.: backoffice Salmon). Só faz
    # sentido com reviewQueue=true; o fecore ignora-a se a fila estiver off.
    # Flui para o frontend via /client-config como qualquer campo deste bloco.
    reviewQueueOnly: bool = False
    # Task API assíncrona (/tasks) no genai-core: pedidos longos com task_id +
    # polling/webhook. OFF por defeito; liga onde um produto precise. (env
    # TASK_API_ENABLED continua a funcionar como fallback.)
    taskApi: bool = False
    # Arquivar os ficheiros ORIGINais dos uploads (ex.: PDF da fatura) para
    # auditoria. Auto-liga já se o cliente tiver extract_invoice/generate_boq;
    # esta flag força explicitamente on/off. (env PERSIST_ORIGINALS = fallback.)
    persistOriginals: bool = False
    # REMOVIDOS (campos mortos, nenhum componente os lia):
    #   showQuestionsMenu, enableFollowupSuggestions
    # REMOVIDO enableFeedback: feedback é sempre-on no frontend, sem flag.
    # REMOVIDO enableHybridSearch: hybrid search (vetorial+keyword) é sempre-on
    #   no retrieval do backend, sem flag — desligá-lo só piora a qualidade.

    @model_validator(mode="before")
    @classmethod
    def _source_click_coherence(cls, data):
        """Mantém sourceClickAction ↔ enableSourcePreview coerentes.
        Novo campo manda; se ausente, deriva do legacy (true→inline, false→none).
        Assim perfis antigos (só booleano) e builds antigos (só booleano) funcionam."""
        if not isinstance(data, dict):
            return data
        action = data.get("sourceClickAction")
        if action in ("inline", "newtab", "none"):
            data["enableSourcePreview"] = (action == "inline")
        elif "enableSourcePreview" in data:
            data["sourceClickAction"] = "inline" if data.get("enableSourcePreview") else "none"
        return data


class StarterPrompt(BaseModel):
    """
    Sugestão de prompt no ecrã inicial. i18n DATA-DRIVEN: `title` e `prompt` são
    mapas {lang:texto} ({ "pt": "...", "en": "...", ... }) que suportam N línguas.
    Retrocompat: se vierem os campos legacy (titlePT/titleEN/titleES/promptPT/…),
    são convertidos para os mapas (sem os remover, para não partir leitores antigos).
    """
    model_config = ConfigDict(extra="allow")

    iconName: str = ""   # editor: picker visual (manifesto de ícones do frontend)
    title: I18nMap = Field(default_factory=dict)    # {lang:texto}
    prompt: I18nMap = Field(default_factory=dict)   # {lang:texto}

    @model_validator(mode="before")
    @classmethod
    def _i18n_from_legacy(cls, data):
        """Constrói title/prompt (mapas) a partir dos campos legacy se ausentes."""
        if not isinstance(data, dict):
            return data
        if not data.get("title"):
            t = {}
            if data.get("titlePT"): t["pt"] = data["titlePT"]
            if data.get("titleEN"): t["en"] = data["titleEN"]
            if data.get("titleES"): t["es"] = data["titleES"]
            if t:
                data["title"] = t
        if not data.get("prompt"):
            pr = {}
            if data.get("promptPT"): pr["pt"] = data["promptPT"]
            if data.get("promptEN"): pr["en"] = data["promptEN"]
            if data.get("promptES"): pr["es"] = data["promptES"]
            if pr:
                data["prompt"] = pr
        return data


class ProfileFrontendWidget(BaseModel):
    """
    Widget embebível (épico widget core-único, Jun 2026) — configura o
    `assets/widget.js` genérico servido pela SWA do próprio cliente.
    O site do cliente cola UMA linha de script; tudo o resto vem daqui
    (via /client-config ou do snapshot assets/client-config.json).
    """
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    mode: Literal["bubble", "inline"] = "bubble"
    position: Literal["bottom-right", "bottom-left"] = "bottom-right"
    offset_x_px: int = Field(20, ge=0)                   # afinar ao pixel (cookie banners etc.)
    offset_y_px: int = Field(20, ge=0)
    # None → cai em branding.primaryColor (nunca '' — padrão das cores do schema)
    bubble_color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    bubble_icon_url: str = ""                            # "" → favicon/logoRail do branding;
                                                        # aceita URL https ou data URI (o Console
                                                        # redimensiona a imagem anexada antes de gravar)
    # Diâmetro da bolha. 56 é o valor histórico (era hardcoded no CSS do
    # widget.js); o ícone interno e a posição do balão de saudação derivam
    # deste número. Limites largos de propósito — há sites que querem uma
    # bolha discreta e outros que a querem bem visível.
    bubble_size_px: int = Field(56, ge=32, le=128)
    # Tamanho do ÍCONE dentro da bolha, em % do diâmetro. 54 = proporção
    # histórica (30/56). Logos com muito padding precisam de 70-90 para não
    # ficarem "afogados" na cor da bolha.
    bubble_icon_scale_pct: int = Field(54, ge=30, le=100)
    bubble_label: I18nMap = Field(default_factory=dict)  # pill de texto na bolha (opcional)
    greeting: I18nMap = Field(default_factory=dict)      # balão de saudação proativa (default OFF: vazio)
    greeting_delay_s: int = Field(3, ge=0)
    panel_width_px: int = Field(420, ge=320)
    panel_height_px: int = Field(640, ge=480)
    # [] = qualquer site https pode embeber (frame-ancestors https:);
    # não-vazio → o creator escreve frame-ancestors 'self' + estas origens.
    allowed_origins: List[str] = Field(default_factory=list)


class ProfileAuthProvider(BaseModel):
    """
    Emissor OIDC confiável para o genai-core VALIDAR tokens (L1, multi-IdP).
    O `issuer` é a chave de pinning. Lido do perfil pelo backend; NÃO vai ao
    runtime-config do FE. `extra='allow'` para evolução sem migração.
    """
    model_config = ConfigDict(extra="allow")

    id: str = ""                                            # identificador interno do provider
    type: Literal["oidc", "msal"] = "oidc"
    issuer: str = ""                                        # iss esperado (pinning)
    audience: str = ""                                      # aud esperado (vazio → não valida aud)
    jwks_uri: str = ""                                      # vazio → discovery via .well-known do issuer
    required_scope: str = ""                                # scope obrigatório (vazio → não exige)
    tenant_id: str = ""                                     # tid esperado (MS; vazio → não valida)
    label: str = ""                                         # rótulo amigável para a UI do Console
    primary: bool = False                                   # emissor primário → user_id puro (oid/sub); adicionais ficam namespaced (issuer|sub). Sem nenhum marcado, o 1.º da lista é o primário.


class ProfileWidgetIdentity(BaseModel):
    """
    Identidade de widget por token assinado (L2). O segredo HMAC vive no Key
    Vault do cliente (`secret_ref`); o genai-core valida assinatura + idade.
    Backend-only — não vai ao runtime-config do FE.
    """
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    secret_ref: str = ""                                    # nome do secret no Key Vault do cliente
    algo: Literal["HS256", "HS384", "HS512"] = "HS256"
    max_age_s: int = Field(default=300, ge=1)               # idade máxima do token (anti-replay)


class ProfileFrontendAuth(BaseModel):
    """
    Autenticação do frontend + identidade (épico multi-IdP, Jun 2026).

    Campos FE (escritos no runtime-config.json da SWA, por cliente):
      - msal: clientId / tenantId / tenantMode / apiScopes / loginType
      - oidc: authority / clientId / scope
    Campos backend (lidos pelo genai-core do PERFIL; NÃO vão ao runtime-config):
      - providers[]      → validação multi-issuer com pinning (L1)
      - widget_identity  → identidade de widget por token assinado (L2)
    """
    model_config = ConfigDict(extra="allow")

    mode: Literal["none", "optional", "required"] = "optional"
    provider: Literal["msal", "oidc"] = "msal"

    # MSAL (Microsoft)
    tenantMode: Literal["single", "multi"] = "single"
    clientId: str = ""
    tenantId: str = ""
    apiScopes: List[str] = Field(default_factory=list)
    loginType: Literal["redirect", "popup"] = "redirect"

    # OIDC genérico (login do FE)
    authority: str = ""                                     # URL do IdP (authority/issuer)
    scope: str = ""                                         # vazio → default seguro no FE

    # Backend — validação de tokens (L1) e identidade de widget (L2)
    providers: List[ProfileAuthProvider] = Field(default_factory=list)
    widget_identity: ProfileWidgetIdentity = Field(default_factory=ProfileWidgetIdentity)


class ProfileFrontend(BaseModel):
    """
    Sub-bloco PÚBLICO do profile — consumido pelo endpoint /client-config.
    O backend ignora este nó; só o Angular do utilizador final o lê.
    """
    model_config = ConfigDict(extra="allow")

    branding: ProfileFrontendBranding = Field(default_factory=ProfileFrontendBranding)
    language: ProfileFrontendLanguage = Field(default_factory=ProfileFrontendLanguage)
    # Painel de insights: None quando ausente (não materializa em perfis que
    # não o usam — mesmo padrão do `auth`). Tipado desde Jul 2026; perfis
    # anteriores com a secção via extra="allow" continuam válidos.
    insightsPanel: Optional[ProfileFrontendInsightsPanel] = None
    features: ProfileFrontendFeatures = Field(default_factory=ProfileFrontendFeatures)
    widget: ProfileFrontendWidget = Field(default_factory=ProfileFrontendWidget)
    # Auth/identidade. Opcional (= None quando ausente) para NÃO materializar um
    # bloco em perfis que caíam no default do environment — retrocompat total.
    auth: Optional[ProfileFrontendAuth] = None
    sttPhraseList: List[str] = Field(default_factory=list)
    sttSilenceTimeoutMs: int = Field(default=3500, ge=0)
    starterPrompts: List[StarterPrompt] = Field(default_factory=list)
    ttsPhoneticMap: Dict[str, str] = Field(default_factory=dict)
    ttsVoiceMap: Dict[str, str] = Field(default_factory=lambda: {
        "pt": "pt-PT-RaquelNeural",
        "en": "en-US-Ava:DragonHDLatestNeural",
        "es": "es-ES-ElviraNeural",
    })
    # Lista de modelos do LLM picker — só relevante quando enableLlmSelector=true.
    # Alimentada no editor pelos modelos realmente deployed no OpenAI do cliente.
    llmModels: List[str] = Field(default_factory=list)
    aiDisclosure: ProfileAiDisclosure = Field(default_factory=ProfileAiDisclosure)
    # Título de boas-vindas do empty-state — mapa i18n {lang:texto}.
    welcomeMessage: I18nMap = Field(default_factory=dict)
    welcomeMessageSize: str = ""   # tamanho da fonte do título de boas-vindas (ex.: "1.5rem")
    welcomeSubtitle: I18nMap = Field(default_factory=dict)   # subtítulo de apresentação abaixo do título (markdown, multilingue)
    legalNotice: I18nMap = Field(default_factory=dict)   # aviso legal recolhível no ecrã inicial (markdown, multilingue)
    # Política de privacidade DO CLIENTE (GDPR) — substitui o placeholder
    # genérico do modal de login. Precedência no FE: privacyPolicyUrl (abre
    # nova aba) → privacyPolicyI18n (markdown no modal) → texto default.
    privacyPolicyUrl: str = ""                            # URL da política do cliente (recomendado)
    privacyPolicyI18n: I18nMap = Field(default_factory=dict)  # alternativa: texto markdown multilingue no modal
    # Género gramatical do assistente (afeta artigos nas labels fixas do FE).
    assistantGender: Literal["feminine", "masculine", "neutral"] = "masculine"


# ─────────────────────────────────────────────────────────────────────────────
# Compliance — EU AI Act (metadata de conformidade por deployment)
# ─────────────────────────────────────────────────────────────────────────────

class ProfileComplianceClassification(BaseModel):
    """
    Classificação de risco EU AI Act por deployment (Anexo III).

    Preenchida pela checklist do Console (tab Conformidade). O default
    `unclassified` torna visível no Dashboard o trabalho por fazer.
    `annex_iii_answers` guarda as respostas (área → bool) para auditoria
    e comparação em re-avaliações.
    """
    model_config = ConfigDict(extra="allow")

    risk_level: Literal["minimal", "limited", "high", "unclassified"] = "unclassified"
    justification: str = ""          # justificação humana (auto-gerada + editável)
    annex_iii_answers: Dict[str, bool] = Field(default_factory=dict)
    classified_by: str = ""          # quem classificou (nome/email)
    classified_at: str = ""          # ISO datetime
    reviewed_by_legal: bool = False  # jurista validou (opcional; não bloqueia `limited`)
    legal_review_date: str = ""
    legal_reviewer: str = ""
    next_review_due: str = ""        # re-avaliar anualmente / em mudança de uso


class ProfileComplianceHighRisk(BaseModel):
    """
    Obrigações extra SÓ para deployments high-risk (Arts. 11/12/14/73).
    O Console exige `enabled=True` + campos preenchidos antes de prod
    quando risk_level == "high". Sem efeito funcional no genai-core (v1).
    """
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    log_retention_days: int = Field(default=365, ge=180)  # Art. 12 — mínimo legal 6 meses
    human_oversight_contact: str = ""    # Art. 14 — responsável humano designado
    oversight_procedure_url: str = ""    # link p/ procedimento interno
    serious_incident_contact: str = ""   # Art. 73 — reporting de incidentes graves


class ProfileCompliance(BaseModel):
    """
    Bloco de conformidade EU AI Act — metadata, sem efeito funcional no
    data plane (v1). Fonte de verdade para o badge ⚖️ do Dashboard, a tab
    Conformidade do editor e o gerador de documentação Anexo IV.
    """
    model_config = ConfigDict(extra="allow")

    classification: ProfileComplianceClassification = Field(default_factory=ProfileComplianceClassification)
    high_risk: ProfileComplianceHighRisk = Field(default_factory=ProfileComplianceHighRisk)
    # Transparência Art. 50 — responsabilidade do conteúdo indexado é do
    # deployer (cliente), formalizada por cláusula contratual.
    deployer_content_responsibility: bool = True
    annex_iv_doc_url: str = ""        # link p/ documentação técnica gerada (blob)
    annex_iv_generated_at: str = ""   # ISO datetime da última geração


# ═════════════════════════════════════════════════════════════════════════════
# Atendimento / Casos (v0.1.32, Jul 2026) — voz, contactos, ingest e filas de
# revisão genéricas. TODOS extra="allow" e opcionais: um perfil existente
# (Salmon) valida sem alteração — o typing é um SUPERSET permissivo. As listas
# da fila default a None (não []) DE PROPÓSITO: é assim que o caminho LEGADO
# continua exato (spec_for_queue só ativa a máquina custom com states E actions
# presentes; ausentes/None ⇒ máquina embutida intocada).
# ─────────────────────────────────────────────────────────────────────────────

class ProfileVoiceTranscription(BaseModel):
    """Transcrição integral verbatim da chamada (OPT-IN; RGPD: a câmara é o
    responsável pelo tratamento). `model` = NOME de deployment de transcrição
    (não usar família gpt-4o). OFF por default → só o resumo reconstituído."""
    model_config = ConfigDict(extra="allow", protected_namespaces=())
    enabled: bool = False
    retention_days: Optional[int] = None
    model: Optional[str] = None


class ProfileVoice(BaseModel):
    """Canal de voz telefónico (Realtime). Comportamento por cliente; os
    segredos (VOICE-OPENAI-ENDPOINT/API-KEY/WEBHOOK-SECRET) vivem no Key Vault,
    NUNCA aqui. OFF por default."""
    model_config = ConfigDict(extra="allow",
                              json_schema_extra={"requires_field": "reviewQueues"})
    enabled: bool = False
    deployment: str = ""          # ex.: gpt-realtime-2.1-mini
    voice: str = "marin"
    language: str = "pt-PT"
    greeting: str = ""
    instructions: str = ""
    queue: str = "tickets"        # fila de tickets (reviewQueues.<queue>)
    transfer_number: str = ""
    kb_top_n: int = 4
    transcription: ProfileVoiceTranscription = Field(default_factory=ProfileVoiceTranscription)


class ProfileContacts(BaseModel):
    """Contacto/entidade unificado — identidade DETERMINÍSTICA entre canais
    (telefone/email/whatsapp/user_id). Isolado por-tenant (o container Cosmos
    é a fronteira). OFF por default. Ver core/managers/contact_store.py."""
    model_config = ConfigDict(extra="allow")
    enabled: bool = False
    identity_fields: Optional[List[Dict[str, Any]]] = None   # [{kind, path}]
    display_name_path: Optional[str] = None
    attribute_paths: Optional[Dict[str, str]] = None


class ProfileIngestAlerts(BaseModel):
    """Sweep de aging/exceções no fim do job de ingestão. OFF por default."""
    model_config = ConfigDict(extra="allow")
    enabled: bool = False
    aging_hours: float = 24        # nunca reduzir por poupança
    email: str = ""
    email_interval_hours: float = 6


class ProfileIngest(BaseModel):
    """Ingestão por email (job Container Apps, cron). Cada fonte em `sources`
    é livre (mailbox/classifier/extraction/reply/…) — extra="allow"."""
    model_config = ConfigDict(extra="allow")
    sources: Optional[List[Dict[str, Any]]] = None
    alerts: ProfileIngestAlerts = Field(default_factory=ProfileIngestAlerts)


class ProfileReviewQueueState(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str = ""
    kind: Literal["open", "parked", "final"] = "open"
    label: str = ""


class ProfileReviewQueueAction(BaseModel):
    """Ação da máquina de estados. NOTA: a origem `from` é palavra reservada em
    Python — não é campo tipado; fica em extra="allow" (preservada byte a byte
    no round-trip). Ex.: {"id":"resolver","from":["triaged"],"to":"resolved"}."""
    model_config = ConfigDict(extra="allow")
    id: str = ""
    to: str = ""
    note_required: bool = False
    label: str = ""


class ProfileReviewQueueNotification(BaseModel):
    model_config = ConfigDict(extra="allow")
    when: str = ""                 # "create" ou id de uma ação
    channel: Literal["sms", "whatsapp"] = "sms"
    to: str = ""                   # dot-path (ex.: payload.citizen.telefone)
    text: str = ""


class ProfileReviewQueueGate(BaseModel):
    """Gate numa transição: chama uma tool MCP e traduz a decisão em
    consequência (proceed | block | <estado alternativo>)."""
    model_config = ConfigDict(extra="allow")
    when: str = ""                 # id da ação a que o gate se aplica
    call: Optional[Dict[str, Any]] = None    # {server, tool, mapping}
    decide: Optional[Dict[str, str]] = None  # resultado → consequência


class ProfileReviewQueueTrigger(BaseModel):
    """Automação da fila. NOTA: `if` é palavra reservada — fica em extra="allow"
    (condições dot-path→valor). `when` = {"event": "create|action:x|state:y"}
    (ou lista) OU {"schedule": {"status","older_than_hours"}}. `do` = lista de
    passos {type: notify|call|transition, …}. Ver review_queue_triggers.py."""
    model_config = ConfigDict(extra="allow")
    id: str = ""
    when: Optional[Dict[str, Any]] = None
    do: Optional[List[Dict[str, Any]]] = None


class ProfileReviewQueue(BaseModel):
    """Uma fila de revisão human-in-the-loop, genérica e configurável. TUDO
    opcional; as LISTAS default a None (não []) para o caminho legado (Salmon)
    continuar exato. `onValidate`/`onIngest` e afins ficam em extra="allow"."""
    model_config = ConfigDict(extra="allow")
    label: str = ""
    states: Optional[List[ProfileReviewQueueState]] = None
    actions: Optional[List[ProfileReviewQueueAction]] = None
    businessKey: Optional[Dict[str, Any]] = None
    notifications: Optional[List[ProfileReviewQueueNotification]] = None
    gates: Optional[List[ProfileReviewQueueGate]] = None
    triggers: Optional[List[ProfileReviewQueueTrigger]] = None
    fields: Optional[List[Dict[str, Any]]] = None
    onValidate: Optional[Dict[str, Any]] = None
    # Auditoria Jul 2026: campo de observações do operador na /fila (lido pelo
    # _queue_options do backend; vale também para filas legado sem spec).
    operatorNotes: bool = False
    onIngest: Optional[Dict[str, Any]] = None


# ─────────────────────────────────────────────────────────────────────────────
# Schema root
# ─────────────────────────────────────────────────────────────────────────────

class ProfileMultiProfile(BaseModel):
    """
    Multi-perfil por link (Épico Multi-Perfil — Julho 2026, v0.1.34).

    Presente APENAS no perfil BASE do cliente. Liga o modo em que um backend
    serve N experiências (variantes) escolhidas pelo slug do link (?uc=<slug>
    → header X-Genesis-Profile-Slug). Cada variante é um blob completo
    `<client>-<env>__<slug>.json` no mesmo storage central.

    Regras (decisões de 17 Jul 2026):
      • enabled=false (default) → modo adormecido, header ignorado por
        completo. Clientes sem o bloco são byte a byte o comportamento atual.
      • slugs = whitelist ativa; disabledSlugs = desativadas sem apagar o blob.
      • Slug inválido/desativado → 403 unknown_profile_slug no backend, página
        explícita brandada no frontend. NUNCA fallback silencioso para o base.
      • O multi-perfil nunca atravessa fronteiras entre clientes — só escolhe
        a variante DENTRO do mesmo tenant/cliente.
    """
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    slugs: List[str] = Field(default_factory=list)
    disabledSlugs: List[str] = Field(default_factory=list)
    # Fixo na fase 1; a fase 2 pode ganhar opções (ex.: redirect).
    invalidSlugBehavior: Literal["error_page"] = "error_page"


class ProfilePricingModel(BaseModel):
    """Preços por 1M tokens em USD (alinhado com a tabela builtin do backend;
    a conversão EUR é feita no cálculo)."""
    model_config = ConfigDict(extra="allow")

    input_per_1m: float = 0.0
    output_per_1m: float = 0.0
    cached_input_per_1m: float = 0.0


class ProfilePricing(BaseModel):
    """
    Overrides de preços por modelo (Auditoria Jul 2026 — o backend lê
    `client_profile.pricing` desde o M5.1 mas o bloco nunca foi tipado).

    Vazio (default) = tabela builtin do backend (pricing_defaults.py).
    `models`: nome do modelo → preços token; `image_models`: nome → preços
    por tier de qualidade (low/medium/high, por imagem, USD).
    """
    model_config = ConfigDict(extra="allow")

    currency: str = ""
    models: Dict[str, ProfilePricingModel] = Field(default_factory=dict)
    image_models: Dict[str, Dict[str, float]] = Field(default_factory=dict)


class ProfileGuestAccessUploads(BaseModel):
    """Uploads de CONVIDADOS numa demo (Épico Demos, v0.1.35).

    OFF por defeito mesmo com o Modo Convidado ligado — uploads públicos
    anónimos são o maior risco. A variante que os precisa (ex.: faturas)
    liga explicitamente, sempre com aperto.
    """
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    pdfOnly: bool = True
    maxMb: int = 10
    maxFiles: int = 3     # por CONVERSA, não por pedido


class ProfileGuestAccessRateLimits(BaseModel):
    """Limites de rate para convidados (mais apertados que os default do
    backend). None = usa env GUEST_RATE_LIMIT_PER_* › defaults (10/100/300).
    Chave de limite por visitante: guest:<id> (resolve NAT partilhado)."""
    model_config = ConfigDict(extra="allow")

    perMinute: Optional[int] = None
    perHour: Optional[int] = None
    perDay: Optional[int] = None


class ProfileGuestAccess(BaseModel):
    """
    Modo Convidado (Épico Demos Marketplace — Julho 2026, v0.1.35).

    Permite que uma VARIANTE de demo seja usada num marketplace público sem
    login: o visitante recebe identidade automática `guest:<aleatório>` na
    primeira interação — tickets/uploads/conversas continuam com dono.

    FECHO DUPLO (regra inviolável): este bloco SÓ atua em backends com a env
    `DEMO_ENVIRONMENT=1` no Container App — posta à mão no provisionamento,
    NUNCA automatizada. Num backend de cliente real, o bloco é inerte byte a
    byte, mesmo copiado por engano. enabled=false (default) = tudo inerte,
    como mcp/audio/voice.

    dailyBudgetEur: orçamento diário da variante. Ao estoirar, o slug entra
    automaticamente nos multiProfile.disabledSlugs (403 brandado) e religa à
    meia-noite UTC. 0 = sem orçamento.
    """
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    uploads: ProfileGuestAccessUploads = Field(default_factory=ProfileGuestAccessUploads)
    rateLimits: ProfileGuestAccessRateLimits = Field(default_factory=ProfileGuestAccessRateLimits)
    dailyBudgetEur: float = 0.0


class ClientProfileSchema(BaseModel):
    """
    Schema completo do profile (backend + frontend num só JSON) — o contrato.

    Usado por:
      - POST /admin/profile/validate (dry-run, sem escrever)
      - PUT  /admin/profile/save     (valida antes de escrever no Blob)
      - GET  /admin/profile/schema   (devolve model_json_schema p/ o editor)
      - creator/migração: base = ClientProfileSchema().to_blob_dict()
    """
    model_config = ConfigDict(extra="allow")

    identity: ProfileIdentity = Field(default_factory=ProfileIdentity)
    personality: ProfilePersonality = Field(default_factory=ProfilePersonality)
    domain: ProfileDomain = Field(default_factory=ProfileDomain)
    custom_instructions: str = ""
    response: ProfileResponse = Field(default_factory=ProfileResponse)
    guardrails: ProfileGuardrails = Field(default_factory=ProfileGuardrails)
    product_identification: ProfileProductIdentification = Field(default_factory=ProfileProductIdentification)
    brand_safety: ProfileBrandSafety = Field(default_factory=ProfileBrandSafety)
    system_prompt_disclaimers: List[str] = Field(default_factory=list)
    tools: ProfileTools = Field(default_factory=ProfileTools)
    tool_limits: ProfileToolLimits = Field(default_factory=ProfileToolLimits)
    retrieval: ProfileRetrieval = Field(default_factory=ProfileRetrieval)
    orchestration: ProfileOrchestration = Field(default_factory=ProfileOrchestration)
    runtime: ProfileRuntime = Field(default_factory=ProfileRuntime)
    memory: ProfileMemory = Field(default_factory=ProfileMemory)
    mcp: ProfileMCP = Field(default_factory=ProfileMCP)
    audio: ProfileAudio = Field(default_factory=ProfileAudio)
    voices: ProfileVoices = Field(default_factory=ProfileVoices)
    query_cache: ProfileQueryCache = Field(default_factory=ProfileQueryCache)
    language: ProfileLanguage = Field(default_factory=ProfileLanguage)

    # ── Atendimento / Casos (v0.1.32) — todos OFF/vazios por default; um perfil
    # que não os use materializa-os inertes, como já acontece com mcp/audio/etc.
    voice: ProfileVoice = Field(default_factory=ProfileVoice)
    contacts: ProfileContacts = Field(default_factory=ProfileContacts)
    ingest: ProfileIngest = Field(default_factory=ProfileIngest)
    reviewQueues: Dict[str, ProfileReviewQueue] = Field(default_factory=dict)

    # Multi-perfil por link (v0.1.34) — só tem efeito no perfil BASE; inerte
    # por default (enabled=false), como mcp/audio/voice/etc.
    multiProfile: ProfileMultiProfile = Field(default_factory=ProfileMultiProfile)

    # Modo Convidado para demos (v0.1.35) — só tem efeito em VARIANTES servidas
    # por backends com env DEMO_ENVIRONMENT (fecho duplo); inerte por default.
    guestAccess: ProfileGuestAccess = Field(default_factory=ProfileGuestAccess)

    # Overrides de preços por modelo (Auditoria v0.1.35) — vazio = tabela
    # builtin do backend. Consumido pelo cálculo de custos (M5.1).
    pricing: ProfilePricing = Field(default_factory=ProfilePricing)

    # Bloco de conformidade EU AI Act — metadata (Console/auditoria), sem
    # efeito funcional no genai-core (v1).
    compliance: ProfileCompliance = Field(default_factory=ProfileCompliance)

    # Bloco frontend — consumido pelo /client-config.
    frontend: ProfileFrontend = Field(default_factory=ProfileFrontend)

    def to_blob_dict(self) -> dict:
        """Serialização para escrita no Blob. mode='json' garante JSON-safe."""
        return self.model_dump(mode="json")
