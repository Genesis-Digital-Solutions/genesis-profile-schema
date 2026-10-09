# Contrato da indexação pelo GAIBO — v1

**Versão do pacote:** `genesis-profile-schema` v0.1.92 · **Código:** `genesis_profile_schema/gaibo_index/`
**Responde a:** BACKLOG gaibo 3.1302 (desenho de 3 Out 2026) e às perguntas de 6 Out 2026.

As regras deste documento estão também em código, no pacote. **Em caso de dúvida, manda o código**
(`index_fields.chunk_problems()` e os modelos de `outbox`). Os dois lados importam o mesmo pacote:
o GAIBO para escrever, o Studio para se proteger e para validar o que publica, o core para mostrar as fontes.

---

## 1. O modelo

- **Recursos:** o GAIBO usa só os recursos do cliente (Document Intelligence, Azure OpenAI, Storage e AI Search).
- **Onde escreve:** no **índice dev** do cliente, o mesmo que o Studio enche. O nome do índice, do serviço de pesquisa
  e do modelo de embeddings vêm no `settings.json` da caixa de saída (§5). Não se leem do índice: nos índices
  migrados da plataforma antiga não há a sentinela `genesis_meta`.
- **Produção:** só o Studio escreve no índice de produção, a pedido do GAIBO e com aprovação da Genesis.
- **Comunicação:** o GAIBO e o Studio nunca se chamam. Falam pela caixa de saída na storage do cliente.
  O genai-core não entra neste circuito.

## 2. Um chunk do GAIBO no índice

| Campo | Regra |
|---|---|
| `id` | `gaibo_` + md5(`"<source_file>_<page>_<chunk_index>"`) → `chunk_id()`. Determinístico: a mesma versão do documento gera os mesmos ids. |
| `source_file` | `gaibo/<chave>/<nome original>` → `source_file_for()`. A **chave** é estável por documento (sobrevive às substituições do ficheiro): `j-` + 8 a 26 caracteres base32 minúsculos (`a-z`, `2-7`). Sem 0, 1, 8 e 9, nunca forma um "ano" (o core e o modelo leem anos nos caminhos). |
| nome original | Até 200 caracteres, em Unicode NFC, sem `/`, `\`, `%`, caracteres de controlo, invisíveis ou de direção, e sem acabar em ponto → `file_name_problems()`. **Os ids derivam do `source_file` completo:** substituir o ficheiro com o mesmo nome mantém os ids; mudar o nome é uma identidade nova (remover + publicar). |
| `origin` | `"gaibo"`. É um campo novo, filtrável. Ausente significa Studio. |
| `origin_ref` | A referência opaca da **execução** que produziu os chunks (`[A-Za-z0-9_-]{1,64}`). Nunca o utilizador. |
| `document_title` | Obrigatório e legível. É o que o utilizador vê na citação; sem ele aparecia o caminho. |
| `url` | Absoluto, `https://<conta>.blob.core.windows.net/gaibo-sources/...`, **codificado como o SDK o devolve** (`blob_client.url`: espaços e `%` codificados), sem query (**nunca um SAS**: quem assina é o core) e só com o fragmento `#page=N` nos PDF. O contentor `gaibo-sources` vive na **conta de storage do core do dev** do cliente: noutra conta o core não assina e o link dá 403. |
| `parent_doc_id` | `doc_` + md5(`source_file`)[:16] → `parent_doc_id()`. |
| `page` / `global_chunk_index` | Inteiros, **no topo e no `metadata`** com o mesmo valor. `global_chunk_index` é sequencial por documento, a partir de 0: o core expande aos chunks vizinhos filtrando pelos campos de topo. |
| `metadata` | **Obrigatório**: JSON de um objeto (ver abaixo). |
| `content` / `enriched_content` / `content_vector` | `content` = texto limpo. `enriched_content` = o mesmo texto com os marcadores de enriquecimento no início (`[Contexto: …]`, `[Perguntas prováveis: …]`). O vetor é calculado sobre o `enriched_content`. |
| `doc_version` | **Obrigatório:** sha256 (hex minúsculo) dos bytes do original. A publicação recalcula-o sobre o original copiado para produção e recusa a entrada se não bater: o original tem de ser o que os chunks descrevem. Conta também para a evidência do Anexo IV. |

**O JSON `metadata` é o que o core lê.** O core não usa os campos de topo no caminho principal:
um `metadata` nulo ou inválido parte a pesquisa desse índice. Tem de trazer `source`, `page`, `url`,
`document_title`, `document_type`, `parent_doc_id`, `global_chunk_index` e `origin`, com os **mesmos
valores dos campos de topo**. `metadata.source` tem de ser igual a `source_file` byte a byte: o core agrupa
as citações e filtra a expansão por esse valor.

**Proibido:**
- campos fora de `GAIBO_WRITABLE_FIELDS`, como visão, `document_category`, `migrated_*` ou `tier`. O `tier`
  punha os documentos do GAIBO à frente dos do Studio;
- `content_type` `dataset_catalog` ou `dataset_vocabulario`, que mandariam o core para tabelas que não existem;
- os ids `genesis_meta` e `__meta__`.

O `metadata` é serializado como JSON normal (`json.dumps`), sem escapar as barras (`\/`): a publicação reescreve a conta
de storage dentro dele e não reconhece um URL escapado.

Antes de enviar um lote, `chunk_problems(doc)` tem de devolver uma lista vazia.

**Extração e corte** (constantes `EXTRACTION_BY_EXTENSION` e `CHUNKING`):

| Tipo de ficheiro | Extração |
|---|---|
| PDF, PPTX, XLSX e imagens | `prebuilt-layout` |
| DOCX | `prebuilt-read` |
| TXT e MD | texto direto |

- **Diferença face ao Studio (intencional):** o Studio extrai com `prebuilt-read` e acrescenta Vision. O GAIBO
  não tem Vision, e o Layout compensa nas tabelas. O custo por página é maior.
- **Texto:** blocos de 512 tokens, com sobreposição de 100.
- **Tabelas:** cada tabela fica num bloco próprio de até 2000 tokens. Acima disso, é partida com sobreposição de
  300 tokens e o cabeçalho repetido em cada pedaço. São as mesmas regras do Studio.

## 3. Substituir e apagar no dev

- **Substituir um documento:** mesma chave, nova execução. O GAIBO apaga os chunks antigos dessa `source_file`
  (só `origin eq 'gaibo'`) e escreve os novos com o novo `origin_ref`.
- **Âmbito:** o GAIBO só lê, conta, substitui e apaga documentos `origin eq 'gaibo'`. Mesmo nome de ficheiro que
  um documento do Studio não colide: as identidades são diferentes, e o GAIBO não avisa disso.
- **Índice dev recriado:** se o Studio recriar o índice (por exemplo, ao mudar o modelo de embeddings), os
  documentos do GAIBO desaparecem. O GAIBO deteta-o pela mudança de `dev_index_generation` no `settings.json` e
  volta a indexar a partir dos originais.

## 4. Publicação em produção — por manifesto

O pedido diz **o quê**, não só **quando**.

1. **O GAIBO escreve `requests/<pr-…>.json`** (`PublishRequest`, escrito uma vez com `If-None-Match: *`).
   - `client_id` é o id do cliente de **dev** no Studio (`<projeto>-dev`, por exemplo `genesis-ai-dev`). Outro valor
     torna o pedido `invalid`.
   - Cada entrada é `publish` ou `remove`.
   - Uma entrada `publish` leva o `origin_ref` e o `chunk_count` que o cliente aprovou no dev.
2. **O Studio responde em `results/<pr-…>.json`** (`PublishResult`). O primeiro estado é `pending_approval`.
   A Genesis aprova ou recusa no Studio, com motivo. Por cliente, a aprovação pode ser automática (`auto_approve`).
3. **Antes de copiar, o Studio confirma no dev, entrada a entrada:**
   - que existem exatamente `chunk_count` chunks dessa `source_file` com `origin='gaibo'`;
   - que todos têm esse `origin_ref`;
   - que todos passam `chunk_problems()`.
   Se algo não bater, a entrada fica `mismatch`, `not_in_dev` ou `invalid` e **não é publicada**.
   Ao republicar um documento, os chunks que já estavam em produção e não fazem parte da nova versão são apagados
   depois de a nova versão ter subido.
4. **Remoções:** só as entradas `remove`, só documentos `origin='gaibo'` em produção. **Nada sai de produção por
   estar ausente do dev.** Uma re-indexação a meio de uma publicação deixa entradas por publicar, nunca apaga.
5. **O resultado diz por entrada o que ficou em produção:**
   - o `outcome`, com o `origin_ref` e o número de chunks copiados;
   - o `dev_checked_at` (o momento em que o dev foi lido) e o `published_at`.
   O GAIBO marca como publicado só o que vier `published` ou `removed`.
6. **Cópia:** os chunks vão tal como estão no dev (texto e vetores). O resto do dev nunca é copiado. O dev e a
   produção têm contas de storage diferentes: o Studio copia também o **original** de `gaibo-sources` do dev para o
   `gaibo-sources` de produção e reescreve o `url` (topo e `metadata`) para a conta de produção. Numa remoção apaga o
   original de produção. A sincronização geral do Studio ignora os documentos do GAIBO nos dois sentidos: não os
   copia e não os apaga.

Estados de `PublishResult.status`: `pending_approval`, `approved`, `publishing` (já em execução; nunca volta a
`approved`), `refused`, `published`, `partially_published`, `failed` e `invalid` (pedido que não valida contra o
modelo).

**A decisão vive no Studio.** O estado autoritativo de cada pedido (aprovado por quem, executado ou não) e as
definições de cada cliente guardam-se do lado do Studio. O `results/` e o `settings.json` são o espelho que o GAIBO
lê: o que outro escritor lá puser é ignorado e reescrito. Uma remoção e uma publicação da mesma chave no mesmo pedido
(mudança de nome) executam primeiro a remoção.

## 5. Caixa de saída

Contentor `gaibo-outbox`, privado, na storage do cliente:

| Caminho | Escreve | Modelo | Escrita |
|---|---|---|---|
| `settings.json` | Studio | `GaiboSettings` | `If-Match` |
| `requests/<pr-…>.json` | GAIBO | `PublishRequest` | `If-None-Match: *` |
| `results/<pr-…>.json` | Studio | `PublishResult` | criado com `If-None-Match: *`, depois `If-Match` |
| `runs/<run-…>.json` | GAIBO | `RunReport` | `If-None-Match: *` |

**`settings.json`:**
- `enabled` vem a `false` por omissão.
- Traz também `auto_approve`, os limites efetivos do cliente (`max_documents`, `max_total_mb`, `max_file_mb` e
  `allowed_extensions`), o serviço de pesquisa, o índice dev, o deployment de embeddings e as dimensões.
- Os valores por tier (`TIER_DEFAULTS`) são provisórios e só servem de ponto de partida no Studio.
- **Enterprise:** desligado por omissão. A indexação é feita pela Genesis, que a pode ligar (sem limites)
  se o contrato o pedir.
- Os limites contam só os documentos `origin='gaibo'`.
- **URLs do core (v0.1.96):** `dev_core_url` (core DEV do cliente — o teste de pesquisa antes de publicar) e
  `prod_core_url` (core de produção — o backoffice depois da promoção). Só a origem `https://<host>`, sem
  caminho, query nem fragmento (a barra final é retirada); vazio = desconhecido. O `prod_core_url` fica vazio
  até à promoção e, enquanto estiver vazio, o GAIBO esconde a publicação.
- **Chave de administração do core:** é o segredo `BACKEND-API-KEY` do core, lido do Key Vault de CADA ambiente
  (dev e prod) com o papel Key Vault Secrets User com âmbito nesse único segredo. Nunca vem no `settings.json`.

**Índice dev recriado:** o `dev_index_generation` do `settings.json` muda sempre que o índice dev é recriado,
mesmo com o mesmo nome e o mesmo modelo. Quando muda, o GAIBO volta a indexar a sua parte a partir dos originais.

**Limite mensal e desbloqueio (v0.1.101).** Além da capacidade (documentos e MB vivos ao mesmo tempo), há um
limite de **documentos indexados ou substituídos por mês civil** (UTC), `max_documents_per_month`, que o GAIBO
conta a partir das suas execuções (`runs/`): as entradas `indexed` e `replaced` de cada `RunReport` contam no mês do
seu **`started_at` (UTC)**, e o Studio conta da mesma forma (uma execução que atravessa a meia-noite de dia 1 conta
no mês em que começou):
- avisa o cliente a 70% e a 90%;
- a 100% recusa novas indexações até ao dia 1 (apagar continua a funcionar);
- se o cliente pedir, a Genesis desbloqueia no Studio: `extra_documents` documentos a mais, válidos só no mês
  `extra_documents_month`, a seguir caducam sozinhos. O total do mês é `monthly_allowance(mês)`;
- `null` = sem limite (por exemplo, o plano `internal`).

**Recursos do cliente para indexar (v0.1.101).** O `settings.json` traz também `aoai_endpoint`, `di_endpoint` e
`enrichment_deployment`, preenchidos pelo Studio a partir do dev do cliente. O Document Intelligence é **sempre**
o AI Services do próprio cliente, nunca um recurso central da Genesis.

**Planos.** Os valores por omissão de cada plano estão em `TIER_DEFAULTS`: `starter`, `professional`,
`enterprise` e, desde a v0.1.101, `demo` (como o Starter), `pilot` (como o Professional) e `internal` (sem
limites, só em ambientes da Genesis). O plano de cada cliente é definido apenas no Studio.

**`runs/`:** um relatório por execução, com o custo real — páginas Read e Layout em separado, tokens de
enriquecimento (entrada e saída) e tokens de embeddings.

Um ficheiro que não valide contra o modelo é tratado como inválido e reportado, nunca saltado em silêncio.
Todas as datas levam fuso (ISO 8601 com `Z` ou `+hh:mm`); uma data sem fuso é inválida.

## 6. Acessos

| Identidade | Papel | Âmbito |
|---|---|---|
| API do GAIBO | Search Index Data Reader | índice dev |
| API do GAIBO | Storage Blob Data Reader | contentor `gaibo-outbox` |
| API do GAIBO | Storage Blob Data Contributor, **com condição** (ABAC) que só permite escrever em `requests/` e `runs/` | contentor `gaibo-outbox` |
| Indexador do GAIBO | Search Index Data Contributor | **só** o índice dev |
| Indexador do GAIBO | Reader | serviço de pesquisa (lê a definição do índice) |
| Indexador do GAIBO | Storage Blob Data Contributor | contentor `gaibo-sources` |
| Indexador do GAIBO | Cognitive Services User | Document Intelligence do cliente |
| Indexador do GAIBO | Cognitive Services OpenAI User | Azure OpenAI do cliente |

- **Nenhum acesso** ao índice de produção.
- **Nenhuma chave:** em particular, nunca a chave de administração do AI Search que está no Key Vault do
  cliente, que dá escrita em todos os índices.
- **Autenticação no AI Search:** passa a «chaves e RBAC», porque o core continua a usar chaves.
- **Contas de storage:** o dev e a produção do cliente têm contas diferentes. O Studio recusa publicar se forem a
  mesma (uma remoção apagaria o original do dev).

## 7. O que o core faz com estes documentos

- **Nome mostrado:** o core mostra o nome do ficheiro sem `gaibo/<chave>/` (`display_name()`), ao modelo e ao
  utilizador.
- **Assinatura dos links:** num chunk do GAIBO, o core só assina links do contentor `gaibo-sources`. Os contentores internos do core (anexos das conversas, exportações e semelhantes) nunca são assinados como fonte de conhecimento, venha o chunk de onde vier.
- **Prioridade de fontes por caminho:** num cliente com a estratégia `path`, os documentos do GAIBO contam como
  externos, a menos que o perfil inclua `gaibo/` nos `internal_markers`. É uma decisão por cliente.
- **«Última versão» por caminho:** num cliente com `latest_version` por caminho (pastas de ano e de família), os
  documentos do GAIBO não têm essas pastas e ficam fora dessas perguntas. Também é por cliente; valida-se no Agent
  Tester antes de ligar a funcionalidade nesse cliente.
- **Agent Tester:** os testsets gerados a partir do índice podem incluir chunks do GAIBO. Depois de substituições do
  GAIBO, regeneram-se.
