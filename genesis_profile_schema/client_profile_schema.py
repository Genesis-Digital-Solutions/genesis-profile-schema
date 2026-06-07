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

from typing import Any, Dict, List, Literal, Optional
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


class ProfileTools(BaseModel):
    model_config = ConfigDict(extra="allow")

    # Baseline RAG documental. O catálogo vivo do backend (/tools) é a lista
    # completa; o editor pré-seleciona estas e mostra as restantes como toggles.
    enabled: List[str] = Field(default_factory=lambda: list(_DEFAULT_TOOLS_ENABLED))
    # config por tool — estrutura aberta (cada tool define o seu)
    config: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


class ProfileRetrieval(BaseModel):
    """
    Knobs de RAG/retrieval por cliente. Antes só env vars (KB_*, RAG_*) — logo
    invisíveis e não-afináveis por cliente no Console. Agora no perfil.

    Regra: qualidade acima de custo. Sem limites superiores — na dúvida, subir.
    """
    model_config = ConfigDict(extra="allow")

    top_k: int = Field(default=20, ge=1)                       # KB_TOP_K
    min_score: float = Field(default=0.15, ge=0.0, le=1.0)     # KB_MIN_SCORE
    enable_rerank: bool = True                                  # KB_ENABLE_RERANK
    chars_per_chunk: int = Field(default=5000, ge=0)           # KB_CHARS_PER_CHUNK
    rerank_chars_per_source: int = Field(default=3000, ge=0)   # RAG_PHASE1_CHARS_PER_SOURCE
    topicality_gate: bool = True                               # KB_TOPICALITY_GATE
    force_diversity: bool = False                              # KB_FORCE_DIVERSITY
    fuzzy_correction: bool = False                             # KB_FUZZY_CORRECTION_ENABLED


class ProfileRuntime(BaseModel):
    """Runtime do agente. Antes env vars (AGENT_*, SUMMARY_*)."""
    model_config = ConfigDict(extra="allow")

    max_turns: int = Field(default=5, ge=1)                    # AGENT_MAX_TURNS
    model_timeout_s: int = Field(default=60, ge=1)            # AGENT_MODEL_TIMEOUT
    max_history_items: int = Field(default=20, ge=0)          # AGENT_MAX_HISTORY_ITEMS
    summary_every_n_turns: int = Field(default=10, ge=0)      # SUMMARY_EVERY_N_TURNS


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


class ProfileMCP(BaseModel):
    """Secção 'mcp' — lista de servers + cache de discovery. OFF por default."""
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    discovery_cache_ttl_seconds: int = Field(default=3600, ge=60, le=86400)
    servers: List[ProfileMCPServer] = Field(default_factory=list)


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
    enableInlineCitations: bool = True
    enablePipelineTrace: bool = True   # on: transparência + resumo de explainability
    showHistory: bool = True
    enableStarterPrompts: bool = True
    enableDarkMode: bool = False
    # REMOVIDOS (campos mortos, nenhum componente os lia):
    #   showQuestionsMenu, enableFollowupSuggestions
    # REMOVIDO enableFeedback: feedback é sempre-on no frontend, sem flag.
    # REMOVIDO enableHybridSearch: hybrid search (vetorial+keyword) é sempre-on
    #   no retrieval do backend, sem flag — desligá-lo só piora a qualidade.


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


class ProfileFrontend(BaseModel):
    """
    Sub-bloco PÚBLICO do profile — consumido pelo endpoint /client-config.
    O backend ignora este nó; só o Angular do utilizador final o lê.
    """
    model_config = ConfigDict(extra="allow")

    branding: ProfileFrontendBranding = Field(default_factory=ProfileFrontendBranding)
    language: ProfileFrontendLanguage = Field(default_factory=ProfileFrontendLanguage)
    features: ProfileFrontendFeatures = Field(default_factory=ProfileFrontendFeatures)
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
    # Género gramatical do assistente (afeta artigos nas labels fixas do FE).
    assistantGender: Literal["feminine", "masculine", "neutral"] = "masculine"


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
    runtime: ProfileRuntime = Field(default_factory=ProfileRuntime)
    memory: ProfileMemory = Field(default_factory=ProfileMemory)
    mcp: ProfileMCP = Field(default_factory=ProfileMCP)
    audio: ProfileAudio = Field(default_factory=ProfileAudio)
    voices: ProfileVoices = Field(default_factory=ProfileVoices)
    query_cache: ProfileQueryCache = Field(default_factory=ProfileQueryCache)
    language: ProfileLanguage = Field(default_factory=ProfileLanguage)

    # Bloco frontend — consumido pelo /client-config.
    frontend: ProfileFrontend = Field(default_factory=ProfileFrontend)

    def to_blob_dict(self) -> dict:
        """Serialização para escrita no Blob. mode='json' garante JSON-safe."""
        return self.model_dump(mode="json")
