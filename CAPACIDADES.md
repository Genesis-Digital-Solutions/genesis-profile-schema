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

## As seis camadas

Um campo do perfil obriga a seis decisões, e cada uma vive num sítio próprio.
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

`control_for(path)` devolve `toggle`, `number`, `select`, `colour`, `url`,
`email`, `date`, `datetime`, `code`, `multiline` ou `text`; `collection_of()`
devolve `list`, `map` ou nada. São duas perguntas separadas de propósito: uma
lista de textos longos é `multiline` + `list`.

**Quase tudo se deriva** do próprio schema — booleanos, números, listas
fechadas e os 57 campos com o `pattern` de cor. A tabela só carrega o que o
contrato não consegue dizer: qual das strings é prosa, qual é código, qual é um
endereço. Há teste a chumbar se a tabela crescer para mais de um quarto das
folhas, e outro a chumbar se um override estiver a repetir o que a derivação já
dava. O padrão das cores é lido do `client_profile_schema`, não copiado.

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
- `regex_risk()` — aviso para as regex de `product_identification.patterns`. O
  core já apanha `re.error`; o que falta lá é limite de TEMPO de execução, e
  isso resolve-se no core, não aqui.
- `looks_like_language_tag()` / `SUGGESTED_LOCALES` — forma BCP-47 e os locales
  com voz de fábrica. **Não há lista fechada de línguas, por desenho**:
  `auto_detect` é multilíngua total e `language.allowed` aceita `["*"]`. E não
  serve para `language.fallback`, cujo valor é uma FRASE para o modelo
  (`"Portuguese (European Portuguese - pt-PT)"`), não um código.

---

## Checklist: acrescentar um campo

1. **Modelo** — o campo em `client_profile_schema.py`, com tipo, default seguro
   e limites. Um perfil vazio validado tem de continuar a ser um perfil
   funcional.
2. **Classificar** — entrada em `EXPOSURE`. Pergunta as duas perguntas, sempre
   as duas: *o cliente precisa de ver isto?* e, separadamente, *pode alterá-lo
   sem partir nada nem contornar um controlo nosso?* Na dúvida, `internal`:
   abrir depois é fácil, fechar depois de o cliente ter mexido não é.
3. **Nomear** — `label` nas duas línguas; `help` se for interruptor ou número
   visível ao cliente; `options` se for lista fechada visível; `note` se houver
   detalhe operacional nosso.
4. **Controlo** — só se o schema não conseguir dizê-lo sozinho: prosa, código
   ou endereço vão a `CONTROL_OVERRIDES`. Tipo, lista fechada e cor derivam-se.
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

129 testes em `tests/` — `test_exposure.py`, `test_ui_text.py`,
`test_presentation.py` e `test_field_checks.py`:

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
- Catálogo em falta devolve vazio em vez de rebentar — texto de interface não
  derruba serviços.

---

## Armadilhas medidas

- **`extra="allow"` em todo o lado.** Uma chave inventada é aceite sem erro. É
  por isso que o Studio tem o `profile_schema_guard.py`; a validação Pydantic
  sozinha não apanha typos.
- **O dialecto dos caminhos.** Índice-free: uma lista de objectos é percorrida
  ao MESMO caminho da lista (`retrieval.indexes.name`). `leaf_paths()` é a
  travessia canónica — havia três escritas à mão, cada uma com o seu dialecto.
  Se precisares de outro dialecto, deriva-o desta.
- **`retrieval.search_index_names` é override total da env.** Não é uma
  afinação de RAG como as vizinhas: escolhe QUE índice o bot consulta.
- **`frontend.csp.*` só actua no rollout do frontend.** O Studio funde as listas
  no `staticwebapp.config.json`; sem novo rollout não há efeito em runtime. Isso
  atrasa a exploração, não a impede — a classificação mantém-se interna.
- **`reviewQueues`**: uma fila referida por um nome ausente deste mapa passa a
  existir como fila fantasma no Cosmos.
- **Os catálogos são dados.** `[tool.setuptools.package-data]` no `pyproject` é
  o que os faz viajar no wheel. Sem essa linha o pacote instala sem os JSON e o
  catálogo fica vazio em produção, em silêncio.

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
- **Consumo do `exposure`/`ui_text` pelos backoffices.** Estão publicados e
  testados; o Studio e o gaibo ainda lêem os seus catálogos locais.
