"""
exposure.py — QUEM pode ver e editar cada campo do perfil.

Terceira camada do contrato, ao lado da forma (`client_profile_schema.py`) e
das dependências (`json_schema_extra`: requires_tool / requires_field). Aqui
declara-se, por caminho, se o campo é interno à Genesis, se o cliente o vê, ou
se o cliente o edita.

PORQUÊ AQUI E NÃO NO CONSUMIDOR
────────────────────────────────
Esta classificação estava a ser escrita à mão no backoffice do cliente, como
uma allowlist de ÁREAS de topo. Uma allowlist de áreas tem um modo de falha
assimétrico: uma área nova nasce negada (seguro), mas um CAMPO novo dentro de
uma área já permitida nasce EXPOSTO — sem que ninguém decida nada. Não é
hipotético: entre a v0.1.41 (o pin do backoffice) e a v0.1.49 entraram 29
campos, dos quais 24 cairiam em áreas já permitidas na próxima subida de pin,
incluindo os cinco de `frontend.csp`.

O default deste módulo é o inverso: caminho sem entrada = `internal`. Expor
passa a ser um acto deliberado, e o teste de cobertura recusa um campo novo
por classificar.

O QUE ISTO NÃO É
────────────────
Não é autorização. É a declaração de intenção do contrato, para os consumidores
a lerem em vez de a adivinharem. Cada consumidor mantém o seu próprio portão —
o backoffice do cliente continua a precisar do seu default-deny local, porque
uma montra não deve depender só do upstream para não expor um campo.

Também não valida valores: isso é do Pydantic, no ficheiro do lado.

NÍVEIS
──────
  internal      — só Genesis (Studio/engenharia). Nunca sai para o cliente.
  client_read   — o cliente vê, não altera. Factos que lhe dizem respeito mas
                  cuja decisão é nossa: escopo contratado, limites, guardrails,
                  classificação de risco.
  client_write  — o cliente vê e altera. O que é genuinamente dele: marca,
                  copy, vocabulário do seu domínio, contactos, e os dados que
                  no AI Act pertencem ao deployer.

DIALECTO DOS CAMINHOS
─────────────────────
Pontuado e SEM índices: uma lista de objectos é percorrida ao MESMO caminho da
lista (`retrieval.indexes.name`, nunca `retrieval.indexes.0.name`). É o
dialecto que o backoffice e o editor já usam ao renderizar. `normalise_path()`
tira segmentos numéricos e marcadores `[]` antes de procurar.

Um mapa aberto (`personality.tone_instructions`, `tools.config`, …) tem UMA
entrada, e tudo o que vive lá dentro herda-a — com excepções por caminho
exacto, que ganham sempre (ver `tools.config.*` no fim da tabela).
"""

from functools import lru_cache
from typing import Any, Dict, FrozenSet, List, Tuple

INTERNAL = "internal"
CLIENT_READ = "client_read"
CLIENT_WRITE = "client_write"

LEVELS: Tuple[str, ...] = (INTERNAL, CLIENT_READ, CLIENT_WRITE)

# Abreviaturas só para a tabela — mantêm-na legível como tabela.
_I, _R, _W = INTERNAL, CLIENT_READ, CLIENT_WRITE


EXPOSURE: Dict[str, str] = {

    # ──────────────────────────────────────────────────────────────────────
    # Identidade — tudo do cliente
    # ──────────────────────────────────────────────────────────────────────
    "identity.assistant_name": _W,
    "identity.assistant_role": _W,
    "identity.company_name": _W,
    "identity.default_language": _I,  # DEPRECADO: nenhum consumidor o le; a lingua vem de language.* e frontend.language.default
    "identity.logo_url": _W,
    "identity.register": _W,
    # Ligado a 1 Set 2026: o core resolve perfil > env TZ > Europe/Lisbon em
    # core/agent/clock.py, e o bloco temporal do prompt e o fast-path do
    # "que horas sao?" leem de la. Passou a client_write no mesmo commit.
    "identity.timezone": _W,

    # ──────────────────────────────────────────────────────────────────────
    # Personalidade — o cliente escolhe o tom, nao reescreve as instrucoes
    # ──────────────────────────────────────────────────────────────────────
    "personality.response_length": _W,
    "personality.tone": _W,
    "personality.tone_instructions": _I,  # prompt nosso por tom; o cliente escolhe `tone`, nao reescreve o texto

    # ──────────────────────────────────────────────────────────────────────
    # Dominio
    # ──────────────────────────────────────────────────────────────────────
    "domain.description": _W,

    # ──────────────────────────────────────────────────────────────────────
    # Instrucoes personalizadas
    # ──────────────────────────────────────────────────────────────────────
    "custom_instructions": _W,

    # ──────────────────────────────────────────────────────────────────────
    # Disclaimers do system prompt
    # ──────────────────────────────────────────────────────────────────────
    "system_prompt_disclaimers": _W,

    # ──────────────────────────────────────────────────────────────────────
    # Resposta — preferencias de apresentacao
    # ──────────────────────────────────────────────────────────────────────
    "response.explainability_summary": _W,
    "response.extractive_mode": _W,
    "response.followup_count": _W,
    "response.show_images": _W,
    "response.show_sources": _W,
    "response.suggest_followups": _W,

    # ──────────────────────────────────────────────────────────────────────
    # Guardrails — o cliente ve, a Genesis decide
    # ──────────────────────────────────────────────────────────────────────
    "guardrails.allow_general_knowledge": _R,  # desliga o grounded-only; e a origem de metade do trabalho anti-invencao
    "guardrails.blocked_words": _W,
    "guardrails.citation_support_warning": _R,  # decide se o aviso de alucinacao chega ao utilizador final
    "guardrails.competitor_brands": _W,

    # ──────────────────────────────────────────────────────────────────────
    # Identificacao de produto — vocabulario do cliente
    # ──────────────────────────────────────────────────────────────────────
    "product_identification.enabled": _W,
    "product_identification.internal_prefixes": _W,
    "product_identification.patterns": _W,
    "product_identification.stopwords": _W,
    "product_identification.strict_mode": _W,

    # ──────────────────────────────────────────────────────────────────────
    # Brand safety
    # ──────────────────────────────────────────────────────────────────────
    "brand_safety.blocked_brands": _W,
    "brand_safety.level": _W,
    "brand_safety.redirect_to": _W,

    # ──────────────────────────────────────────────────────────────────────
    # Linguas
    # ──────────────────────────────────────────────────────────────────────
    "language.aliases": _I,  # tabela de normalizacao interna
    "language.allowed": _W,
    "language.fallback": _R,  # NOME CANONICO que vai como instrucao ao modelo, nao um codigo ISO: quem o escreve somos nos
    "language.strategy": _W,

    # ──────────────────────────────────────────────────────────────────────
    # Frontend — a montra propriamente dita
    # A maior area (169 folhas) e o coracao da montra: marca, cores, copy,
    #    widget. Tres blocos ficam fechados — csp, auth e llmModels.
    # ──────────────────────────────────────────────────────────────────────
    "frontend.aiDisclosure.enabled": _R,  # obrigacao AI Act Art. 50 — nao pode ser desligavel pelo cliente
    "frontend.aiDisclosure.text": _W,
    "frontend.aiDisclosure.textI18n": _W,
    "frontend.assistantGender": _W,
    "frontend.auth.apiScopes": _I,
    "frontend.auth.authority": _I,
    "frontend.auth.clientId": _I,
    "frontend.auth.loginType": _I,
    "frontend.auth.mode": _I,
    "frontend.auth.provider": _I,
    "frontend.auth.providers.audience": _I,
    "frontend.auth.providers.id": _I,
    "frontend.auth.providers.issuer": _I,
    "frontend.auth.providers.jwks_uri": _I,
    "frontend.auth.providers.label": _I,
    "frontend.auth.providers.primary": _I,
    "frontend.auth.providers.required_scope": _I,
    "frontend.auth.providers.tenant_id": _I,
    "frontend.auth.providers.type": _I,
    "frontend.auth.scope": _I,
    "frontend.auth.tenantId": _I,
    "frontend.auth.tenantMode": _I,
    "frontend.auth.widget_identity.algo": _I,
    "frontend.auth.widget_identity.enabled": _I,
    "frontend.auth.widget_identity.max_age_s": _I,
    "frontend.auth.widget_identity.secret_ref": _I,
    "frontend.branding.botAvatarShape": _W,
    "frontend.branding.botAvatarSize": _W,
    "frontend.branding.disclaimer": _W,
    "frontend.branding.disclaimerI18n": _W,
    "frontend.branding.favicon": _W,
    "frontend.branding.headerLogoHeight": _W,
    "frontend.branding.headerText": _W,
    "frontend.branding.headerTextColor": _W,
    "frontend.branding.headerTextSize": _W,
    "frontend.branding.logoDark": _W,
    "frontend.branding.logoLight": _W,
    "frontend.branding.logoRail": _W,
    "frontend.branding.primaryColor": _W,
    "frontend.branding.primaryTextColor": _W,
    "frontend.branding.productName": _W,
    "frontend.branding.subtitle": _W,
    "frontend.branding.theme.bgSidebar": _W,
    "frontend.branding.theme.bgSidebarSubtle": _W,
    "frontend.branding.theme.dark.bgPage": _W,
    "frontend.branding.theme.dark.bgSidebar": _W,
    "frontend.branding.theme.dark.bgSidebarCollapsed": _W,
    "frontend.branding.theme.dark.bgSidebarSubtle": _W,
    "frontend.branding.theme.dark.bgSubtle": _W,
    "frontend.branding.theme.dark.bgSurface": _W,
    "frontend.branding.theme.dark.codeBg": _W,
    "frontend.branding.theme.dark.codeText": _W,
    "frontend.branding.theme.dark.headerBg": _W,
    "frontend.branding.theme.dark.iconHeaderColor": _W,
    "frontend.branding.theme.dark.iconInputColor": _W,
    "frontend.branding.theme.dark.iconSidebarColor": _W,
    "frontend.branding.theme.dark.inputBg": _W,
    "frontend.branding.theme.dark.sourceCardBg": _W,
    "frontend.branding.theme.dark.sourcesBubbleBg": _W,
    "frontend.branding.theme.dark.textPrimary": _W,
    "frontend.branding.theme.dark.textSecondary": _W,
    "frontend.branding.theme.dark.textSidebarPrimary": _W,
    "frontend.branding.theme.dark.textSidebarSecondary": _W,
    "frontend.branding.theme.dark.textSidebarTertiary": _W,
    "frontend.branding.theme.dark.textTertiary": _W,
    "frontend.branding.theme.dark.traceBubbleBg": _W,
    "frontend.branding.theme.dark.userBubble": _W,
    "frontend.branding.theme.dark.welcomeCardBg": _W,
    "frontend.branding.theme.light.bgPage": _W,
    "frontend.branding.theme.light.bgSidebar": _W,
    "frontend.branding.theme.light.bgSidebarCollapsed": _W,
    "frontend.branding.theme.light.bgSidebarSubtle": _W,
    "frontend.branding.theme.light.bgSubtle": _W,
    "frontend.branding.theme.light.bgSurface": _W,
    "frontend.branding.theme.light.codeBg": _W,
    "frontend.branding.theme.light.codeText": _W,
    "frontend.branding.theme.light.headerBg": _W,
    "frontend.branding.theme.light.iconHeaderColor": _W,
    "frontend.branding.theme.light.iconInputColor": _W,
    "frontend.branding.theme.light.iconSidebarColor": _W,
    "frontend.branding.theme.light.inputBg": _W,
    "frontend.branding.theme.light.sourceCardBg": _W,
    "frontend.branding.theme.light.sourcesBubbleBg": _W,
    "frontend.branding.theme.light.textPrimary": _W,
    "frontend.branding.theme.light.textSecondary": _W,
    "frontend.branding.theme.light.textSidebarPrimary": _W,
    "frontend.branding.theme.light.textSidebarSecondary": _W,
    "frontend.branding.theme.light.textSidebarTertiary": _W,
    "frontend.branding.theme.light.textTertiary": _W,
    "frontend.branding.theme.light.traceBubbleBg": _W,
    "frontend.branding.theme.light.userBubble": _W,
    "frontend.branding.theme.light.welcomeCardBg": _W,
    "frontend.branding.theme.textSidebarPrimary": _W,
    "frontend.branding.theme.textSidebarSecondary": _W,
    "frontend.branding.theme.textSidebarTertiary": _W,
    # ⚠ frontend.csp.* — controlo de seguranca. Acrescentar uma origem a
    #    script-src da pagina de chat do proprio cliente e um vector de XSS
    #    persistente. Entrou na v0.1.43; o gaibo esta pinado na v0.1.41, por isso
    #    ainda nao o ve — no dia em que subir o pin, cai dentro de `frontend`
    #    (area ja permitida) e fica editavel sem decisao nenhuma.
    "frontend.csp.extraConnectSrc": _I,
    "frontend.csp.extraFrameSrc": _I,
    "frontend.csp.extraImgSrc": _I,
    "frontend.csp.extraScriptSrc": _I,
    "frontend.csp.extraStyleSrc": _I,
    "frontend.features.enableDarkMode": _W,
    "frontend.features.enableDocumentUpload": _R,
    "frontend.features.enableInlineCitations": _W,
    "frontend.features.enableLlmSelector": _I,  # expoe a escolha de modelo ao utilizador final
    "frontend.features.enablePdfExport": _W,
    "frontend.features.enablePipelineTrace": _R,
    "frontend.features.enableShare": _W,
    "frontend.features.enableSourcePreview": _W,
    "frontend.features.enableStarterPrompts": _W,
    "frontend.features.enableTTS": _R,
    "frontend.features.enableVoiceLoop": _R,
    "frontend.features.persistOriginals": _R,
    "frontend.features.renderSourcesSection": _W,
    "frontend.features.reviewQueue": _R,
    "frontend.features.reviewQueueHome": _R,
    "frontend.features.reviewQueueOnly": _R,
    "frontend.features.showHistory": _W,
    "frontend.features.sourceClickAction": _W,
    "frontend.features.taskApi": _R,
    "frontend.features.toolWorkspace": _R,
    "frontend.features.turnOnVoiceRecorder": _R,
    "frontend.features.voiceMode": _R,
    "frontend.insightsPanel.openOnLoad": _W,
    "frontend.insightsPanel.panelTypes": _W,
    "frontend.insightsPanel.providerBadge.icon": _W,
    "frontend.insightsPanel.providerBadge.label": _W,
    "frontend.insightsPanel.quickInsights.icon": _W,
    "frontend.insightsPanel.quickInsights.id": _W,
    "frontend.insightsPanel.quickInsights.label": _W,
    "frontend.insightsPanel.quickInsights.prompt": _W,
    "frontend.insightsPanel.quickInsights.questions.label": _W,
    "frontend.insightsPanel.quickInsights.questions.prompt": _W,
    "frontend.insightsPanel.title": _W,
    "frontend.language.default": _W,
    "frontend.language.enabled": _W,
    "frontend.legalNotice": _W,
    "frontend.llmModels": _I,  # ids provider:model:mode — escolha de modelo e custo nosso
    "frontend.privacyPolicyI18n": _W,
    "frontend.privacyPolicyUrl": _W,
    "frontend.shareDefaultExpiryDays": _W,
    "frontend.shareExpiryOptionsDays": _W,
    "frontend.starterPrompts.iconName": _W,
    "frontend.starterPrompts.prompt": _W,
    "frontend.starterPrompts.title": _W,
    "frontend.sttPhraseList": _W,
    "frontend.sttSilenceTimeoutMs": _I,  # afinacao do reconhecimento de fala
    "frontend.ttsPhoneticMap": _W,
    "frontend.ttsVoiceMap": _W,
    "frontend.welcomeMessage": _W,
    "frontend.welcomeMessageSize": _W,
    "frontend.welcomeMessageSizeMobile": _W,
    "frontend.welcomeSubtitle": _W,
    "frontend.widget.allowed_origins": _W,
    "frontend.widget.bubble_color": _W,
    "frontend.widget.bubble_icon_fit": _W,
    "frontend.widget.bubble_icon_scale_pct": _W,
    "frontend.widget.bubble_icon_url": _W,
    "frontend.widget.bubble_label": _W,
    "frontend.widget.bubble_size_px": _W,
    "frontend.widget.enabled": _W,
    "frontend.widget.greeting": _W,
    "frontend.widget.greeting_delay_s": _W,
    "frontend.widget.mobile_mode": _W,
    "frontend.widget.mode": _W,
    "frontend.widget.offset_x_px": _W,
    "frontend.widget.offset_y_px": _W,
    "frontend.widget.panel_height_px": _W,
    "frontend.widget.panel_width_px": _W,
    "frontend.widget.position": _W,

    # ──────────────────────────────────────────────────────────────────────
    # Conformidade (AI Act) — dividido por QUEM e dono do facto
    # ──────────────────────────────────────────────────────────────────────
    "compliance.annex_iv_doc_url": _R,
    "compliance.annex_iv_generated_at": _R,
    "compliance.classification.annex_iii_answers": _R,
    "compliance.classification.classified_at": _R,
    "compliance.classification.classified_by": _R,
    "compliance.classification.justification": _R,
    "compliance.classification.legal_review_date": _W,
    "compliance.classification.legal_reviewer": _W,
    "compliance.classification.next_review_due": _W,
    "compliance.classification.reviewed_by_legal": _W,
    "compliance.classification.risk_level": _R,
    "compliance.deployer_content_responsibility": _R,
    "compliance.high_risk.enabled": _R,
    "compliance.high_risk.human_oversight_contact": _W,
    "compliance.high_risk.log_retention_days": _R,
    # retenção de dados pessoais: decisão do deployer (igual a voice.transcription.retention_days)
    "compliance.retention.conversations_anonymous_days": _W,
    "compliance.retention.conversations_authenticated_days": _W,
    "compliance.high_risk.oversight_procedure_url": _W,
    "compliance.high_risk.serious_incident_contact": _W,
    "compliance.sector": _W,
    "compliance.use_case": _W,

    # ──────────────────────────────────────────────────────────────────────
    # Canal de voz
    # ──────────────────────────────────────────────────────────────────────
    "voice.aiDisclosure": _R,  # obrigacao AI Act Art. 50 no canal de voz
    "voice.category_hints": _W,
    "voice.deployment": _I,  # deployment Azure
    "voice.enabled": _R,
    "voice.greeting": _W,
    "voice.instructions": _I,  # prompt do canal de voz, derivado das capacidades
    "voice.kb_top_n": _I,
    "voice.language": _W,
    "voice.queue": _W,
    "voice.transcription.enabled": _R,
    "voice.transcription.model": _I,
    "voice.transcription.retention_days": _W,  # retencao de dados pessoais: decisao do deployer
    "voice.transfer_number": _W,
    "voice.voice": _W,
    "voice.web.enabled": _R,

    # ──────────────────────────────────────────────────────────────────────
    # Vozes TTS
    # ──────────────────────────────────────────────────────────────────────
    "voices.by_locale": _W,
    "voices.max_tts_chars": _I,
    "voices.phonetic_map": _W,

    # ──────────────────────────────────────────────────────────────────────
    # Audio / STT
    # ──────────────────────────────────────────────────────────────────────
    "audio.disfluency_removal": _I,
    "audio.glossary": _W,
    "audio.max_duration_min": _I,
    "audio.max_speakers": _I,
    "audio.phrase_bias": _I,
    "audio.phrase_list": _W,
    "audio.speech_locale": _W,

    # ──────────────────────────────────────────────────────────────────────
    # Ingestao
    # ──────────────────────────────────────────────────────────────────────
    "ingest.alerts.aging_hours": _W,
    "ingest.alerts.email": _W,
    "ingest.alerts.email_interval_hours": _W,
    "ingest.alerts.enabled": _W,
    "ingest.sources": _I,  # wiring de blob/containers

    # ──────────────────────────────────────────────────────────────────────
    # Tools — escopo comercial, nao preferencia
    # ──────────────────────────────────────────────────────────────────────
    "tools.config": _I,  # mapa aberto: leva wiring do Foundry e a politica de captura (PII, base legal)
    "tools.enabled": _R,  # escopo contratado, nao preferencia de UI

    # ──────────────────────────────────────────────────────────────────────
    # Limites de tools
    # ──────────────────────────────────────────────────────────────────────
    "tool_limits.max_attached_doc_chars": _R,
    "tool_limits.max_user_prompt_chars": _R,

    # ──────────────────────────────────────────────────────────────────────
    # Memoria de utilizador
    # ──────────────────────────────────────────────────────────────────────
    "memory.enabled": _R,
    "memory.max_facts": _I,
    "memory.min_confidence": _I,
    "memory.extraction_mode": _R,
    "memory.seed_from_identity": _R,
    "memory.exclude_special_categories": _R,

    # ──────────────────────────────────────────────────────────────────────
    # Multi-perfil
    # ──────────────────────────────────────────────────────────────────────
    "multiProfile.disabledSlugs": _R,
    "multiProfile.enabled": _R,
    "multiProfile.invalidSlugBehavior": _I,  # comportamento de fallback do router
    "multiProfile.slugs": _R,

    # ──────────────────────────────────────────────────────────────────────
    # Acesso convidado — limites que a Genesis define
    # ──────────────────────────────────────────────────────────────────────
    "guestAccess.dailyBudgetEur": _I,  # teto de gasto nosso
    "guestAccess.enabled": _R,
    "guestAccess.rateLimits.perDay": _R,
    "guestAccess.rateLimits.perHour": _R,
    "guestAccess.rateLimits.perMinute": _R,
    "guestAccess.realtimeSessionEstEur": _I,  # estimativa de custo nossa
    "guestAccess.uploads.enabled": _R,
    "guestAccess.uploads.maxFiles": _R,
    "guestAccess.uploads.maxMb": _R,
    "guestAccess.uploads.pdfOnly": _R,

    # ──────────────────────────────────────────────────────────────────────
    # Orquestracao
    # ──────────────────────────────────────────────────────────────────────
    "orchestration.agent_planner": _I,
    "orchestration.allow_web": _R,  # o cliente tem de saber se o bot pesquisa na web; ligar/desligar e nosso
    "orchestration.parallel_tools": _I,
    "orchestration.retrieval_strategy": _I,

    # ──────────────────────────────────────────────────────────────────────
    # RAG — motor interno, INTEIRO fechado
    # ⚠ AREA INTEIRA INTERNA. Sao 38 knobs do motor de RAG. Quatro deles
    #    (min_score, refuse_pregen_min_score, weak_grounding_ceiling,
    #    faithfulness_overlap_skip) sao os pisos anti-invencao: baixa-los desliga,
    #    em silencio, a protecao que impede o bot de inventar. Nenhum cliente tem
    #    como raciocinar sobre isto, e o efeito de errar nao e visivel na UI.
    # ──────────────────────────────────────────────────────────────────────
    "retrieval.chars_per_chunk": _I,
    "retrieval.context_include_source_fields": _I,
    "retrieval.context_top_k": _I,
    "retrieval.enable_rerank": _I,
    "retrieval.faithfulness_overlap_skip": _I,
    "retrieval.force_diversity": _I,
    "retrieval.fuzzy_correction": _I,
    "retrieval.gpt_rerank_broad": _I,
    "retrieval.indexes.name": _I,
    "retrieval.indexes.rerank_mode": _I,
    "retrieval.indexes.weight": _I,
    "retrieval.latest_version.date_field": _I,
    "retrieval.latest_version.enabled": _I,
    "retrieval.latest_version.family_field": _I,
    "retrieval.latest_version.intent_patterns": _I,
    "retrieval.latest_version.strategy": _I,
    "retrieval.latest_version.version_field": _I,
    "retrieval.latest_version.year_segment_regex": _I,
    "retrieval.min_score": _I,
    "retrieval.neighbor_expansion.enabled": _I,
    "retrieval.neighbor_expansion.max_added": _I,
    "retrieval.neighbor_expansion.top_anchors": _I,
    "retrieval.neighbor_expansion.window": _I,
    "retrieval.refuse_pregen_min_score": _I,
    "retrieval.rerank_chars_per_source": _I,
    "retrieval.rerank_top_k": _I,
    "retrieval.search_index_names": _I,
    "retrieval.source_priority.enabled": _I,
    "retrieval.source_priority.internal_markers": _I,
    "retrieval.source_priority.label_overrides": _I,
    "retrieval.source_priority.legal_allowlist": _I,
    "retrieval.source_priority.reranker_floor": _I,
    "retrieval.source_priority.strategy": _I,
    "retrieval.source_priority.tier_field": _I,
    "retrieval.source_url_sas_ttl_days": _I,
    "retrieval.top_k": _I,
    "retrieval.topicality_gate": _I,
    "retrieval.weak_grounding_ceiling": _I,

    # ──────────────────────────────────────────────────────────────────────
    # Runtime — modelos e timeouts
    # Modelos e timeouts. Mudar aqui muda custo e latencia da frota.
    # ──────────────────────────────────────────────────────────────────────
    "runtime.agent_mode": _I,
    "runtime.agent_model": _I,
    "runtime.internal_model": _I,
    "runtime.max_history_items": _I,
    "runtime.max_turns": _I,
    "runtime.model_timeout_s": _I,
    "runtime.summary_every_n_turns": _I,

    # ──────────────────────────────────────────────────────────────────────
    # MCP — integracoes e credenciais
    # ⚠ AREA INTEIRA INTERNA. Contem slots de credencial (auth.token,
    #    auth.client_secret) e o flag `trusted`, que decide se uma tool externa
    #    corre sem confirmacao.
    # ──────────────────────────────────────────────────────────────────────
    "mcp.confirm_actions": _I,
    "mcp.disabledServers": _I,
    "mcp.discovery_cache_ttl_seconds": _I,
    "mcp.enabled": _I,
    "mcp.servers.auth.audience": _I,
    "mcp.servers.auth.authorize_url": _I,
    "mcp.servers.auth.client_id": _I,
    "mcp.servers.auth.client_id_env": _I,
    "mcp.servers.auth.client_secret": _I,
    "mcp.servers.auth.client_secret_env": _I,
    "mcp.servers.auth.issuer": _I,
    "mcp.servers.auth.per_user": _I,
    "mcp.servers.auth.revocation_url": _I,
    "mcp.servers.auth.scopes": _I,
    "mcp.servers.auth.token": _I,
    "mcp.servers.auth.token_env": _I,
    "mcp.servers.auth.token_url": _I,
    "mcp.servers.auth.type": _I,
    "mcp.servers.enabled": _I,
    "mcp.servers.erp": _I,
    "mcp.servers.name": _I,
    "mcp.servers.timeout_seconds": _I,
    "mcp.servers.tool_prefix": _I,
    "mcp.servers.trusted": _I,
    "mcp.servers.url": _I,

    # ──────────────────────────────────────────────────────────────────────
    # Contactos / CRM
    # Wiring de identidade/CRM.
    # ──────────────────────────────────────────────────────────────────────
    "contacts.attribute_paths": _I,
    "contacts.display_name_path": _I,
    "contacts.enabled": _I,
    "contacts.identity_fields": _I,

    # ──────────────────────────────────────────────────────────────────────
    # Cache de queries
    # Cache interna.
    # ──────────────────────────────────────────────────────────────────────
    "query_cache.enabled": _I,
    "query_cache.index_version": _I,
    "query_cache.ttl_seconds": _I,

    # ──────────────────────────────────────────────────────────────────────
    # Precos — estrutura de custo da Genesis
    # Estrutura de custo da Genesis. Nunca sai para o cliente.
    # ──────────────────────────────────────────────────────────────────────
    "pricing.currency": _I,
    "pricing.image_models": _I,
    "pricing.models": _I,
    "pricing.usd_to_eur": _I,

    # ──────────────────────────────────────────────────────────────────────
    # Filas de revisao
    # ──────────────────────────────────────────────────────────────────────
    "reviewQueues": _I,  # nome de fila invalido cria filas fantasma em Cosmos
    # ──────────────────────────────────────────────────────────────────────
    # Excepções por caminho exacto dentro de mapas abertos
    #
    # `tools.config` é interno em bloco, mas o TEXTO de prompt de duas tools é
    # do cliente. Caminhos exactos, nunca prefixos: os modelos de tool-config
    # são `extra="allow"`, e um prefixo admitiria chaves inventadas.
    # Deliberadamente ausentes: `tools.config.record_contact_details.*` —
    # `notify_emails` é um canal de saída de PII e `legal_basis` é uma
    # atestação RGPD com proveniência carimbada pelo Studio.
    # ──────────────────────────────────────────────────────────────────────
    "tools.config.extract_legal_terms.prompt_preset": _W,
    "tools.config.extract_legal_terms.prompt_custom": _W,
    "tools.config.generate_boq.prompt_preset": _W,
    "tools.config.generate_boq.prompt_custom": _W,
    "tools.config.generate_boq.rates": _W,
    "tools.config.generate_boq.rates.match": _W,
    "tools.config.generate_boq.rates.unit": _W,
    "tools.config.generate_boq.rates.price": _W,
    "tools.config.generate_boq.rates.label": _W,
}


# ─────────────────────────────────────────────────────────────────────────────
# API
# ─────────────────────────────────────────────────────────────────────────────

def normalise_path(path: str) -> str:
    """Caminho no dialecto da tabela: sem índices numéricos e sem `[]`."""
    parts = [p for p in path.replace("[]", "").split(".") if p and not p.isdigit()]
    return ".".join(parts)


def exposure_of(path: str) -> str:
    """Nível de um caminho. Ausente = `internal` (fail-safe).

    Procura o caminho exacto e, não o encontrando, sobe pelos antepassados —
    é assim que o conteúdo de um mapa aberto herda o nível do mapa.
    """
    norm = normalise_path(path)
    if not norm:
        return INTERNAL
    if norm in EXPOSURE:
        return EXPOSURE[norm]
    parts = norm.split(".")
    for i in range(len(parts) - 1, 0, -1):
        ancestor = ".".join(parts[:i])
        if ancestor in EXPOSURE:
            return EXPOSURE[ancestor]
    return INTERNAL


def is_client_visible(path: str) -> bool:
    return exposure_of(path) in (CLIENT_READ, CLIENT_WRITE)


def is_client_writable(path: str) -> bool:
    return exposure_of(path) == CLIENT_WRITE


@lru_cache(maxsize=4)
def paths_at(level: str) -> FrozenSet[str]:
    """Caminhos declarados com este nível (não expande mapas abertos)."""
    if level not in LEVELS:
        raise ValueError(f"nível desconhecido: {level!r}")
    return frozenset(p for p, lvl in EXPOSURE.items() if lvl == level)


# ─────────────────────────────────────────────────────────────────────────────
# Enumeração de folhas — fonte única do dialecto
#
# Havia três travessias deste JSON Schema escritas à mão (guard e inventário do
# Studio, gerador de metadata do backoffice), cada uma com o seu dialecto. Esta
# é a do contrato; quem precisar de outro dialecto deriva-o daqui.
# ─────────────────────────────────────────────────────────────────────────────

def _resolve(node: Any, defs: Dict[str, Any]) -> Dict[str, Any]:
    seen = 0
    while isinstance(node, dict) and "$ref" in node and seen < 32:
        base = dict(defs.get(node["$ref"].split("/")[-1], {}))
        base.update({k: v for k, v in node.items() if k != "$ref"})
        node = base
        seen += 1
    return node if isinstance(node, dict) else {}


@lru_cache(maxsize=1)
def _walk_schema() -> Tuple[Tuple[str, ...], Tuple[str, ...], Dict[str, Tuple[str, ...]],
                            Dict[str, Dict[str, Any]]]:
    from genesis_profile_schema.client_profile_schema import ClientProfileSchema

    js = ClientProfileSchema.model_json_schema()
    defs = js.get("$defs", {})
    leaves: List[str] = []
    open_maps: List[str] = []
    enums: Dict[str, Tuple[str, ...]] = {}
    shapes: Dict[str, Dict[str, Any]] = {}

    def walk(node: Any, path: List[str]) -> None:
        node = _resolve(node, defs)
        props = node.get("properties")
        if props:
            for key, sub in props.items():
                walk(sub, path + [key])
            return
        alts = [a for a in node.get("anyOf", []) + node.get("oneOf", [])
                if _resolve(a, defs).get("type") != "null"]
        nested = [a for a in alts if "properties" in _resolve(a, defs)]
        if nested:
            for alt in nested:
                walk(alt, path)
            return
        shape = _resolve(alts[0], defs) if alts else node
        kind = shape.get("type", "object")
        if kind == "array":
            item = _resolve(shape.get("items", {}), defs)
            if "properties" in item:
                for key, sub in item["properties"].items():
                    walk(sub, path + [key])
                return
        dotted = ".".join(path)
        if not dotted:
            return
        leaves.append(dotted)
        if kind == "object":
            open_maps.append(dotted)
        members = shape.get("enum")
        if isinstance(members, list) and members and dotted not in enums:
            enums[dotted] = tuple(str(m) for m in members)
        item_shape = _resolve(shape.get("items", {}), defs) if kind == "array" else {}
        shapes.setdefault(dotted, {
            "type": kind,
            # Tipo de CADA entrada, quando o campo é uma lista: sem isto um
            # consumidor não distingue lista de textos de lista de números.
            "items_type": item_shape.get("type") if item_shape else None,
            "pattern": shape.get("pattern") or item_shape.get("pattern"),
            "enum": enums.get(dotted),
        })

    walk(js, [])
    return tuple(dict.fromkeys(leaves)), tuple(dict.fromkeys(open_maps)), enums, shapes


def leaf_paths() -> Tuple[str, ...]:
    """Todas as folhas do schema instalado, no dialecto sem índices."""
    return _walk_schema()[0]


def open_map_paths() -> Tuple[str, ...]:
    """As folhas que são mapas abertos (conteúdo livre por contrato)."""
    return _walk_schema()[1]


def leaf_shapes() -> Dict[str, Dict[str, Any]]:
    """`{caminho: {type, pattern, enum}}` da mesma travessia única.

    É o que permite a um consumidor derivar o controlo certo (interruptor,
    número, selector, selector de cor) sem manter listas de nomes de campos à
    mão — ver `presentation.py`.
    """
    return {k: dict(v) for k, v in _walk_schema()[3].items()}


def enum_members() -> Dict[str, Tuple[str, ...]]:
    """Membros de cada lista fechada, por ordem de declaração.

    A ordem é a do `Literal` no schema, não alfabética: quem desenhou o campo
    pôs as opções por uma ordem, e a UI mostra-as assim.
    """
    return dict(_walk_schema()[2])


def unclassified_paths() -> Tuple[str, ...]:
    """Folhas do schema sem entrada na tabela — devem ser zero.

    O que este módulo promete não é que a tabela esteja certa (isso decide-se
    campo a campo), é que nenhum campo escapa à decisão.
    """
    return tuple(p for p in leaf_paths() if p not in EXPOSURE)


def orphan_entries() -> Tuple[str, ...]:
    """Entradas da tabela que já não correspondem a nada no schema.

    Uma entrada é legítima se for uma folha, ou se viver dentro de um mapa
    aberto (as excepções por caminho exacto de `tools.config`).
    """
    leaves = set(leaf_paths())
    maps = open_map_paths()
    return tuple(
        p for p in EXPOSURE
        if p not in leaves and not any(p.startswith(m + ".") for m in maps)
    )
