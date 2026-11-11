# CAPACIDADES — genesis-profile-schema

Inventário do que este pacote JÁ faz. Ler ANTES de mexer: existe para evitar
construir o que já está construído, e para que uma alteração ao contrato não
saia daqui sem as decisões que ela obriga a tomar.

Não substitui ler o código. Evita desenhar de raiz o que já lá está.

---

## O que este pacote é

A fonte de verdade única do perfil de cliente, partilhada por três consumidores
que não falam entre si:

| Consumidor | Como consome | Para quê |
|---|---|---|
| **genai-core** (data plane) | `model_validate` no save; `GET /admin/profile/schema` | validar o perfil que serve o bot |
| **Genesis Studio** (control plane) | `model_json_schema()` em `/api/profile-schema`, `profile_schema_guard.py`, `profile_schema_inventory.py` | editor de perfis, guard anti-campos-fantasma, inventário injectado nos prompts dos agentes |
| **gaibo** (backoffice do cliente) | gerador `profile/field_metadata.py` → `field-schema.ts` | a montra que o cliente vê |

O gaibo **não fala com o Studio** (decisão fechada). O pacote é o único canal
entre os três — o que não estiver aqui é adivinhado lá, ou escrito à mão duas
vezes.

---

## As sete camadas

Um campo do perfil obriga a sete decisões, e cada uma vive num sítio próprio.
Nenhuma delas está no modelo Pydantic por acidente: o modelo é o que o core usa
para CARREGAR o perfil, e tudo o que lá se acrescenta pode impedir um bot de
arrancar.

### 1. Forma — `client_profile_schema.py`

O modelo Pydantic. Tipos, defaults, `Literal`, limites (`ge`, `min_length`),
`extra="allow"` em todos os submodelos por retrocompatibilidade deliberada.

### 2. Dependências — `json_schema_extra` no próprio campo

`requires_tool` / `requires_field`. O editor lê-os para avisar e impedir
combinações incoerentes (ex.: uma flag que só faz sentido com uma tool ligada).
Há **dois sítios de autoria** e ambos contam: ao nível do campo
(`Field(json_schema_extra=...)`, que aterra no nó da propriedade) e ao nível do
modelo (`ConfigDict(json_schema_extra=...)`, que aterra no `$defs`). O
field-level ganha quando os dois existem.

### 3. Quem vê e quem edita — `exposure.py`

Tabela por caminho: `internal`, `client_read`, `client_write`. **Default é
`internal`** — um caminho sem entrada resolve para escondido.

Esta classificação já esteve escrita no repo do gaibo, como allowlist de ÁREAS.
Não voltar a fazê-lo: uma allowlist de áreas nega bem uma área nova, mas expõe
em silêncio um CAMPO novo dentro de uma área já permitida. Medido a 1 Set 2026:
entre a v0.1.41 e a v0.1.49 entraram 29 campos, 24 dos quais ficariam
client-editáveis na subida de pin sem decisão de ninguém — incluindo os cinco
de `frontend.csp`.

### 4. Como se chama — `ui_text/<locale>.json` + `ui_text.py`

`label`, `help`, `note`, `options`, indexados **pelo caminho do campo**. O
caminho já é a chave; não há chave de tradução a inventar. Duas línguas hoje
(`pt-PT`, `en-GB`), acrescentar uma terceira é acrescentar um ficheiro.

Duas vozes, de propósito:
- **`help`** — o que acontece se mexeres. Para quem usa o produto.
- **`note`** — envs, precedências, acoplamentos. Para nós.

**Tecto da `help` visível ao cliente (v0.1.86, 4 Out 2026):** `CLIENT_HELP_MAX_CHARS = 240`
nos campos com exposure ≠ `internal` (o popover do GAIBO), com teste a chumbar. Passou? Condensar —
o que o cliente precisa de ler (RGPD, DPA, custo, o que não se guarda) fica na ajuda; o detalhe de
operador vai para a `note`. Não mover para a `note` o que o cliente tem de saber: ela não lhe é mostrada.

A distinção não é cosmética: as hints do Studio dizem coisas como "passa para
`tool.__init__`", que é o que um cliente não deve ler e o que nós precisamos de
ler.

**Projecção** — `annotated_json_schema(locale)` devolve o `model_json_schema()`
com `title` ← label, `description` ← help e `x-genesis-option-labels` ←
options. Serve quem só sabe ler JSON Schema, sem obrigar a escrever o texto
duas vezes. A `note` fica de fora de propósito. O esquema original nunca é
tocado (há teste). Um `$def` usado em dois caminhos com textos diferentes fica
por anotar e aparece em `annotation_conflicts()` — hoje zero, porque
`theme.light` e `theme.dark` partilham modelo E texto.

### 5. Que controlo desenhar — `presentation.py`

`control_for(path)` devolve `toggle`, `number`, `select`, `combobox`, `colour`,
`url`, `email`, `date`, `datetime`, `code`, `multiline` ou `text`;
`collection_of()` devolve `list`, `map` ou nada. São duas perguntas separadas
de propósito: uma lista de textos longos é `multiline` + `list`.

**`select` e `combobox` são duas escolhas diferentes.** `select` é lista
fechada — o schema (ou `languages.py`) enumera os valores e um valor fora deles
é erro. `combobox` é texto livre COM sugestões: o campo guarda o nome de algo
de um catálogo que vive fora do contrato (os `prompt_preset` das tools, cujo
catálogo é o `PRESETS` do genai-core, sem endpoint), e um valor que a lista não
conhece é legítimo — o core ignora-o, avisando. As sugestões, com nome, estão
em `ui_text` (`options_of`); é o controlo que diz se a lista fecha, não a
presença de `options`. Há teste a exigir que todo o `combobox` tenha sugestões
nas duas línguas e não seja `enum`, e outro — o que teria apanhado o issue #6
do gaibo sozinho — a exigir que qualquer campo com valores nomeados no
catálogo tenha um controlo de escolha (`select` ou `combobox`), nunca prosa.

**Quase tudo se deriva** do próprio schema — booleanos, números, listas
fechadas e os 57 campos com o `pattern` de cor. A derivação vê também **dentro
de `tools.config`**: o perfil declara-o mapa aberto, mas os blocos com modelo
tipado (`_KNOWN_TOOL_CONFIG_MODELS`) dizem sozinhos que `search_web.mode` é
lista fechada e `record_contact_details.retention_days` é número —
`exposure.tool_config_shapes()` traz essas formas, SEM as tornar folhas do
perfil (não exigem entrada em `EXPOSURE`). A tabela só carrega o que o contrato
não consegue dizer: qual das strings é prosa, qual é código, qual é um
endereço, qual é o nome de um preset, e as duas listas fechadas que o schema
tipa como `str` (`frontend.language.*`, espaço `UI_LANGS`). Há teste a chumbar
se a tabela crescer para mais de um quarto das folhas, e outro a chumbar se um
override estiver a repetir o que a derivação já dava. O padrão das cores é lido
do `client_profile_schema`, não copiado.

### 6. Valores perigosos — `field_checks.py`

Verificações de CONTEÚDO, deliberadamente fora do Pydantic. O modelo valida
forma; isto identifica valores que fazem mal, e devolve-os a quem chama em vez
de rejeitar.

A razão de estarem fora do modelo é a mesma sempre: o `client_profile_schema` é
usado pelo core para carregar o perfil que serve o bot. Um validador novo a
recusar um valor que hoje passa não protege ninguém — impede o perfil de
carregar. Quem escreve é que descarta; quem lê continua a ler tudo.

- `sanitise_csp_sources()` — allowlist de origens. `frontend.widget.allowed_origins`
  e `frontend.csp.extra*` são interpoladas **literalmente** numa directiva do CSP
  quando o Studio escreve o `staticwebapp.config.json`; um `;` fechava a
  directiva e abria outra, e o `allowed_origins` é editável pelo cliente.
  O `creator.py` do Studio passou a filtrar por aqui.
  Aceita também origens de app móvel híbrida (`capacitor://host`, `ionic://host`,
  sem caminho nem wildcard; v0.1.151) e `is_app_origin()` separa-as das web.
- `regex_risk()` — aviso para as regex de `product_identification.patterns`. O
  core já apanha `re.error`; o que falta lá é limite de TEMPO de execução, e
  isso resolve-se no core, não aqui.
- `looks_like_language_tag()` / `SUGGESTED_LOCALES` — forma BCP-47 e os locales
  com voz de fábrica. Valida a FORMA, nunca a pertença: `language.allowed` aceita
  `["*"]` e línguas de fora do mapa de propósito. E não serve para
  `language.fallback`, cujo valor é uma FRASE para o modelo
  (`"Portuguese (European Portuguese - pt-PT)"`), não um código. **Que valores
  existem** é a camada 7 (`languages.py`), não esta — e há um espaço que É
  fechado: o `UI_LANGS` do `frontend.language.*`.

- `transfer_target.py` (v0.1.106, 13 Out 2026) — o destino da transferência de
  chamada (SIP REFER). `voice.transfer_number` é do cliente e aceita só telefone
  (`phone_target`: E.164 ou extensão, separadores tirados, `sip:` recusado);
  destinos SIP vivem em `voice.transfer_sip_uri` (interno, `sip_target`:
  gramática de allowlist, sem headers) e ganham ao número quando válidos
  (`voice_transfer_target`). O core aplica isto ao servir a chamada; o Studio e
  o backoffice avisam antes de gravar. Um número válido pode ainda ser caro
  (premium/internacional): isso fecha-se no SBC, não aqui.
  Desde a v0.1.107, **vários destinos** (`voice.transfer_targets`, `client_write` — o backoffice ainda nega a área `voice` inteira:
  `id`, `label`, `description`, `number`, `default`) com o SIP de cada um num
  mapa interno à parte (`voice.transfer_sip_uris`, `{id: "sip:…"}`) —
  `voice_transfer_targets()` devolve os destinos efetivos e os problemas
  (`[(onde, código)]`, nunca corta em silêncio: até 10 destinos, nome 60 e
  descrição 200). Uma lista com pelo menos um destino válido ganha ao número
  único; sem nenhum, o número único é o destino implícito `geral`.

### 7. Que valores existem — `languages.py`

O espaço de valores de um campo, quando é enumerável mas não é um `Literal`.
Hoje só as línguas, e são o caso que justificou a camada: são **três** espaços
distintos e não se sobrepõem.

| campo | espaço | fechado? |
|---|---|---|
| `language.fallback` | `CANONICAL_NAMES` (57 nomes em prosa) | sim |
| `language.allowed` | `LANGUAGE_CODES` + `"*"` | **não, por desenho** |
| `language.aliases` (chave e valor) | `LANGUAGE_CODES` | **não, por desenho** |
| `frontend.language.default` / `enabled` | `UI_LANGS` (8 códigos secos) | sim |

Desde a **v0.1.65** (17 Set 2026), `compliance.config_variations` guarda as
**variações materiais de configuração** de um deployment — capacidades ativadas
num cliente que a frota não tem (hoje: a consulta analítica tabular), com
finalidade, datas, se alteram a finalidade prevista ou a classificação de risco,
o que trouxeram de novo e quem reviu. Vem da nota jurídica de 14 Set 2026: a
variação não faz do deployment um AI system distinto, mas sem registo não há
como o defender. Lista vazia = alinhado com o comum. É **inteiramente interno**
(chega ao deployer pela documentação Anexo IV, não por painel do cliente) e não
tem efeito nenhum no data plane.

Desde a **v0.1.68** (22 Set 2026):
- o registo de variações ganhou os **campos jurídicos** da nota de 22 Set
  (versão avaliada, referência da alteração, materialidade, fundamentação,
  controlos afetados, evidência, medidas com dono e estado, gatilhos de
  reavaliação). Continua **interno**. `materiality`, `controls_impacted` e
  `reassessment_triggers` são vocabulários fechados (`Literal`) — seguros por
  serem campos novos, sem valores históricos a partir;
- `compliance.data_subject_rights` (`controller_name`, `request_channel`,
  `dpo_contact`) diz ao core quem é o **responsável pelo tratamento** e por
  onde se lhe pedem direitos, para a resposta a "apaga os meus dados".
  `client_write` — são factos do deployer. **Não** é validado no modelo: o core
  (`core/compliance/data_subject_rights.py`) só usa um canal com forma de email
  ou URL https, e trata o default "Genesis Digital Solutions" do `company_name`
  como ausência (senão apresentava a Genesis, subcontratante, como responsável);
- a derivação de controlos (`presentation.py`) passou a ver o `enum` dos ITENS
  de uma lista: `List[Literal[...]]` é `select` + `list` (escolha múltipla).
  Antes dava `text`, e nunca se tinha notado porque não havia nenhuma.

Desde a v0.1.53, os quatro campos de data do `compliance` declaram
`format: "date"`/`"date-time"` no JSON Schema (via `json_schema_extra`, só
anotação — a validação continua a aceitar texto livre, porque o modelo também
CARREGA perfis com valores históricos imperfeitos). ⚠️ O
`retrieval.latest_version.date_field` parece data e NÃO é (é o nome de um campo
do índice) — há teste a proibir-lhe um `format`.

O `ISO_TO_CANONICAL` **veio do core** na v0.1.51 (`core/agent/language_detector.py`),
onde era privado — e era por isso que nem o Studio nem o backoffice do cliente
conseguiam validar nem renderizar nenhum destes campos. O core passou a importar
daqui e os nomes privados dele mantêm-se, para os usos internos não mexerem.
**Não recriar uma cópia local no core**: era a divergência silenciosa que isto
fechou.

O `UI_LANGS` é uma cópia deliberada do `UI_LANGS` do fecore
(`src/app/i18n/strings.ts`) — é TypeScript, não há como importá-lo. Quem
acrescentar uma língua de interface lá tem de acrescentar aqui **e** dar-lhe
etiqueta no `ui_text`; há um teste a chumbar nesse dia.

Nenhuma função deste módulo recusa nada: `is_known_language_code()` responde se
a língua está no mapa, e um `False` é motivo para AVISAR, nunca para bloquear —
`allowed` aceita línguas de fora de propósito.

### 7b. Que campos são multilíngues — `i18n_fields.py` (19 Out 2026, v0.1.128)

`i18n_field_paths()` dá os campos `{língua: texto}` (dialecto do `exposure`, `*` na chave de um mapa de
modelos, `tools.config.<tool>` à frente dos blocos das tools). A marca é o NOME do alias no fonte
(`I18nMap`/`I18nText`/`I18nHelp`/`I18nNotice`, procurado na MRO), a mesma regra do `i18n_maps.py` do
gaibo. Não muda nenhum tipo nem o JSON Schema (hash igual antes e depois). Regra do produto: todo o
campo multilíngue tem a opção de o agente traduzir. Um `Dict[str, str]` novo sem alias chumba o teste
até entrar em `NOT_I18N_STR_MAPS` (com a razão) ou usar o alias. ⚠️ Os três multilíngues de facto em
`Union[str, Dict[str, str]]` (rótulos da extração legal e da captura, finalidade da captura) ficam em
`UNMARKED_I18N_FIELDS`. Pôr-lhes o alias muda o gaibo (editor por língua + portão de gravação), por
isso combina-se primeiro com a equipa do gaibo. `tool_config_models()` (`tool_configs.py`) é a cópia
pública do `_KNOWN_TOOL_CONFIG_MODELS`. O nome privado fica: o gaibo importa-o.

### 7c. Tarefas do agente — `agentic.py` (20 Out 2026, v0.1.129)

`ProfileAgentic` (`agentic: {enabled, budget{steps 1–200, writes 1–50, wall_clock_hours ≤ 720}}`),
opcional na raiz e por frente; ausente ou `null` = desligado. Exposição INTERNAL (só a Genesis liga, no
Studio). O core lê-o como dicionário em `core/agent/durable/config.py`; os tetos espelham os do core.
**v0.1.132 (A3, 27 Out 2026):** `budget.cost_eur` (0–50 €], `plan_visible` (lista de passos no chat;
ausente = sim) e `verify` (A2: reler depois de cada escrita; ausente = sim) — todos INTERNAL, com label
e ajuda em pt-PT/en-GB. Omissões do core: 20 passos, 3 escritas, 720 h, 0,50 €. **v0.1.152 (4 Nov 2026, épico «Agente colega», passo 1):** `agentic.enabled` passa a CLIENT_WRITE (o cliente liga e desliga no GAIBO; desligar pausa os agentes das filas no core); o resto de `agentic.*` continua INTERNAL; a ajuda ao cliente cabe no popover e o detalhe de operador está na `note`.

---

### 7d. Entradas e encaminhamento — `channels.py` (11 Nov 2026, v0.1.163)

`ProfileChannels` (`channels: {inputs[], routes[]}`, carril C1a do `codigo/CONTEXT_PACK_canais_entrada_saida.md`): entradas (`id`, `channel` numa allowlist de 10 canais — só `email` é lido pelo core, `LIVE_CHANNELS`; uma entrada de email aponta sempre para uma fonte do `ingest.sources` por `ingest_source`) e rotas por ordem (`inputs` vazio = todas, `when: {all, any}` com condições `{field, op, value}` FECHADAS — `ROUTE_FIELDS` com tipo — `text`, `address`, `number`, `bool` — e `OPS_BY_KIND`; campo ou operador desconhecido = erro de schema — e `to: {module: queue, queue}`; `MODULES` cresce um carril de cada vez). É a única gramática das rotas: o core e o Studio importam as constantes daqui (nunca uma segunda allowlist). `None` = hoje (o core traduz o `ingest.sources` em memória). Tudo `internal`; modelos `extra="forbid"`; `all`/`any` sem alias (o `to_blob_dict` grava pelos nomes dos campos). O GAIBO não conhece a área — o handoff (`codigo/HANDOFF_gaibo_channels_area_floor.md`) pede para a pôr no `AREA_FLOOR` ANTES de o GAIBO subir o pin para a v0.1.163 (senão o `test_every_wholly_internal_area_is_floored` dele fica vermelho — falha fechada) e muito antes de qualquer campo passar a `client_write`. **Ordem de rollout** (a regra do `mcp.servers[].signing`): modelos `forbid` + gramática fechada ⇒ um core com este pin recusa um `channels` escrito por uma versão futura e, com ele, o save do perfil inteiro (400) — nunca valores novos no perfil antes de core e GAIBO terem o pin; promoção e clone conferem o pin do destino. SEM `regex` (revisão de 11 Nov 2026: avaliado sobre texto de quem envia, o `re` do Python não tem tempo limite e nenhuma lista de padrões proibidos fecha o ReDoS — volta com um motor com tempo limite); endereços (`from.*`, `to`) só `equals`/`in_list`/`exists`, nunca substring. `allow_inf_nan=False` nas condições. Ids (`ID_RE`, `fullmatch`) aceitam os ids das fontes do Studio (maiúsculas, até 64).

## Camada 8 — o que o prompt base impõe: `house_rules.py` + `house_rules/<locale>.json`

A primeira camada que NÃO descreve a forma do perfil: descreve o comportamento
que o prompt base do bot impõe a toda a frota, para que quem escreve
`custom_instructions` (Studio hoje, backoffice do cliente ao re-pinar) seja
avisado quando o texto desfaz uma regra da casa. Existe porque as
`custom_instructions` GANHAM ao prompt base por desenho e o Studio e o gaibo não
falam um com o outro — este pacote é o único canal.

- **Registo** (`HOUSE_RULES`, dict por `rule_id`): classe `invariant` (há portão
  em código; uma instrução contrária não tem efeito) · `strong_default` (só
  prompt; a instrução do cliente ganha de facto) · `lever` (já é campo do
  perfil) · `guidance` (apresentação). Por regra: onde vive o portão, a frase
  literal do `prompt_builder` (`anchor`) e os `lever_paths`. Severidade por
  classe em `SEVERITY_BY_CLASS` (`no_effect | warning | note | info`) — contrato
  com quem desenha o aviso.
- **Texto por língua** em `house_rules/pt-PT.json` e `en-GB.json`: `title`,
  `summary` (o que o produto impõe), `boundary` (o que o cliente PODE fazer),
  `example_conflict`, `example_ok`. Mesma tolerância do `ui_text`; viaja no
  `package-data`. `describe(locale)` funde registo e texto.
- **Separação playbook/cliente** (`custom_instructions_text.split_playbook_blocks`):
  corta os playbooks MCP copiados para o campo pelo cabeçalho
  `## … [genesis-mcp-<x>-playbook-vN]` até ao próximo `## ` ou à primeira linha em
  branco (os 4 playbooks reais não têm nem um nem outro por dentro). Sem isto um
  lint reporta como colisão do cliente a nossa própria cópia congelada.
- **A régua:** um invariante só é invariante com portão em código; a lista de
  invariantes é fechada no teste, com motivo. **A direcção** é julgada sobre o
  texto do cliente (restringir é sempre seguro); este registo só diz o que cada
  regra impõe.
- **O que impede o registo de mentir:** o core (que pina este pacote) tem
  `tests/test_house_rules_anchors.py` a confirmar que cada `anchor` continua no
  `prompt_builder`. Regra sem âncora só quando o portão é só código/config.
- **`no_candidate_ranking` (v0.1.70, 23 Set 2026, épico Análise de CVs — regra
  D7):** com CVs na conversa o bot resume mas não ordena, pontua nem recomenda
  candidatos (AI Act Anexo III, 4.a — faz-se na triagem `analyse_cv`, com
  supervisão humana). `strong_default`, só prompt, âncora "Do NOT rank, score or
  shortlist candidates". O bloco no core é CONDICIONAL ao turno
  (`core/agent/cv_turn.py`) — a âncora vive numa função do `prompt_builder`, que
  o teste de âncoras do core lê pelo código-fonte.
- **O lint em si NÃO vive aqui** — é do consumidor (Studio:
  `custom_instructions_lint.py`). O pacote dá a lista e o corte, para que os
  dois lados avisem contra o mesmo.

---

## Ata legal — `audio.municipal_minutes` (2 Nov 2026, v0.1.141)

`organ_type` aceita também `orgao_colegial` («Órgão da Administração Pública — conselho, júri, comissão
— regras do CPA, art.º 34.º»), com os textos da UI em pt/en. O core e o fecore já o aceitam; um perfil
gravado com ele por um core com o pin antigo dá 400 — a v0.1.141 traz-o; escolher só com os pins nela.
**v0.1.142 (2 Nov 2026, F2.4):** cada membro ganha `email` opcional (validado com a regex do Intake, minúsculas,
`client_write`) — para onde o espaço «Reuniões» envia a convocatória, a minuta e a ata aprovadas; nunca chega ao
prompt nem à ata (o `municipal_config` do core descarta-o).
**Biblioteca de modelos de ata (v0.1.144, 3 Nov 2026, F3.6/R10; D11/D23):** `minutes_library.py` + `minutes_library/*.json`
(`list_models()`, `get_model(id)`, `model_for_organ_type(organ_type)` — os quatro órgãos autárquicos → `autarquia`,
`orgao_colegial` → `orgao_colegial`; cópias; cada modelo validado ao carregar). Nesta versão cada modelo traz só os
PRAZOS LEGAIS depois da reunião (`deadlines`: `id`, `label` pt/en, `law`, `from: meeting_date`, `days`, `unit`
`calendar|business`, `window` opcional, `scope` opcional): a autarquia tem o edital (5 dos 10 dias seguintes,
Lei 75/2013, Anexo I, art.º 56.º n.º 1) e a publicação (30 dias, n.º 2), em dias corridos (a lei não diz; a
confirmar com o jurídico); o órgão da AP não tem. Prompts, validador e fórmulas migram depois (D11). Não é campo do
perfil: não entra no `EXPOSURE` nem no registo de sugestões do Studio.
**Tipos de reunião por dados (v0.1.146, 3 Nov 2026, F4 — decisão do Bruno):** cada modelo da biblioteca traz `family` (municipal/public/private), `regime`, `rules`, `member_term`, `outsiders`, `weight` (permilagem no condomínio, capital nas sociedades) e `organs[]` (o `id` é o `organ_type` do perfil; `preside`, `roles` = a lista fechada em PT, `signatures`, `subject` da fórmula, `closing`). Modelos novos: `condominio`, `sociedade_comercial` (AG SQ/SA, CA, gerência), `associacao`, `ipss` (deliberação reproduzida na íntegra, art.º 21.º-D). `organ_model_map()`/`organ_types()`/`organ_info()` substituem o mapa fixo; um teste prova que o `Literal` do `organ_type` e a biblioteca são os mesmos. Membros ganham `weight` (dado do cliente, nunca inventado). Prazos por órgão (`deadlines[].organs`, validados contra os órgãos do modelo; `organ_info()["deadlines"]` só traz os do órgão); o validador recusa um modelo a meio (regime sem `family`/`organs`, órgão repetido). Percurso `audio` com o caso `private_body` e `members.weight`/`members.email`. v0.1.147: `audio.meetings_quick_mode` (modo «Rápido», `client_write`) e o caso `quick` no percurso. v0.1.148: `contacts.link_meetings` (membros das reuniões ligados aos contactos, só pelo email). Pesquisa jurídica em `codigo/CONTEXT_PACK_reunioes_F4_tipos_privados.md`; falta a validação do Michel.

## Percursos de configuração — `module_guides.py` + `module_guides/*.json` (31 Out 2026, v0.1.140)

O PERCURSO de cada módulo: casos de uso («Para que é?», com predefinição), passos por ordem marcados
`essential`/`optional`/`advanced` (para que serve, quando usar, campos essenciais e avançados, condição, «feito»,
exemplos), ligações a outros módulos (declaradas uma vez, do lado de quem recebe; `links_for` mostra-as dos dois
lados) e «Rever». Fonte única do ecrã guiado do Studio, do Mapa dos módulos, da tool `get_module_guide` do agente e do
manual. O genai-core não o lê. Módulos: `ingest`, `review_queues`, `intake`, `cv_screening`, `doc_verification`,
`retrieval`, `auth`, `audio`. Validação ao carregar: caminhos que existem no schema, nenhum campo em dois passos; nos
módulos de mapa todos os campos do item num passo; nos de perfil, testes de cobertura por módulo (CVs, Pesquisa, Autenticação, Verificação documental). Um caso pode
estar «em preparação» (`available: false`, 3 Nov 2026 — sem predefinição; ex.: «Concursos — quem avalia», ainda sem
esquema no core). Predefinições em `module_guides/presets/<módulo>.<caso>.<língua>.json`, GERADAS do código do editor
do Studio (`frontend/scripts/queue-presets.mjs`, `docver-presets.mjs`) com teste de paridade lá — nunca à mão: num
módulo de mapa `item` (validado com o modelo do item), num de perfil `config` = o bloco `tools.config.<tool>`
(validado com o modelo da tool). `doc_verification` (3 Nov 2026): casos «Concursos — quem concorre» (esquema
`concursos`), «Candidaturas a apoios por formulário» (`fem`) e «quem avalia» em preparação; o que o ecrã do cliente
mostra (separadores, registo) é do ESQUEMA no core, não do perfil.

## Tabelas-resumo, totais, `@same` e domínios da empresa — `queue_summaries.py` (5 Nov 2026, v0.1.157)

`reviewQueues.<fila>.summaryTables`/`summaryTotals` tipados com as regras do produtor (core
`review_queue_summaries.py`) — mas aqui uma entrada partida RECUSA o perfil, onde o core a largava em
silêncio; `check_summary_references` liga as partes `summary` às tabelas da mesma fila (validador da
`ProfileReviewQueue`). `columnLabels`/`valueLabels` usam o alias `SummaryText` (não `I18nMap`): são mapas
coluna → texto, e com `I18nMap` no nome o `i18n_field_paths` marcava o mapa inteiro como multilíngue.
`SAME_STATE = "@same"` documenta o destino reservado de `actions[].to` (só um core ≥ 145e88a0 o entende).
`ProfileIngest.internal_domains` normaliza como `customer_mapping.internal_domains()` e recusa o que não é
domínio (`_I`). Campos novos no passo `fields` (avançado) do percurso `review_queues`.

## Checklist: acrescentar um campo

1. **Modelo** — o campo em `client_profile_schema.py`, com tipo, default seguro
   e limites. Um perfil vazio validado tem de continuar a ser um perfil
   funcional.
2. **Classificar** — entrada em `EXPOSURE`. Pergunta as duas perguntas, sempre
   as duas: *o cliente precisa de ver isto?* e, separadamente, *pode alterá-lo
   sem partir nada nem contornar um controlo nosso?* Na dúvida, `internal`:
   abrir depois é fácil, fechar depois de o cliente ter mexido não é.
3. **Nomear** — `label` nas duas línguas; `help` se for interruptor ou número
   visível ao cliente (até 240 caracteres nos visíveis); `options` se for lista
   fechada visível; `note` se houver detalhe operacional nosso.
4. **Controlo** — só se o schema não conseguir dizê-lo sozinho: prosa, código,
   endereço ou nome de um catálogo externo (`combobox`, com as sugestões em
   `options`) vão a `CONTROL_OVERRIDES`. Tipo, lista fechada e cor derivam-se —
   também dentro dos blocos tipados de `tools.config`. Um `str` com `options`
   no catálogo tem de ser `select` ou `combobox`; o teste chumba se for prosa.
5. **Gates** — `python -m pytest tests/` tem de passar. Ele chumba se ficares a
   meio de qualquer um dos passos acima.
6. **Versão** — `pyproject.toml`. Alteração só de texto é patch; campo novo é
   patch também, mas obriga a re-pin nos consumidores para lá chegar.
7. **Esta página** — se a capacidade mudou, actualizar a entrada. Uma frase.

## Checklist: remover ou renomear um campo

Não há remoção silenciosa: os testes chumbam com entrada morta em `EXPOSURE` e
no catálogo. Remover é remover nos três sítios. Antes disso, confirmar no
**produtor** de cada consumidor se ainda é lido — `extra="allow"` significa que
um campo removido do modelo continua a viver no blob sem dar erro.

---

## Invariantes que os testes protegem

198 testes em `tests/` — `test_exposure.py`, `test_ui_text.py`,
`test_presentation.py`, `test_field_checks.py`, `test_languages.py` e
`test_value_bounds.py`:

- Toda a folha do schema está classificada; nenhuma entrada morta.
- Áreas inteiramente internas — `retrieval`, `mcp`, `runtime`, `pricing`,
  `query_cache`, `contacts` — verificadas **contra o schema**, não contra a
  tabela, para apanhar um campo novo que lá entre.
- 35 caminhos nomeados um a um que nunca podem ficar visíveis ou editáveis, cada
  um com o motivo escrito no teste: os cinco `frontend.csp.*`, os slots de
  credencial do MCP, `mcp.servers.trusted`, os pisos anti-invenção do
  `retrieval`, a divulgação de IA do AI Act, a escolha de modelo.
- Conteúdo de mapa aberto herda o nível do mapa; excepções por caminho exacto
  (`tools.config.generate_boq.*`) ganham.
- Toda a folha tem nome nas duas línguas; interruptores e números visíveis têm
  ajuda; listas fechadas visíveis têm os valores nomeados **nos dois sentidos**
  (um membro novo no schema chumba; um membro removido deixa texto órfão que
  também chumba).
- Valores nomeados no catálogo implicam um controlo de escolha: `select` se a
  lista fecha, `combobox` se aceita texto livre. Um `combobox` tem sempre
  sugestões nas duas línguas e nunca assenta num `enum`. Os `enum` dos blocos
  tipados de `tools.config` derivam sem linha na tabela.
- Catálogo em falta devolve vazio em vez de rebentar — texto de interface não
  derruba serviços.
- Os campos SEM CONSUMIDOR ficam escondidos, com o motivo por campo. Um campo
  editável que não faz nada é pior do que um campo ausente: o cliente muda-o,
  acredita que mudou algo, e o suporte descobre meses depois.
- `identity.default_language`, `audio.max_duration_min` e `voice.transcription.model` (v0.1.149) estão marcados `deprecated` no próprio JSON Schema
  (não só num comentário), e não pode voltar a ter `help` — a ajuda que lá
  estava descrevia um comportamento inexistente.
- `language.fallback` tem de mostrar a FORMA do valor na ajuda: o rótulo
  sozinho convida a escrever `pt-PT`, que é a coisa errada.
- **Os defaults do contrato vivem dentro dos espaços de valores que o contrato
  publica**: o `fallback` de fábrica é um `CANONICAL_NAMES`, os `aliases` são
  `LANGUAGE_CODES`, o `frontend.language.default`/`enabled` são `UI_LANGS`. Se
  divergirem, o backoffice desenha um select onde o valor actual do cliente não
  aparece — e ao guardar muda-o sem ninguém pedir.
- Os dois espaços de língua têm de continuar SEPARADOS (`pt` só na interface,
  `pt-PT` só no detector): juntar as listas parece arrumação e parte os campos.
- Cada `UI_LANGS` tem etiqueta nas duas línguas, nos dois campos — uma língua
  nova no fecore sem etiqueta dava uma opção sem nome no backoffice.
- Forma válida ≠ língua conhecida: `looks_like_language_tag("sw")` é `True` e
  `is_known_language_code("sw")` é `False`, e `language_tag_problems` **não**
  consulta o mapa. É o que mantém `allowed` aberto.

---

## Armadilhas medidas

- **Um default aqui é comportamento em produção, não só documentação.** O core
  funde o perfil do Blob por cima de `ClientProfileSchema().to_blob_dict()`
  (`DEFAULT_PROFILE`) e a migração de clientes do Studio parte do mesmo dict:
  a chave AUSENTE no Blob vale o default deste ficheiro. Caso real:
  `toolWorkspace` ficou a `True` (comentário "opt-OUT") depois de o core passar
  a opt-in — todo o perfil sem a chave recebia o layout dedicado ao ligar a
  fatura/BoQ. Corrigido v0.1.69 com teste (`test_tool_workspace_default.py`).
  Mudar o sentido de uma flag no core obriga a mudar o default AQUI.
- **`extra="allow"` em todo o lado.** Uma chave inventada é aceite sem erro. É
  por isso que o Studio tem o `profile_schema_guard.py`; a validação Pydantic
  sozinha não apanha typos. **O caso extremo já aconteceu**: o envelope do
  `GET /admin/profile/get` (`{profile, etag, last_modified}`) validava como se
  fosse um perfil — `client_id` a `None`, `identity` nos defaults, perfil real
  enterrado numa chave extra, resposta 200. O core recusa-o desde Set 2026
  (`profile_save_guards.py`); o schema continua a aceitá-lo, por desenho.
- **`ge=` não trava o infinito** (corrigido v0.1.54). `weight: float = Field(ge=0.0)`
  aceitava `1e400` → `inf`, e no merge dos scores `0.0 * inf = nan` tornava a
  ordenação do retrieval arbitrária. `nan` já era recusado pelo `ge`; `inf` não.
  Fechado com `allow_inf_nan=False` no `ProfileRetrievalIndex`. Qualquer campo
  `float` novo que multiplique alguma coisa precisa do mesmo.
- **A regra dos limites foi reescrita conscientemente (v0.1.54).** O docstring da
  `ProfileRetrieval` dizia "sem limites superiores — na dúvida, subir" e estava a
  ser lido como "nunca pôr tecto nenhum". A instrução original era **não baixar um
  limite se isso piorar o funcionamento** — não "é proibido pensar em tectos".
  Agora estão lá as quatro alíneas. O ponto que muda decisões: **acima de 50 o
  `top_k` não é honrado** (hard limit do semantic reranker do Azure, cortado no
  `azure_search_client`), por isso 200 configurados entregam 50 e o operador fica
  a acreditar noutra coisa. O tecto `le=200` é rede para o zero a mais, não
  política de custo — há um teste que falha se alguém o apertar abaixo de 4×50.
  Medido a 3 Set 2026 em dois índices vivos (1417 chunks): **~330 tokens/chunk em
  média, ~1130 no p90** — subir o `top_k` de 20 para 50 leva o contexto de ~22k
  para ~57k tokens por turno, a p90.
- **Um limite que o schema não declara é um contrato que mente** (v0.1.54).
  `shareDefaultExpiryDays` aceitava 999999; o core sempre cortou em 30
  (`MAX_EXPIRY_DAYS`). O modal oferecia o prazo grande, o servidor entregava 30
  dias, ninguém via. Agora `le=30` aqui e nos itens de `shareExpiryOptionsDays`.
  **Para prazos maiores sobe-se primeiro o core, depois este `le`** — nunca ao
  contrário.
- **O dialecto dos caminhos.** Índice-free: uma lista de objectos é percorrida
  ao MESMO caminho da lista (`retrieval.indexes.name`). `leaf_paths()` é a
  travessia canónica — havia três escritas à mão, cada uma com o seu dialecto.
  Se precisares de outro dialecto, deriva-o desta.
- **Sete campos de língua, TRÊS espaços de valores, um campo morto.**
  `language.strategy`/`allowed`/`aliases`/`fallback` mandam no bot;
  `frontend.language.default`/`enabled` mandam no selector da interface;
  `identity.default_language` **não é lido por ninguém** (deprecado v0.1.51).
  Dentro do bloco `language` já há dois espaços — `allowed`/`aliases` são
  códigos ISO, `fallback` é o NOME CANÓNICO que vai como instrução ao modelo —
  e o `frontend.language.*` é um terceiro: os 8 códigos SECOS do `UI_LANGS`
  (`pt`, não `pt-PT`). MEDIDO nos 29 perfis da frota: todos usam `pt`, e `pt`
  não existe no mapa do detector. Ver a camada 7.
- **`frontend.language.enabled` chega ao selector do chat SEM filtro.** Medido
  no fecore: o `chat.component` faz `this.enabledLanguages = enabled` tal e
  qual, e o `pickLang` do `client-config.service` procura a chave exacta. Um
  código com região (`pt-PT`) renderiza uma entrada cujas strings caem para
  inglês ou português — degrada em silêncio, não dá erro.
- **`voice.transcription.*` passou a ter consumidor na v0.1.68** (22 Set 2026, caminho B do parecer Astra): transcrição das conversas por voz no WIDGET com o motor GPT-Live, gravada pelo core (`live_web.py`) na conversa `voice:live:<sessão>` com o TTL das conversas ou `retention_days` (0, vazio ou lixo normalizam para None = a retenção das conversas — sem `ge`, para um 0 gravado por um GAIBO antigo não bloquear a gravação do perfil). OFF por defeito — é gravação de dados pessoais (RGPD), exige DPA e aviso ao visitante. Entre v0.1.61 e v0.1.67 os três caminhos foram `internal` porque nada os lia (a promessa era reabrir a exposição no mesmo commit em que o consumidor nascesse — cumprida): `enabled` e `retention_days` são agora `client_read` (o cliente VÊ, nós ligamos); `model` continua interno e sem consumidor (a transcrição vem da própria sessão GPT-Live) e está **deprecado desde a v0.1.149** (mesma marca do `identity.default_language`).
- **Defaults mudados na v0.1.105 (13 Out 2026): `voice.queue` passa de `"tickets"` a `""` (voz sem fila por omissão) e `compliance.retention.conversations_anonymous_days` de 90 a 180** (decisão de 12 Out). Armadilha: o save do core grava os defaults literais (`to_blob_dict`), por isso os perfis já gravados TÊM os valores antigos explícitos (15 de 15 com `voice.queue` a 13 Out) e não mudam com o bump — mudar perfil a perfil. Do lado do core, a fila da voz só é declarada com a voz ligada (`review_queue_names`), e o fallback `DEFAULT_ANONYMOUS_DAYS` subiu também. **v0.1.152 (4 Nov 2026):** os dois prazos de `compliance.retention.conversations_*_days` passam a CLIENT_READ (o GAIBO mostra-os só em leitura; alterar pede-se à Genesis — decisão do Bruno na triagem do backlog do GAIBO).
- **`voice.transcription.phone` (v0.1.78, 1 Out 2026)**: transcrição das CHAMADAS telefónicas — fase 1, só o que o ASSISTENTE diz — gravada pelo core (`voice/phone_transcript.py`) na conversa `voice:<call_id>` (a mesma onde a ponte ao agente grava as consultas da chamada) com a mesma `retention_days`. Interruptor PRÓPRIO, separado do `enabled` do site (cada canal tem o seu aviso e a sua menção no DPA). OFF por defeito; `client_read` como o `enabled`. O chamador fica para a fase 2 (consentimento + deployment de transcrição), não é ligado por este campo.
- **`audio.live_transcription_enabled` + `audio.live_max_duration_min` (v0.1.69, 23 Set 2026, bloco 7 do pack GPT-Live §9)**: transcrição de REUNIÕES em tempo real pelo microfone no widget (Azure Speech `ConversationTranscriber` no browser; pós-produção pela tool `transcribe_audio` com `source="live"`). OFF por defeito — gravação de pessoas (RGPD) e ~1,30–1,60 USD/h. O toggle é `client_read` (o cliente vê, nós ligamos — matéria de DPA e de custo); o tecto é `internal`, 240 min por defeito e com piso `ge=240` (nunca abaixo, decisão do pack). Ambos com `requires_tool: transcribe_audio`. Consumidores: core `meeting_transcript.py` e `/client-config` (`transcription.live`); o peso `transcription_per_minute` do bloco `billing` é do Studio, não do schema. **`audio.teams_import_enabled` (v0.1.150, R18):** importar a transcrição de uma reunião Teams pelo conector Graph do core; OFF, `client_read` (DPA e consentimento do administrador do cliente; ligamos nós), passo `live` do percurso. **`audio.max_duration_min` (v0.1.95):** por omissão 240 (era 120) — alinhado com o teto FIXO de 4 h por ficheiro que o core aplica. **Deprecado na v0.1.149** (marca `deprecated` no JSON Schema, rótulo «não usado», nota sem ajuda): o core deixou de o ler e o Studio de o editar; fica por retrocompat dos blobs.
- **Equipa F4 — emissores de confiança para a equipa (v0.1.123, 16 Out 2026):** `frontend.auth.providers[].team_email_domains` (domínios normalizados, até 20; vazio = o emissor não vale para a equipa, o de sempre) e `allowed_client_ids` (apps aceites, `azp`/`appid`; vazio = qualquer app com a audience certa). Ambos `internal`: só a Genesis os marca, nunca o cliente nem o GAIBO. Um emissor com domínios da equipa exige `id`, e os `id` preenchidos não se repetem em `providers` (os vazios continuam aceites: a Indaqua tem quatro). Consumidor: core `core/auth.py` e `core/team/login_key.py` (a ficha liga-se por `iss`+`sub` com o email verificado de um desses domínios; o Entra de empresa continua por `tid`+`oid`).
- **`identity.timezone` é lido desde a v0.1.52** — o core resolve perfil > env
  `TZ` > `Europe/Lisbon` em `core/agent/clock.py`, e daí saem o bloco temporal
  do system prompt e o fast-path do "que horas são?". É a hora de NEGÓCIO do
  cliente, não a de cada utilizador (essa seria um header `X-Client-TZ`, que
  não existe). Um nome IANA inválido cai no de omissão com aviso no log.
  ⚠️ O core precisa do pacote `tzdata` no `requirements.txt`: a imagem é
  `python:3.12-slim` e sem ele um `Asia/Dubai` válido cai em Lisboa.
- **`retrieval.search_index_names` é override total da env.** Não é uma
  afinação de RAG como as vizinhas: escolhe QUE índice o bot consulta.
- **`frontend.csp.*` só actua no rollout do frontend.** O Studio funde as listas
  no `staticwebapp.config.json`; sem novo rollout não há efeito em runtime. Isso
  atrasa a exploração, não a impede — a classificação mantém-se interna.
- **`reviewQueues`**: uma fila referida por um nome ausente deste mapa passa a
  existir como fila fantasma no Cosmos. **`reviewQueues.{fila}.fields` (v0.1.98,
  `queue_fields.py`)**: deixou de ser `List[Dict]` livre; é uma lista da definição
  de campo ÚNICA (`FieldDefinition`), com até 200 campos e chaves sem repetição —
  rótulos por língua, tipo, ordem/grupo, `editable`/`hidden`/`required`. Sem
  `fields` a fila fica igual. Consumidores: core `review_queue_spec` (passa-os no
  `to_public`) + validação do payload editado; fecore detalhe da `/fila`; Studio
  editor de campos da tab Filas. `reviewQueues.{fila}.sla` (v0.1.77) é
  interno como o resto da fila; o `calendar` (v0.1.77, raiz, `Optional` — um
  perfil sem ele fica com `calendar: null` no blob validado — o `to_blob_dict`
  não omite nulos, e o core e o Studio tratam null como ausente; quem escreve
  `calendar.holidays` tem de criar o nó) tem os feriados municipais editáveis
  pelo cliente (`calendar.holidays` = CLIENT_WRITE; `AAAA-MM-DD`, `MM-DD` ou
  `easter±N`) e o país/descanso só de leitura. Booleanos recusados (não viram
  1 h nem terça-feira); em dias úteis o prazo vai até 366.
- **Os catálogos são dados.** `[tool.setuptools.package-data]` no `pyproject` é
  o que os faz viajar no wheel. Sem essa linha o pacote instala sem os JSON e o
  catálogo fica vazio em produção, em silêncio.
- **`runtime.agent_mode` é um vocabulário, não um esforço** (v0.1.62, 16 Set
  2026): aceita `fast | balanced | thinking | max | auto` — os nomes que o
  Studio mostra (Rápido, Equilibrado, Pensamento, Máximo, Auto router) e que o
  genai-core traduz em `reasoning_effort` numa tabela fixa
  (`core/managers/effort_modes.py`). O esforço técnico (`xhigh`, `high`) e o
  modo Pro NÃO entram aqui. O core valida o perfil no save com este `Literal`,
  logo um valor novo só chega ao Studio depois do re-pin no core — o Studio
  que o ofereça antes recebe 422. Teste: `tests/test_runtime_agent_mode.py`.
- **Tectos das imagens que o modelo vê vivem em `tool_limits`** (v0.1.63, 16 Set
  2026): `max_images_per_turn` (10) e `max_image_total_mb` (40), `client_read`
  como os limites de caracteres. Eram só env no core
  (`MULTIMODAL_MAX_IMAGES_PER_TURN` / `MULTIMODAL_MAX_TOTAL_MB`); o core lê
  perfil > env > default. **Zero é "não enviar imagens ao modelo"** — decisão de
  produto (gancho para créditos por cliente), não um limite reduzido: o texto
  extraído no upload continua a servir o turno.
- **Ponte voz → agente completo vive em `voice.agent`** (v0.1.64, 16 Set 2026,
  Bloco D do parecer Astra): `enabled` (OFF), `mode` (o vocabulário de
  `runtime.agent_mode`, `fast` por default), `timeout_s` (30, piso 10) e
  `max_speech_chars` (900, piso 300). Vale para os dois canais de voz. O
  consumidor é o `voice/agent_bridge.py` do genai-core (tool
  `consultar_agente`); `enabled`/`mode` são `client_read`, os tectos internos.
- **`voice.greeting` é `str | {lang: texto}`** (v0.1.66, 22 Set 2026), o mesmo
  padrão de `welcomeMessage`: a sessão de voz do widget passou a falar a língua
  seleccionada no frontend, e a saudação tinha de a acompanhar. A `str` continua
  válida e o core lê-a como estando em `voice.language`. Regra do consumidor
  (`voice/greeting.py` do genai-core): sem saudação na língua da sessão diz-se só
  a divulgação de IA nessa língua — nunca se cola a saudação de outra.
- **`tools.config.run_code` é o bloco tipado da análise com código** (v0.1.67,
  22 Set 2026, F3 do parecer Astra): `deployment`, `timeout_s` (120, piso 60),
  `max_runs_per_turn` (2, piso 1), `memory` (1g/4g/16g/64g), `max_output_files`
  (5, piso 1), `allow_attachments`. A tool é OFF por omissão (só em
  `tools.enabled`) e a config é interna: os anexos saem para a sandbox do
  fornecedor e cada execução é uma sessão facturada. Consumidor:
  `tools/run_code/` do genai-core.
- **`tools.config.search_web` tem tecto por resposta e leitura de páginas**
  (v0.1.136, 29 Out 2026): `max_calls_per_turn` (2, piso 1),
  `read_pages` (False; liga a tool companheira `read_web_page`, só com
  `allowed_domains`) e `max_page_reads_per_turn` (3, piso 1); `null` vale o
  mesmo que ausente. Consumidores: `tools/web_search/turn_limit.py` e
  `tools/web_page_reader/` do genai-core.
- **`tools.config.analyse_cv` é o bloco tipado da Triagem de CVs** (v0.1.71,
  23 Set 2026, épico Análise de CVs, Fase 4), em módulo próprio
  (`tool_cv_analysis.py`): `prompt_preset`/`prompt_custom` (overlay de domínio),
  `retention_days` (183–365), `max_batch` (50–500), `parallelism` (1–16),
  `deployment` e `job_templates` (vagas-tipo com critérios na forma que o
  workspace confirma; tectos = os do motor: 40 critérios, 500 chars, 30 000 de
  anúncio). Pisos e tectos = os que o core aplica. O cliente edita domínio,
  retenção e vagas-tipo; lote, paralelismo e deployment são internos. **Não há**
  interruptor da máscara nem do texto escondido — são contrato (D2). Consumidor:
  `tools/cv_analysis/jobs/settings.py` do genai-core.
  **v0.1.126 (19 Out 2026, F1 do plano da triagem):** anúncio da vaga-tipo até 60 000 (= o core);
  `job_templates[].interview_checks` («a confirmar fora do CV», ≤ 40 × 300); `candidate_notice` (empresa,
  assinatura, contacto só email ou `https://`, e `templates` por decisão `advance|hold|reject|none` × língua
  `pt|en`, únicos, com campos de fusão por allowlist `CV_NOTICE_MERGE_FIELDS` — um `{campo}` desconhecido é
  recusado; a nota sobre a IA NÃO é campo, o fecore junta-a sempre); `pre_screening_notice` (`pt`/`en`, texto
  do aviso antes da triagem). Tudo fechado (`extra=forbid`) e `client_write`; os dois blocos são `Optional` —
  `null` no blob gravado = ausente.
- **`tools.config.verify_documents` é o bloco tipado da Verificação Documental** (v0.1.100, 8 Out 2026, contrato 101), em módulo próprio (`tool_doc_verification.py`): `scheme` (esquema dos casos novos, com a gramática de slug do core; texto com sugestões nas `options` do ui_text, **nunca** `Literal` — um esquema novo não pode partir o perfil num core com o pin antigo), `parallelism` (1–8, 4) e `deployment`. Tudo interno. **Não há** interruptor do login nem nomes de papéis/tenants: o core exige login sempre e o resto é env. Consumidor: `tools/doc_verification/jobs/settings.py` do genai-core (lido do perfil da frente do caso). **`document_templates` (3 Nov 2026, sem tag — vai no próximo bump):** os moldes do cliente dos documentos finais (o parecer no FEM, o relatório nos concursos), `[{scheme, document, name, sha256}]` com `extra="forbid"` e um por documento de um esquema (a versão fixa `fem@…` conta como o esquema base); vazio = o molde base da Genesis. O Word vive no armazenamento do cliente (contentor `intake-templates`), carregado pelo Studio no `PUT /admin/doc-verification/opinion-template` do core, que devolve a impressão; o core lê a referência em `tools/doc_verification/opinion/client_template.py` e, com outro conteúdo ou o molde em falta, recusa (503) — nunca o base em silêncio. No percurso guiado, `advanced` do passo `final_documents`. **`rules` (v0.1.159, 6 Nov 2026, F2 das regras configuráveis):** as regras do esquema que o cliente mudou, `{esquema base: {overrides: {id da regra: {enabled?, severity? (critical|attention), params? {nome: número | texto ≤200 | lista de textos ≤1000}, source? ≤400}}}}` com `extra="forbid"` e valores estritos (bool não passa por número); `{}` por omissão, nunca `null`. O schema só valida a forma: que parâmetros cada tipo de verificação deixa mudar (e o tipo de cada um) é do core (`engine/forms/overrides.py`), que ignora e reporta o resto. Nunca cria regras nem muda onde ler no formulário. No percurso, `advanced` do passo `purpose`. **`rules.<esquema>.added` (v0.1.160, 7 Nov 2026, F4):** as regras que o cliente ACRESCENTA — lista (≤ 50, `[]` por omissão, ids únicos) de `{id ^c\.…, layer row|photo, check, table?, doc_types?, params, sentence{pt,en} ≤400, source ≤400, criterion, severity, enabled}` com `extra="forbid"`; cruzamentos (`doc`) ficam de fora. Só a forma: que tipos, tabelas e colunas valem é do core (`engine/forms/added.py`).
- **Tema: o cliente só edita o essencial (v0.1.99, 7 Out 2026)**: as cores de pormenor do tema (`frontend.branding.theme.*`, `.light.*`, `.dark.*`, destaque por modo incluído) passaram a `client_read` — o cliente vê-as no gaibo mas edita só a marca (`primaryColor`, logos, texto do cabeçalho) e o `theme.finish`; a Genesis afina o resto no Studio. Os rótulos/ajudas do tema no `ui_text` foram reescritos pelo que o ecrã mostra (o menu do avatar deixou de se chamar «Fundo da barra lateral») e o Studio lê-os daqui (`theme_fields` em `/api/profile-value-spaces`) — uma fonte só. `identity.logo_url` passou a `internal`: não tem consumidor; o logótipo vive em `frontend.branding.logoLight/logoDark`.
- **Tema por modo, acabamento e «Powered by» (v0.1.98, 7 Out 2026)**: `frontend.branding.theme.light|dark.accent` e `textOnAccent` (destaque por modo; vazio = `primaryColor`/`primaryTextColor`), `frontend.branding.theme.finish` (`flat`/`gradient`/`metallic`/`glass`, opções fechadas — nunca CSS livre) e `frontend.branding.showPoweredBy` (`True` por omissão; **interno**, decisão comercial — o GAIBO não o mostra). Consumidores: `client-config.service.ts`/`theme-accent.ts`/`theme-finish.ts` do fecore e a tab Tema do Studio. Na mesma versão, `frontend.aiDisclosure.text` passou a `""` por omissão (= texto automático do fecore, na língua do utilizador); o antigo default em PT continua no módulo (`_DEFAULT_AI_DISCLOSURE`) só como referência.
- **`frontend.widget.resizable` e `frontend.insightsPanel.clearable` (v0.1.97, 7 Out 2026)**: os dois ligados por omissão e editáveis pelo cliente (`_W`). `resizable` deixa o visitante redimensionar o painel do widget (bordas e canto, tetos 60%/90% do ecrã, proporção 0,55–1,3; tamanho no browser); `panel_width_px`/`panel_height_px` passam a ser o tamanho inicial. `clearable` mostra o botão «Limpar painel» (com «Repor») no painel de insights do fecore. Consumidores: `assets/widget.js` e `insights-panel` do fecore (via `/client-config`, que devolve o `frontend` tal como está); o Studio edita-os no separador Widget e no painel de insights.
- **`voice.web.engine` escolhe o MOTOR da voz no widget** (v0.1.68, 22 Set 2026): `realtime` (default — o de sempre, zero regressão) ou `live` (GPT-Live full-duplex, com `voice.web.live_deployment`, ex. `gpt-live-1`). Ambos internos: são infra nossa (deployment, região, quota de sessões, fallback automático ao Realtime). Só o widget — o telefone fica no Realtime. Consumidor: `core/handlers/live_web.py`; o Studio cria o deployment quando o motor é `live`.
- **`tool_limits.attached_inline` põe o documento anexado INTEIRO no contexto**
  (v0.1.72, 25 Set 2026, C5 do parecer Astra), em módulo próprio
  (`attached_inline.py`): `enabled` (OFF = prompt de sempre no core) e
  `max_tokens` (default = máximo = 190 000, piso 1 000) — o tecto que o core
  honra abaixo do corte de preço dos 272k de input; o schema recusa mais do que
  isso. Os dois são internos (alavanca de custo nossa). Na mesma versão o
  default da frota de `max_attached_doc_chars` subiu de 250 000 para 800 000
  (≈190k tokens em PT) — um perfil com o valor explícito mantém o seu.
  Consumidor: `core/agent/attached_inline.py` do genai-core.
- **`access` — quem pode entrar numa frente** (v0.1.72, 25 Set 2026, contrato
  42): `ProfileAccess` na raiz (`allowedRoles`, `allowedGroups`,
  `allowedEmailDomains`, `allowedProviders`). **Default `None`, nunca um objeto**:
  o `to_blob_dict()` é o `DEFAULT_PROFILE` do genai-core e um `{}` por omissão
  exigiria identidade forte a toda a frota (teste `test_access_and_ciam.py`).
  Interno por agora (fronteira de segurança; expor no GAIBO é decisão futura).
  Consumidores: `core/authz/variant.py` (genai-core) e o `variant-access.component`
  do Studio. Na mesma versão, **`frontend.auth.tenantMode` aceita `"ciam"`**
  (Entra External ID, com `authority` `*.ciamlogin.com`; o fecore trata-o em
  `services/auth/variant-auth.ts` e no `msal-auth.service.ts`).

- **`intake.definitions` — questionários regulados com metodologia
  determinística** (v0.1.79, 2 Out 2026, épico Intake B1), em três módulos
  próprios: `rules_grammar.py` (a gramática das condições — JSON estruturado
  numa allowlist, sem `eval`, com tectos de profundidade/nós/listas/texto e
  números finitos; devolve as referências para quem valida as confirmar; o
  motor de regras do genai-core avalia esta MESMA gramática),
  `field_definition.py` (a definição de campo ÚNICA do produto: os 6 tipos do
  `form()` do core mais `multiselect`, `money`, `datetime`, `year`, `table`) e
  `intake_schema.py` (secções, perguntas com `show_if`/`assist`/`prefill_from`,
  glossário com allowlist de secções, e a metodologia: catálogo fechado de
  termos — `count_matches`, `points`, `category_max`, `bonus` —, completude,
  red flags, sequência de decisão, escalamentos e casos de referência). Toda a
  referência é confirmada ao gravar; uma pontuação não refere outra; a
  completude e as red flags não referem o resultado; `use_case` é allowlist sem
  `credit_scoring`/`hiring`; `extra="forbid"` em tudo (é novo). **Interno por
  inteiro** até o core o ler; nenhuma definição de cliente vive neste repo (os
  testes usam uma sintética). Consumidor: `core/rules/` do genai-core.
  Revisto no mesmo dia por uma revisão independente (13 achados, todos com
  teste): `field_values.py` valida RESPOSTAS pelo tipo da pergunta (o mesmo
  validador para os casos de referência e para o motor); os literais das
  condições são confirmados contra o tipo e as opções das perguntas; `show_if`
  sem ciclos (ordem topológica em `IntakeDefinition.visibility_order()`);
  orçamento de nós POR DEFINIÇÃO (`MAX_DEFINITION_NODES`); números estritos
  (`StrictNumber`: `true` e `"5"` não são números); taxas > 0; escalamentos
  sem encadeamento. **v0.1.133 (28 Out 2026, Quadrantis — condições de 27 Out):** `IntakeFund.active` (em subscrição; por omissão sim — só os ativos se escolhem ao criar um processo, um inativo fica na lista e nos processos que o têm); `IntakeFxPolicy.via_usd_sources` (fonte oficial de cada paridade fixa, só moedas de `via_usd`, até 200 caracteres; dentro do hash da metodologia, como `via_usd`; vazio = impressão igual à de antes); `IntakeDefinition.metric_targets` (`IntakeMetricTargets`: `completion_rate`, `fill_minutes_mean` (máximo, minutos), `prefill_unchanged_rate`, `agreement_rate` — opcionais; `null` = sem metas; operação, fora do hash); `IntakeRetention.unsubmitted_from` (`link_end` por omissão, como antes, ou `invite` — os dias de um processo nunca submetido e não cancelado contam do envio do convite, nunca antes de o link expirar). **v0.1.130 (21 Out 2026, Quadrantis — fundo por processo):** `IntakeDefinition.funds` (`IntakeFund` {key, name em todas as línguas}, até 50, chaves únicas) — com lista, quem cria o processo escolhe o fundo e a designação sai nos documentos e nas advertências; vazia = o `fund` único, como antes; operação, fora do hash da metodologia. **v0.1.94 (7 Out 2026, caderno C3):** `IntakeTexts.documents_notice` (`IntakeNotice`) — o aviso da leitura automática dos documentos carregados, aprovado pela Compliance do cliente; em todas as línguas da definição; sem ele o percurso mostra o texto do produto; fora do hash da metodologia (como os outros textos). **v0.1.93 (7 Out 2026, retenção):** `IntakeDefinition.retention` (`IntakeRetention`: `years` 1–30 — prazo de conservação de cada processo a contar da conclusão da avaliação ou da subscrição registada, se posterior; no fim o core apaga processo, ficheiros e pessoa sem outros processos, e durante o prazo os documentos guardados ficam imutáveis; vazio = nada se apaga sozinho, como antes — e `unevaluated_days` 7–3650, por omissão 90, para os processos nunca avaliados); operação, fora do hash da metodologia. **v0.1.92 (6 Out 2026, B13 — folha de cálculo do cliente como molde):** `IntakeDocumentTemplate.kind` aceita `spreadsheet` (molde `.xlsx`; os outros continuam `.docx`) com `cells` (`IntakeSheetCell`, até 200: célula «Folha!A1», origem FECHADA `INTAKE_SHEET_SOURCES` = answer/amount_base/subject_name/fund/evaluation_date, `map` valor da opção → texto da folha (numa escolha múltipla o core escreve a opção que mais pontua na metodologia; empate → a ordem do mapa, desde 21 Out 2026), `not_applicable` e `not_applicable_when` para o «N/A» só numa condição) e `result` (`IntakeSheetResult`: célula + texto da folha → resultado da metodologia); validado na definição (pergunta existe, `amount_base` só em montantes, chaves do mapa são opções, condições e resultados existem, células sem repetição). **v0.1.91 (6 Out 2026, B9 — documento de identificação e CV):** `IntakeQuestion.prefill_document_field` (lista fechada `INTAKE_ID_DOCUMENT_FIELDS`: nome completo, nomes próprios, apelidos, número, nacionalidade, país emissor, nascimento, validade, local de nascimento, sexo, morada — só com `prefill_from: id_document`, em perguntas editáveis e visíveis; sem ele o documento não propõe nada nessa pergunta); com várias origens propõe-se a primeira que der valor, por ordem fixa (documento, CV, comprovativo, convite, anterior); `IntakeDefinition.uploads` (`IntakeUploads.retention`: `delete_after_submit` por omissão — o ficheiro apaga-se na submissão e ficam os dados, os excertos e a impressão — ou `keep_with_process`; os ficheiros pedem-se só quando alguma pergunta os usa e são sempre opcionais; fora do hash da metodologia); `IntakeReviewPolicy.list_columns` (até 3 perguntas a mostrar na lista da equipa, validadas). Na mesma versão, a **biblioteca de modelos** do Intake passa a viver aqui (`intake_library.py` + `intake_library/*.json`: `list_templates()`/`get_template(id)`, cópias; cada modelo validado como `IntakeDefinition` ao carregar; 6 modelos genéricos — adequação, KYC, conflito de interesses, elegibilidade, fornecedores, consentimento) — fonte única para o Studio e o GAIBO; os de investimento propõem a partir do documento de identificação e do CV. **v0.1.90 (5 Out 2026, reavaliação):** `IntakeQuestion.prefill_from` aceita `previous` — numa reavaliação pedida pela equipa, a resposta da avaliação anterior da mesma pessoa aparece PROPOSTA (confirma ou corrige); só em perguntas editáveis e visíveis; nunca nas de conhecimento (decisão de produto: o teste responde-se de novo). **v0.1.89 (4 Out 2026, B7):** `IntakeDefinition.documents` (`IntakeDocumentTemplate`: `key`, `kind` questionnaire/internal_sheet/warning — `outcome` só e sempre nas advertências —, `title`, `template` (nome do .docx no armazenamento do cliente), `sha256` do molde aprovado, `version`, `effective_from`, `revoked_from`); versão única por tipo; fora do hash da metodologia (versão própria). **v0.1.88 (4 Out 2026):** `IntakeGlossaryTerm.questions` — allowlist por PERGUNTA dentro das `sections` do termo (vazio = toda a secção, como antes); validada (pergunta existe e está numa secção do termo); fora do hash da metodologia (onde aparece não é conteúdo). **v0.1.87 (4 Out 2026, D8):** capacidade `quality` ATIVA (controlo de qualidade mensal da Compliance; por omissão `Intake.Compliance`; `reopen` continua reservada) e `IntakeReviewPolicy.quality` (`IntakeQualityPolicy`: `sample_rate` 0,10 e `sample_min` 5 — amostra dos validados no mês, todos se forem menos do que o mínimo; fora do hash da metodologia). **v0.1.85 (3 Out 2026, B8):** `IntakeDefinition.communications` (`IntakeCommunications`: `invite`, `reminders`, `reminder_days` [3, 7] crescentes, `team_alert_day` 15, `team_alert_emails` — tudo desligado por omissão), `texts.warnings` (`IntakeWarning` por resultado da metodologia: título, texto, Opção A, Opção B — em todas as línguas), `fund` (nome do OIC/fundo); papel por omissão `Intake.Compliance` em `view` e `export` (a capacidade `quality` do D8 continua reservada até haver código). **v0.1.84 (3 Out 2026, análise vs proposta):** `IntakeDefinition.texts` (`IntakeTexts`: `intro`, `privacy` — tomada de conhecimento obrigatória antes da 1.ª resposta —, `declaration` — aceite obrigatoriamente na submissão — e `incomplete_warning`; texto simples até 12 000 caracteres por língua, os que se aceitam têm de existir em TODAS as `languages`; fora do hash da metodologia); `IntakeQuestion.prefill_field` (`name`/`email`/`phone` — que dado do convite se propõe; só com `prefill_from: invitation`); `IntakeReviewPolicy.parallel_run` (execução em paralelo com a matriz antiga: a equipa regista o resultado dela). **v0.1.83 (3 Out 2026, B8):** `IntakeMethodology.fx` (`IntakeFxPolicy`) — câmbio da avaliação: `source` `ecb` (taxas de referência do dia útil anterior à submissão) e `via_usd` (moedas que o BCE não publica, ex. AED/SAR, em unidades por 1 USD — parâmetro aprovado pela Compliance, sem `USD`); dentro do hash da metodologia; sem o bloco não há câmbio. **v0.1.82 (3 Out 2026, B6):** `IntakeDefinition.review` (`IntakeReviewPolicy`) — área da equipa: `roles` (capacidade → app roles; capacidades FECHADAS `INTAKE_CAPABILITIES` = view/create/review/second_review/export, `reopen`/`quality` reservadas e recusadas até existirem), `double_validation` (montante mínimo + moeda, red flags, resultados; mudar o resultado do motor obriga sempre) e `amount_required`; separação de funções fixa no produto (quem cria não revê; 1.ª ≠ 2.ª validação); fora do hash da metodologia. Na mesma versão, `frontend.features.intakeTeam` (rota /equipa do fecore; só mostra — a autorização é dos papéis), `intakeTeamHome` (arranca em /equipa) e `intakeTeamOnly` (só a área da equipa, sem chat); `frontend.features.shareAccess` (`auto`/`public`/`login` — quem abre um link de conversa partilhada). **v0.1.81 (3 Out 2026, B5):** `IntakeDefinition.presentation` (`IntakePresentation`) — só aparência do percurso: `bilingual` (pergunta e opções também na outra das `languages`, por baixo) e `footer` (rodapé legal); fora do hash da metodologia, como `access`. Na mesma versão, `frontend.branding.darkHeaderLogo` (default `True`; `False` = só o nome do cliente nos cabeçalhos escuros do percurso). **v0.1.80 (2 Out 2026, B4):** `IntakeDefinition.access`
  (`IntakeAccessPolicy`) — link pessoal + código a cada entrada: validade do
  link, sessão por inatividade, validade e tentativas do código, códigos
  falhados até bloquear, intervalo e máximo diário de códigos, canais
  (`email`/`sms`). Defaults = decisões do Bruno; tetos impedem desligar a
  proteção. Na mesma versão, **`mcp.servers[].chat`** passa a tipado
  (`bool`, default `True`; `False` = só automações, como o core já lia). As
  forks Salmon e Demos ainda não o declaram (`extra="forbid"`) e serão
  sincronizadas com o base.

- **Nomes de voz validados (v0.1.159, 6 Nov 2026)** — os valores de `frontend.ttsVoiceMap` e `voices.by_locale` têm de ser nomes de voz da Azure (`voice_names.py`: locale + nome, sufixo HD opcional, até 100); vazio fica. Entram no SSML do core e do fecore, que já os saltavam no uso; aqui o save recusa-os. As vozes HD (incluindo as `:MAI-Voice-…`) são permitidas de propósito; o GAIBO é mais restrito e recusa HD no que o cliente grava, por custo. O mesmo padrão vive no core (`ssml.is_valid_voice_name`) e no fecore (`voice-name.ts`).
- **Captura com consentimento na voz (v0.1.112)** — `voice.capture.enabled` (bool, **desligado** por omissão, `_R`): sem ele um turno de voz nunca autoriza a captura; ligado, só no widget GPT-Live, com a pergunta dita palavra por palavra e verificada (core `core/agent/voice_capture_consent.py`). Campos, base legal e finalidade continuam os de `record_contact_details`.
- **Lead → pedido na fila (v0.1.111)** — `tools.config.record_contact_details.queue` (vazio por omissão = só o email): cada captura completa cria um pedido nessa fila (core `core/managers/capture_queue.py`). Interno como o resto do bloco da captura.
- **Resumo da chamada transferida (v0.1.110)** — `voice.transfer_summary_emails` (lista, vazia por omissão, `_W`): para onde o core manda o resumo que o assistente escreve ao passar a chamada a uma pessoa (I21); e `voice.transfer_summary_to_queue` (bool, **desligado** por omissão, `_W`): se a transferência também cria um pedido na fila da voz. Validação dos endereços no consumidor (core e a drenagem do Studio), como os `notify_emails`.
- **Modo da variante (v0.1.124, 17 Out 2026):** `variantMode` na raiz (`None`/`"shared"` = Partilhada, o merge DEFAULT + base + variante de sempre; `"separate"` = Separada, o genai-core funde só DEFAULT + variante, sem nada do principal). Só conta no blob de uma variante; `None` por omissão (um `null` gravado vale Partilhada) e `internal` (só o Studio o escreve). O consumo no core e no Studio é a fase B das autenticações por variante (pack das variantes §13.11).
- **Login: `stepUp` e teto de emissores (v0.1.125, 18 Out 2026, ponto 0 das variantes):** `frontend.auth.stepUp` (bool, `False` = o de sempre; lido só pelo genai-core; `internal`) declarado; `frontend.auth.providers` com no máximo `MAX_AUTH_PROVIDERS` = 64 (o D5 do Studio aceita 50 tenants, mais os outros emissores; o fecore guarda a impressão de até 128 hashes e acima disso desliga a guarda); o comentário da `audience` diz a verdade (vazia → o core ignora o emissor).
- **Equipa e papéis do produto (v0.1.114, `team.py`)** — bloco `team` (só o BASE conta; None = desligado): `enabled`, `modules` (interruptores approvals/queues/intake/docver/variant_access — desligado = como hoje), `roles[]` (`id`, `label`, `capabilities` do catálogo `CAPABILITIES`, com alvo opcional `queue.operate:<fila>`/`actions.approve:<regra>`, e `entra.{roles,groups}` em Avançado). `role_templates(módulo)` dá os papéis prontos; `team_problems`. **v0.1.120 (16 Out 2026):** `team_areas(base, variants)` — as áreas que o cliente TEM, calculadas do perfil, nunca escolhidas à mão: fila (`frontend.features.reviewQueue`), aprovações (`actionRules.enabled` com regra `approve`), Intake (definições no base), Casos (`verify_documents`), frentes (`multiProfile` com variante ativa); cada uma com `managed` (a equipa gere-a). Novo papel pronto «Intake — Auditor» (ver + documentos), o par do `Intake.Auditor` do Entra. **v0.1.121 (16 Out 2026):** `ProfileTeam.entry` (`anyone` por omissão / `team`): quem pode usar o assistente — com `team`, só a equipa (o genai-core recusa os outros logins). **v0.1.122 (16 Out 2026, F2):** três áreas novas — CVs (`cv`, `analyse_cv`), Atas (`minutes`, `transcribe_audio`) e Ferramentas de documentos (`documents`, `extract_invoice`/`generate_boq`) — com `cv.use`/`minutes.use`/`documents.use` e os papéis prontos Recrutador, Utilizador de atas e Utilizador de documentos (dão-se por frente); e «Ver a fila» (`queue.view`, alvo opcional por fila; quem trata também vê) com o papel «Consulta da fila». As ajudas das capacidades cabem no popover de 240 caracteres do GAIBO (teste); o detalhe de operador vai para a `note` dos `team.modules.*`. As PESSOAS e o âmbito por frente vivem no genai-core. Tudo `_W` (o cliente configura no GAIBO). **v0.1.123 (16 Out 2026):** `ProfileTeam.insights_phase2` (bool, `False`, `internal`): liga a fase 2 da «Saúde da equipa» no genai-core (ativação dos convites, aprovações «a carimbo», separação de funções, acessos negados em contagens); só a Genesis, depois de o DPO validar; desligado, o core nem regista os acessos negados.
- **Pedidos MCP assinados (v0.1.154, 4 Nov 2026, I3 do épico «Agente colega»)** — `mcp.servers[].signing` (`ProfileMCPSigning`, `extra="forbid"`: só `enabled`, por omissão `None` = desligado; `_I`): o genai-core assina cada POST a esse servidor (RFC 9421, ES256 com a chave do cliente) e, com um agente a agir, leva `Genesis-Agent`/`Genesis-Mission` assinados. Ordem de rollout do `read_tools`: só num core que anuncie `mcp_request_signing`; desligado = omitir a chave; as forks não o conhecem.
- **Filtro por categoria de documento é opt-in (v0.1.162, 11 Nov 2026)** — `retrieval.category_filter` (bool, `False`, interno, passo «De onde vem o conhecimento» do percurso `retrieval`). Desligado, o genai-core não oferece o filtro `document_category` ao LLM nem o herda da mensagem; ligar só em índices cujas categorias são pastas do cliente — na frota medida eram rótulos de tema do LLM e uma frase comum escondia quase todo o índice.
- **O dump de `mcp.servers[]` não escreve valores por omissão (v0.1.161, 8 Nov 2026)** — `chat` (True), `read_tools` (vazio), `trusted_data` (≠ True) e `signing` (desligado) só saem do `model_dump`/`to_blob_dict` quando não têm o valor por omissão, exatamente como o `MCPServerConfig` do genai-core. Antes, qualquer gravação pelo `/admin/profile/save` escrevia `"chat": true, "read_tools": [], "trusted_data": false` em todos os servidores (medido na Indaqua dev), e um core anterior a um destes campos (`extra="forbid"`) recusava a config MCP inteira numa promoção ou rollback. ⚠️ Os blobs já gravados com o pin antigo ficam com as chaves até serem regravados por um core já na v0.1.161.
- **Registo durável das ações (v0.1.115, `action_ledger.py`)** — bloco `actionLedger` (só o BASE; None = desligado): `enabled`, `retention_days` (365 por omissão, 180–3650). `ledger_policy(perfil)` é a regra ÚNICA `{on, required, retention_days}`: alto risco (`classification.risk_level == "high"` ou `high_risk.enabled`, a mesma regra do core) regista SEMPRE, falha fechada e usa `high_risk.log_retention_days`. A cadeia vive aqui para o core (escreve) e o Studio/GAIBO (verificam) fazerem a MESMA conta: `EVENTS`, `CHAIN_FIELDS` (lista fechada; NADA pessoal em claro — valores e identidades entram como `salted_digest` com sal por entrada, guardado na parte apagável `ERASABLE_FIELDS` = params/salt/who; apagar tira o sal e o digest deixa de se ligar à pessoa, EDPB 02/2025), `entry_hash`, `verify_chain` (diz em que `seq` parte: hash, elo ou entrada em falta). Apagar os valores por RGPD não parte a cadeia. **v0.1.131:** evento `checked` — a releitura do sistema depois de uma escrita (A2 do core agêntico), `result.code` = `verified`/`unverified`/`contradicted`, `ok` False só numa contradição.  **v0.1.132:** evento `withdrawn` — o pedido de aprovação pendente retirado por quem pediu (`approver` vazio) ou por um operador ao parar a tarefa (`approver` = «studio»). **v0.1.153 (4 Nov 2026, I2 do épico «Agente colega»):** cadeia v2 — `CHAIN_V = 2`, `CHAIN_FIELDS_V2` = v1 + `chain_v` + `mission_s256`; `entry_hash` escolhe os campos pela versão DA ENTRADA (`chain_fields`; sem `chain_v` = v1, outra = `UnknownChainVersion` → `verify_chain` diz `unknown_chain_version`), por isso as cadeias já escritas e as mistas verificam; `mission_s256(bytes)` (SHA-256 em base64url, AAuth) e `MISSION_S256`. A lista v1 NUNCA muda. **v0.1.155 (5 Nov 2026, passo 5A do «Agente colega»):** cadeia v3 — `CHAIN_V = 3`, `CHAIN_FIELDS_V3` = v2 + `effect_digest` (o efeito que o sistema devolveu a uma escrita: n.º da encomenda, da fatura) + `why_digest` (a justificação do agente), ambos `salted_digest` com sal próprio; valor e sal na parte apagável (`ERASABLE_FIELDS` ganha `effect`/`why`); `effect_norm` (texto curto, só dígitos sem zeros à esquerda) é o que entra no digest e o que a pesquisa por efeito compara; `CHAIN_FIELDS_ALL` = os campos de TODAS as versões, a usar em qualquer leitura com projeção (verificar, provar). **v0.1.156 (5 Nov 2026, passo 5A):** `witness_sealed` (`_I`, só a Genesis) — «Testemunha selada»: as cópias dos carimbos no contentor `ledger-witness` do storage do cliente (só em produção) ficam em modo «Locked» até ao fim do prazo (ninguém as apaga, nem a Genesis; o storage do cliente só se apaga depois e o desmantelar fica bloqueado até lá); desligado = «Unlocked» (quem tem a chave da conta pode retirar a proteção). `witness_sealed(perfil)` é a regra pura (só `True` exato no BASE). **v0.1.158 (5 Nov 2026):** `timestamping` (`_I`, só a Genesis) — o carimbo temporal RFC 3161 do carimbo diário: `public` (TSA pública, grátis, não qualificada) | `qualified` (qualificada eIDAS; a TSA escolhe-a o core, num catálogo fechado) | `off`; None/null/desconhecido = `public` (`timestamping_mode(perfil)`, só o BASE, `TIMESTAMPING_MODES`). Nenhum URL nem credencial no perfil. `_W`.
- **Cadeia v4 do registo (v0.1.158, 5 Nov 2026, contrato 222)** — `CHAIN_V = 4`, `CHAIN_FIELDS_V4` = v3 + `provenance_digest` (de onde vieram os valores sensíveis de uma escrita do agente, `salted_digest` com sal próprio; o registo e o sal na parte apagável, `ERASABLE_FIELDS` + `provenance`). `provenance_record` é a forma FECHADA do registo (`{v, outcome: logged|approval|blocked, findings: [{param, kind, origin: untrusted|unknown, masked, sources}]}`, ≤ 20 achados, sem controlos) — o core grava-a, o verificador independente e o Studio leem-na. As cadeias v1–v3 e as mistas continuam a verificar.
- **Intake ↔ contacto (v0.1.116, C6)** — `contacts.link_intake` (falso; `_I`; no bloco `contacts`, que aceita extras — o `intake` é fechado e um core antigo recusaria o perfil): os processos do Intake guardam a referência ao contacto da pessoa (identidade DECLARADA, nunca funde) e entram na linha temporal.
- **Limites por período (v0.1.116, F4)** — `actionRules.rules.period_limits[]` (até 5): `period` day/week/month (calendário no fuso `identity.timezone`, semana seg–dom), `per` user/client, `max` (≥0), `sum_param` (vazio = contar ações; senão soma o campo), `currency`, `over` (block por omissão). Conta o que foi FEITO; contagem ilegível = falha fechada (o `over`). Problemas `invalid_period_limit`, `too_many_period_limits`. `_W`.
- **Resposta corrigida depois do 👎 (v0.1.117, I35)** — `frontend.features.showFeedbackResolution` (falso; `_W`): o fecore marca as respostas da conversa cujo report foi resolvido (`GET /conversations/<id>/feedback-resolutions` do core, só o dono).
- **Descarregar os meus dados (v0.1.117, I36)** — `frontend.features.enableDataExport` (falso; `_W`): o fecore mostra a quem tem login o descarregar do ficheiro com as conversas, a memória e os pedidos (`GET /user/data-export` do core).
- **Telefone com login obrigatório (v0.1.118)** — `voice.agent.phone_when_login_required` (falso; `_I`): a ponte do telefone entra no `/completions` com a chave interna e quem liga é sempre anónimo; desligado, o 401 de sempre (o telefone diz que não consegue consultar).
- **Áudio das reuniões (v0.1.144, 3 Nov 2026, M2/R5 do épico «Reuniões e atas»)** — `audio.meeting_audio_retention_days` (30 por omissão; 0 = não se guarda; teto 180; `_R`, `requires_tool: transcribe_audio`): dias que o áudio de uma reunião gravada no espaço «Reuniões» fica em `upload/meeting-audio/` para a diarização no fim e os excertos do ecrã «quem fala». Vale o MENOR entre ele e a retenção das atas; quem apaga é a regra `expire-meeting-audio` do Studio e o core.
- **Atas → pedidos (v0.1.118, I30)** — `audio.minutes_action_items_queue` (vazio por omissão = desligado; `_I` como a fila da captura e o `reviewQueues`; `requires_tool: transcribe_audio` + `requires_field: reviewQueues`): a fila onde o dono da ata transforma as ações combinadas em pedidos, escolhendo quais (core `core/managers/minutes_queue.py`). Fila inexistente = desligado; o responsável fica como texto, nunca como atribuição.
- **O que vem junto com o create_ticket (v0.1.119, auditoria D3/D10)** — `tools.config.create_ticket.status_lookup` (`check_ticket_status`, I19) e `.no_info_offer` (chip do «não sei», I20), `Optional[bool]`: None/ausente = ligado com a tool (o que os clientes que já a tinham veem), `false`/`true` explícitos mandam; o Studio grava `false` nos clientes novos e ao criar o bloco. Dentro do `tools.config` (mapa aberto gravado byte-fiel): a chave nunca se materializa como `null` num perfil antigo.
- **Aprovação por outra pessoa (v0.1.113)** — `actionRules.rules.approval`: `roles` (app roles) e/ou `groups` (object ids) do Entra — pelo menos um —, `expires_hours` (24, 1..720) e `notify_emails` (até 10), todos `_W`. `approval_queue_template()` é a máquina de estados que o core reconhece (pending → approved/rejected/expired) e o Studio cria; `approval_queue_shape_ok`. **v0.1.132:** estado final `withdrawn` e ação `withdraw` (só de `pending`) no template; `approval_queue_with_withdraw` acrescenta-os, numa cópia, a uma fila criada antes (o core fá-lo ao ler — o perfil não se regrava) e `approval_queue_can_withdraw` diz se a fila os tem com a forma certa; o `shape_ok` continua a aceitar as filas antigas. Problemas novos `approve_without_approvers`, `invalid_approver`, `invalid_notify_email`, `approval_queue_shape`.
- **Regras por ação do agente (v0.1.109, `action_rules.py`)** — bloco `actionRules` (`enabled` + `rules[]`: `id`
  estável, `action` = `<servidor>.<tool>` ou tool nativa, `mode` allow/confirm/approve/block, `limits[]` com
  `param`/`op`/`value`/`currency`/`over`, `approval.queue`, `variants`, `log_only`, `note`). Editável pelo cliente
  (fora de `mcp.*`); desligado = comportamento de hoje. `action_rules_problems(profile)` cruza com o resto do perfil
  (fila que existe, servidor `per_user` recusado para aprovar, servidor desaparecido assinalado) e nunca levanta.
  Os mínimos de segurança vivem no core, não aqui.
- **Valores de origem não confiável (v0.1.158, 5 Nov 2026, contrato 222)** — `actionRules.untrusted_values.mode` (`off`|`log`|`approve`, `_R`; ausente/null = `log`, desconhecido = `approve`: `untrusted_values_mode`) e `actionRules.rules[].sensitive_params` (≤ 20 caminhos, `_W`; `sensitive_params_of`). Problemas: `invalid_sensitive_param`, `invalid_untrusted_mode` (erros) e `untrusted_blocks_without_approval` (aviso: com `approve`, uma regra de conector permitir/confirmar sem fila e aprovadores bloqueia a escrita do agente com um valor não confiável). O core usa a fila e os aprovadores da regra mesmo com modo «permitir».
- **Mensagens de suporte do GAIBO (v0.1.141, `gaibo_index/support_messages.py`)** — `SupportMessage` (GAIBO, em
  `support-messages/`, escrita uma vez: remetente com email = Reply-To e `kind` membro/Suporte Genesis, `locale`,
  assunto numa linha ≤ 120 sem controlo, separadores de linha Unicode nem Cf/Co, descrição ≤ 2000 só com LF/TAB e
  sem inversão bidirecional) e `SupportMessageResult` (Studio, em `support-message-results/`, If-Match:
  `pending|sent|failed|invalid` + `reason_code` + `reason` ≤ 300 + `sent_at`); `SUPPORT_MESSAGES_PER_HOUR` (20).
  O Studio envia o email para a caixa de suporte da Genesis; a condição ABAC da API passa a incluir
  `support-messages/`. Os prefixos não se cobrem (`StringStartsWith`). Contrato 201.
- **`GaiboSettings.auto_approve` ligada por omissão (v0.1.141)** — decisão de 31 Out 2026; as definições já
  gravadas trazem o valor explícito e não mudam.
- **Documentos do GAIBO apagados pela Genesis (v0.1.138, `gaibo_index/removals.py`)** — `GenesisRemovalNotice`
  (Studio, em `genesis-removals/` da caixa do dev, `If-None-Match: *`, nunca reescrito): `environment` dev/prod,
  `source_file` só do GAIBO, `origin_ref` da execução apagada, chunks, original removido; `is_valid_notice_id`,
  `removal_blob`. O GAIBO só lê: dev → removido pela Genesis (sai da capacidade, não do limite mensal); prod →
  «não publicado». Contrato §3.
- **Convites da Equipa do GAIBO (v0.1.108, `gaibo_index/invites.py`)** — `InviteRequest` (GAIBO, em
  `invites/`) e `InviteResult` (Studio, em `invite-results/`) na caixa de saída; `normalize_email`,
  `is_valid_invite_id`, `INVITES_PER_HOUR`. O Studio convida para o tenant do cliente (nunca o da Genesis); a
  condição ABAC da API do GAIBO passa a incluir `invites/`. Contrato §5.1. **v0.1.109:** `reason_code` ganha
  `sending`/`duplicate`/`expired`/`uncertain` (o executor do Studio usa-os — a v0.1.108 recusava-os) e o `display_name`
  recusa invisíveis Cf/Co (U+202E, largura zero).
- **Contrato da indexação pelo GAIBO (v0.1.92, `gaibo_index/`; v0.1.101: limite mensal com desbloqueio, recursos do cliente para indexar e planos `demo`/`pilot`/`internal`; v0.1.102: `di_model` por plano — Read no Starter/Demo, Layout nos restantes, via `extraction_for()` — e Enterprise ligado sem limites; v0.1.103: ação `reindexed` fora do limite mensal, `settings_missing_keys`/`REQUIRED_SETTINGS_KEYS`, validadores `is_valid_origin_ref/request_id/run_id` e as regras de apagar com o cliente desligado e de substituir acima da capacidade; v0.1.143: `RunDocument.uploaded_by_ref` opcional — quem carregou o documento no GAIBO, referência opaca).** O formato de um
  chunk do GAIBO no índice dev (`origin`/`origin_ref`, `source_file` =
  `gaibo/<chave>/<nome>`, ids `gaibo_`, o JSON `metadata` que o core lê) com
  `chunk_problems()`, e a caixa de saída GAIBO↔Studio (`settings.json`, pedidos de
  publicação por manifesto, resultados, relatórios de custo). Não é um perfil: é a
  costura partilhada pelo GAIBO, pelo Studio e pelo core. Documento legível em
  `docs/contrato-indexacao-gaibo.md`. **v0.1.96:** `GaiboSettings.dev_core_url`/`prod_core_url` (origem
  `https://<host>` do core dev e prod do cliente; prod vazio até à promoção).

---

## O que NÃO existe aqui

- **Autorização.** `exposure.py` é declaração de intenção do contrato, não um
  portão. Cada consumidor mantém o seu — o backoffice do cliente continua a
  precisar do default-deny local, porque uma montra não deve depender só do
  upstream para não expor um campo.
- **Validação de valores para lá do Pydantic.** Em aberto e conhecido:
  `product_identification.patterns` são regex do cliente executadas do nosso
  lado, sem limite de complexidade (ReDoS), e
  `frontend.widget.allowed_origins` não valida formato de origem.
- **Classificação por cliente.** A tabela é do PRODUTO, igual para toda a frota.
  Se um dia houver override por cliente, só pode ESTREITAR o que a tabela
  permite, nunca alargar.
- **Consumo do `exposure`/`ui_text` pelos backoffices.** O gaibo já consome
  ambos do pacote (`field_text.py`, `upstream_exposure.py`); o Studio usa o
  `exposure` na baseline e o `ui_text` nos espaços de valores, mas as hints do
  editor continuam locais.
- **O lint de `custom_instructions`.** O registo de regras e o corte de
  playbooks estão aqui (camada 8); a chamada ao juiz LLM e o ecrã são do
  consumidor. O gaibo só vê o registo depois de re-pinar.
