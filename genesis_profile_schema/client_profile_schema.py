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
    """
    model_config = ConfigDict(extra="allow")

    title: str = ""                                # título do cartão; "" = default da tool
    field_schema: Dict[str, Union[ProfileLegalExtractFieldSpec, str]] = Field(
        default_factory=dict,
        alias="schema",
        json_schema_extra={"requires_tool": "extract_legal_terms"},
    )


# Mapa key de tools.config → model tipado. Tools fora deste mapa passam sem
# validação estrutural (estrutura aberta, como sempre).
_KNOWN_TOOL_CONFIG_MODELS: Dict[str, Any] = {
    "search_web": ProfileToolSearchWebConfig,
    "generate_image": ProfileToolGenerateImageConfig,
    "extract_legal_terms": ProfileToolLegalExtractConfig,
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


class ProfileRetrieval(BaseModel):
    """
    Knobs de RAG/retrieval por cliente. Antes só env vars (KB_*, RAG_*) — logo
    invisíveis e não-afináveis por cliente no Console. Agora no perfil.

    Regra: qualidade acima de custo. Sem limites superiores — na dúvida, subir.
    """
    model_config = ConfigDict(extra="allow")

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


class ProfileMCP(BaseModel):
    """Secção 'mcp' — lista de servers + cache de discovery. OFF por default."""
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    discovery_cache_ttl_seconds: int = Field(default=3600, ge=60, le=86400)
    servers: List[ProfileMCPServer] = Field(default_factory=list)
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
    # Exige REVIEW_QUEUE_ENABLED=true no genai-core do cliente + container
    # Cosmos `review_queue`. Default false: só liga onde for contratado.
    reviewQueue: bool = False
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
    bubble_icon_url: str = ""                            # "" → favicon/logoRail do branding
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


# ─────────────────────────────────────────────────────────────────────────────
# Schema root
# ─────────────────────────────────────────────────────────────────────────────

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

    # Bloco de conformidade EU AI Act — metadata (Console/auditoria), sem
    # efeito funcional no genai-core (v1).
    compliance: ProfileCompliance = Field(default_factory=ProfileCompliance)

    # Bloco frontend — consumido pelo /client-config.
    frontend: ProfileFrontend = Field(default_factory=ProfileFrontend)

    def to_blob_dict(self) -> dict:
        """Serialização para escrita no Blob. mode='json' garante JSON-safe."""
        return self.model_dump(mode="json")
