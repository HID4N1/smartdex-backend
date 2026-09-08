# Current Chatbot Backend Architecture Audit

Audit date: 2026-07-29  
Scope: SmartDex sales chatbot backend only. Adjacent quote/devis code is mentioned where it explains pricing behavior or shared AI patterns. This document now includes the 2026-07-29 state-management remediation notes.

## Executive Summary

The chatbot is a Django REST Framework endpoint backed by a custom RAG pipeline. It stores conversations in the database, retrieves SmartDex knowledge from a local ChromaDB collection, and generates answers with OpenAI `gpt-4.1-mini`.

The current implementation is closer to a generic RAG assistant with sales-flavored instructions than a controlled SmartDex sales consultant. Sales behavior, qualification rules, objection handling, and some pricing rules live mostly in retrievable knowledge documents, not in a high-priority model instruction. Therefore those behaviors only apply when relevant chunks are retrieved.

The biggest pricing issue is source fragmentation and priority ambiguity:

- `pricing_guide.txt` is classified as `doc_type=pricing`.
- `pricing_breakdown.txt` contains important detailed price ranges but is classified as `doc_type=general`.
- For pricing intent, retrieval filters to `doc_type=pricing`, so `pricing_breakdown.txt` is excluded.
- The deterministic pricing engine in `core/pricing/` is not used by the chatbot.
- The model is asked to produce prices from retrieved text, so it can blend incomplete retrieved pricing, prompt rules, and its own language-model priors.

## 2026-07-29 State-Management Fix

The failing showcase-site conversation exposed a state bug, not a prompt wording issue. Before the fix, `BusinessLogicEngine.extract_facts()` built facts from the current message plus recent assistant and user history. The project classifier then matched broad keywords from that combined text. Because SmartDex assistant responses often mention AI services and generic "systems", stale assistant wording could contaminate later turns. Corrections were not represented as first-class events, so an explicit "non" did not invalidate earlier inferred e-commerce or AI values.

Structured conversation state is now persisted on `Conversation.structured_state` and recomputed after every turn. The durable schema separates concepts that were previously blended into generic fact fields:

```python
{
    "language": "fr",
    "industry": None,
    "business_activity": None,
    "legal_structure": None,
    "requested_solution": None,
    "project_type": None,
    "requested_features": [],
    "rejected_features": [],
    "primary_objective": None,
    "service_family": None,
    "complexity": None,
    "last_asked_field": None,
    "asked_fields": [],
    "completed_fields": [],
    "invalidated_fields": [],
    "missing_relevant_fields": [],
    "correction_history": [],
}
```

Extraction now reads the current user message semantically instead of blindly assigning it to `last_asked_field`. For example, if the assistant asks for the activity and the user answers `vitrine`, the extractor records `project_type = "showcase_website"` and leaves `industry` missing. The next question selector can then ask for the industry again because the answer advanced a different field.

Classification rules are deterministic. `vente en ligne` maps to the `online_sales` feature and can drive an `ecommerce` project type while it is not rejected. `site vitrine` and `vitrine` map to `showcase_website`. `réservation en ligne` maps to `booking_feature`, `gestion de flotte` maps to `operational_management_feature`, and AI classifications require explicit AI signals such as `IA`, `intelligence artificielle`, `chatbot`, `assistant intelligent`, `OCR`, `agent IA`, or `machine learning`. Ordinary service words such as `vente`, `site`, `réservation`, `gestion`, `plateforme`, and `système` are not enough to select `ai_solution`.

Corrections are detected deterministically with signals such as `non`, `ce n'est pas`, `je voulais dire`, `seulement`, `juste`, `plutôt`, `pas de`, and `sans`. A correction has priority over previous confirmed values, inferred values, and model guesses. When the user says `non je veux seulement une simple vitrine`, the merge policy invalidates conflicting requested features, records the correction, rejects `online_sales`, `ecommerce`, and `ai_solution`, applies `showcase_website`, and recomputes derived fields.

Derived fields are no longer preserved when source facts change. `recompute_derived_state()` recalculates `service_family`, `project_type`, `complexity`, `completed_fields`, and `missing_relevant_fields` after every meaningful update. This is what prevents a stale e-commerce or AI classification from surviving an explicit correction.

Completed fields are calculated from normalized values plus validation rules. `industry = "cosmetics"`, `project_type = "showcase_website"`, and `legal_structure = "SARL"` are completed independently. Completed values are skipped by the next-question selector unless the user supplies a correction.

Qualification is contextual. A basic showcase website uses relevant fields such as industry, catalogue display, branding/content availability, number of pages, timeline, and budget. Legal structure is captured if the user volunteers it, but it is not a default required field for a simple cosmetics showcase website.

Customer-facing fallback responses are generated from confirmed state only. For showcase websites, wording uses natural labels such as `site vitrine`, `site`, or `projet de site`; raw enum names, package labels, and generic AI/system wording are rejected by validation. The validator also rejects more than one question, premature pricing, AI mentions without AI state, legal-form questions when irrelevant or already completed, e-commerce mentions after rejection, and internal classification leaks.

Regression coverage now includes the exact failing conversation through `/api/chatbot/chat/`. The final confirmed state is protected as:

```python
{
    "language": "fr",
    "industry": "cosmetics",
    "project_type": "showcase_website",
    "service_family": "website_development",
    "requested_features": [],
    "legal_structure": "SARL",
}
```

## 2026-07-29 Pre-Qualification Fix

A later regression showed that a bare greeting such as `Bonjour` entered qualification immediately. The root cause was that deterministic fallback generation treated an empty project state as missing qualification data. Because `industry` was the first missing relevant field, a new conversation could ask for sector, legal structure, budget, or timeline before the user had expressed any project.

The remaining real-runtime bug was in `RAGChain.run()`: the function called `BusinessLogicEngine.analyze()` before the greeting and wait-for-project guard. That meant state recomputation and missing-field selection could be reached before the system had chosen the greeting handler. The fix moved the pre-qualification branch to the top of `RAGChain.run()`:

```python
load_conversation_state()
intent = detect_prequalification_intent(user_message)

if intent == "greeting" and not state.has_active_project:
    return greeting_handler(state)

if intent == "small_talk" and not state.has_active_project:
    return small_talk_handler(state)

if not state.has_active_project and not detect_project_intent(user_message):
    return wait_for_project_handler(state)

run_business_logic()
run_qualification_selector_if_needed()
run_retrieval()
run_llm()
run_validation()
```

For `bonjour`, the runtime now returns before query rewriting, business logic, qualification selection, retrieval, LLM generation, validation repair, or qualification fallback. The response source is `greeting_handler`, and the trace records `qualification_selector_called = False`.

The state machine now has an explicit pre-qualification stage:

```text
START
  |
  v
GREETING
  |
  v
WAIT_FOR_PROJECT
  |
  | detect_project_intent(message) == True
  v
DISCOVERY
  |
  v
QUALIFICATION
  |
  v
RECOMMENDATION
  |
  v
PRICING
  |
  v
LEAD_CAPTURE
  |
  v
HANDOFF
```

`GREETING` and `WAIT_FOR_PROJECT` cannot select qualification questions. The durable state includes `has_active_project`, `prequalification_intent`, and `just_activated_project`. Until `has_active_project` is true, `missing_relevant_fields` is empty and deterministic fallback uses the greeting/general-question handler.

New conversation state is initialized as:

```python
{
    "current_state": "WAIT_FOR_PROJECT",
    "has_active_project": False,
    "project_type": None,
    "industry": None,
    "completed_fields": [],
    "asked_fields": [],
}
```

`select_missing_relevant_fields()` now has a hard guard and raises `QualificationNotAllowed("Qualification cannot run before project intent.")` if called before `has_active_project` is true.

Project intent is detected deterministically from a request phrase plus a project object. Examples that activate discovery include `Je veux un site web`, `Je cherche un ERP`, `Nous avons besoin d'un CRM`, `Je voudrais une application mobile`, `Nous souhaitons automatiser notre entreprise`, `Je veux un chatbot IA`, and `Nous cherchons une solution digitale`. Greetings, thanks, small talk, identity questions, service-list questions, and generic help questions remain in `WAIT_FOR_PROJECT`.

The greeting handler returns the fixed welcome for a greeting-only turn and asks only what the user wants to realize today. It never asks for industry, legal structure, budget, timeline, company size, or project type before project intent exists. Once a project appears, discovery begins with the first relevant question, normally `Quel est votre secteur d'activité ?`.

Validation now rejects premature qualification while no active project exists. If a generated response asks legal structure, budget, timeline, company size, or industry before project intent, the system falls back to the deterministic greeting/general response.

Regression tests now cover:

- `Bonjour` stays in `GREETING` with no qualification fields.
- `Bonjour` then `Merci` stays in `WAIT_FOR_PROJECT`.
- `Bonjour` then `Je veux un site web.` transitions to `DISCOVERY`.
- `Bonjour` then `Quels services proposez-vous ?` answers services and stays in `WAIT_FOR_PROJECT`.
- `Bonjour` then `Je veux un ERP.` starts discovery without pricing or recommendation.
- A brand-new conversation gets fresh structured state and cannot inherit qualification progress.

## 2026-07-29 Duplicate Industry Question Fix

The conversation `Quel est votre secteur d'activité ?` -> `location de voiture` repeated the same industry question because the industry extractor did not recognize car-rental vocabulary. `_detect_industry()` only handled cosmetics, restaurant, and clinic. As a second failure, `calculate_completed_fields()` validated `industry` against the same narrow set, so even a future extracted value such as `car_rental` would not have been considered completed.

The failure was therefore in extraction and completion, not in the prompt. The merge code could only apply fields that extraction returned; since `location de voiture` produced no `industry` update, recomputation left `industry = None`, `completed_fields` did not include `industry`, and `select_missing_relevant_fields()` correctly but undesirably selected `industry` again.

Car-rental normalization is now explicit. These variants map to `industry = "car_rental"`:

- `location de voiture`
- `location automobile`
- `agence de location`
- `loueur automobile`
- `location de véhicules`
- `Auto Rental`
- `car rental`

`INDUSTRY_KEYWORDS` is the source of truth for both extraction and completion validation, so adding a canonical industry in one place keeps the pipeline consistent. A trace helper, `trace_message_processing()`, records incoming message, extracted entities, normalized values, state before merge, merge result, recomputed state, completed fields, missing fields, and selected next field for debugging one-turn state failures.

The selector now asserts that the selected next field is not already completed. The response validator also rejects any outgoing question that asks a completed field or the last completed field unless that field has been explicitly invalidated by correction. This protects against future selector or wording regressions.

## Folder Structure

```text
apps/chatbot/
  views.py                 HTTP endpoint and orchestration
  urls.py                  /api/chatbot/chat/
  serializers.py           request/response validation helpers
  models.py                Conversation and ChatMessage persistence
  tests.py                 placeholder only

core/ai/rag/
  chain.py                 RAG orchestration, intent detection, prompt assembly, OpenAI chat calls
  retriever.py             OpenAI embeddings, Chroma search, lexical fallback
  vectorstore.py           embedding creation and Chroma document insertion
  loader.py                loads .txt knowledge files
  prompts/prompt_template.txt
                           active chatbot prompt template

static/documents/
  company_info.txt
  faq.txt
  knowledge_base.txt       currently empty
  objections.txt
  pricing_breakdown.txt
  pricing_guide.txt
  qualification_flow.txt
  rules.txt
  sales_style.txt
  services_detailed.txt
  use_cases.txt

scripts/
  ingest_docs.py           one-off ingestion script for static documents into Chroma

core/pricing/
  deterministic pricing and quote generation for devis; not called by chatbot
```

## 1. Overall Architecture

### Request Flow

```text
Client
  |
  | POST /api/chatbot/chat/
  | body: { "message": "...", "conversation_id": optional UUID }
  v
config/urls.py
  |
  v
apps/chatbot/urls.py
  |
  v
ChatbotAPIView.post()
  |
  | validate message and optional conversation_id
  | load or create Conversation
  | persist user ChatMessage
  | load full DB message history
  | call RAGChain.run(message, history=history[:-1])
  v
RAGChain
  |
  | sanitize query
  | optionally rewrite short follow-up with LLM
  | keyword intent detection
  | retrieve Chroma chunks via embeddings
  | filter/rerank chunks
  | build prompt
  | call OpenAI chat completion
  v
ChatbotAPIView.post()
  |
  | persist assistant ChatMessage
  | return answer, sources, intent, rewritten query
  v
Client
```

### Response Flow

The response is assembled in `apps/chatbot/views.py` and includes:

```json
{
  "conversation_id": "uuid",
  "message_id": 123,
  "query": "sanitized user query",
  "rewritten_query": "standalone retrieval query",
  "intent": "pricing|technical|company|services|general|unknown",
  "answer": "assistant response",
  "sources": [
    {
      "source": "pricing_guide.txt",
      "chunk_index": 0,
      "total_chunks": 10,
      "doc_type": "pricing"
    }
  ]
}
```

`context_used` is produced internally by `RAGChain.run()` but is not returned by the API.

### Components Involved

- Django REST Framework: API endpoint and JSON parsing/rendering.
- Django ORM: persists conversations and messages.
- ChromaDB: persistent vector store at `settings.CHROMA_DIR`, default `BASE_DIR / "chroma_db"`.
- OpenAI Python SDK:
  - embeddings: `text-embedding-3-small`
  - chat generation: `gpt-4.1-mini`
- Static text knowledge files under `static/documents`.

### Middleware

The chatbot uses global Django middleware from `config/settings.py`:

- CORS middleware
- security middleware
- WhiteNoise
- Django session middleware
- common middleware
- CSRF middleware
- auth middleware
- messages middleware
- clickjacking protection

There is no chatbot-specific middleware, no chatbot authentication layer, no rate limiter, and no AI safety middleware.

### Architecture Diagram

```text
                         +----------------------+
                         | static/documents/*.txt|
                         +----------+-----------+
                                    |
                                    | scripts/ingest_docs.py
                                    v
                           +------------------+
                           | ChromaDB         |
                           | collection       |
                           | smartdex_kb      |
                           +---------+--------+
                                     ^
                                     | vector/lexical search
+--------+       +-------------------+--------------------+       +---------+
| Client | ----> | Django DRF ChatbotAPIView               | ----> | OpenAI  |
+--------+       | apps/chatbot/views.py                   |       | chat    |
                 +-------------------+--------------------+       +---------+
                                     |
                                     | Conversation, ChatMessage
                                     v
                              +--------------+
                              | SQL database |
                              +--------------+
```

## 2. Prompt System

### Active Chatbot Prompt Template

Location:

- `core/ai/rag/prompts/prompt_template.txt`

Loaded by:

- `RAGChain._load_prompt()`

Injection point:

- `RAGChain._build_prompt(history, context, question)`
- The generated prompt is sent as a `user` message to OpenAI in `_generate()`.

Variables:

- `{context}`: retrieved source chunks
- `{question}`: sanitized original user query
- `{history}`: supported by `RAGChain._build_prompt()` and by `DEFAULT_PROMPT`, but the active prompt file does not contain `{history}`. Therefore conversation history is currently built but not injected into the final answer prompt.

Active template order:

```text
Consultant identity
Core objective
Strict rules
Communication style
How to respond
Example style
Vague request handling
Pricing handling
Hesitation handling
CONTEXT: {context}
QUESTION: {question}
Final instructions
```

### Fallback Default Prompt

Location:

- `core/ai/rag/chain.py`, `DEFAULT_PROMPT`

Used only when no prompt file exists. Because `core/ai/rag/prompts/prompt_template.txt` exists, this is not the active prompt.

Important difference:

- The fallback `DEFAULT_PROMPT` includes `CHAT HISTORY: {history}`.
- The active file does not include history.

### Final OpenAI System Message

Location:

- `core/ai/rag/chain.py`, `_generate()`

Content:

```text
You are a Smartdex AI assistant. Be accurate, grounded, natural, and sales-oriented.
```

This is the highest-priority chatbot instruction sent to the final generation call. The detailed consultant prompt is lower priority because it is sent as a `user` message.

### Query-Rewrite Prompt

Location:

- `core/ai/rag/chain.py`, `_rewrite_query_with_history()`

Used when:

- History exists.
- The sanitized query has 12 words or fewer.

Message structure:

- `system`: `Rewrite follow-up questions into standalone retrieval queries.`
- `user`: dynamic prompt containing recent history and latest user message.

Temperature:

- `0`

Purpose:

- Improve retrieval for short follow-up questions.

### Knowledge Documents as Behavioral Prompts

Several documents contain behavioral rules but are only used if retrieved:

- `rules.txt`: response rules, pricing rules, restrictions, tone.
- `qualification_flow.txt`: sales qualification flows.
- `sales_style.txt`: consultant phrasing and avoided style.
- `objections.txt`: objection handling.

These are not guaranteed system instructions. They are knowledge chunks competing with service, FAQ, company, use-case, and pricing chunks.

### Adjacent Devis Prompts

These are not used by the chatbot endpoint:

- `apps/devis/prompts/requirement_prompt.py`
- `apps/devis/prompts/quote_prompt.py`
- `apps/devis/prompts/validation_prompt.py`
- `apps/devis/prompts/planning_prompt.py`

They support quote generation, extraction, and wording in the devis module.

## 3. Knowledge Base and RAG

### Document Location

Knowledge files live in:

```text
static/documents/
```

Current files:

- `company_info.txt`
- `faq.txt`
- `knowledge_base.txt` empty
- `objections.txt`
- `pricing_breakdown.txt`
- `pricing_guide.txt`
- `qualification_flow.txt`
- `rules.txt`
- `sales_style.txt`
- `services_detailed.txt`
- `use_cases.txt`

### Ingestion

Ingestion script:

- `scripts/ingest_docs.py`

Flow:

```text
load_txt_files(static/documents)
  -> clean_text()
  -> get_doc_type(filename)
  -> get_chunking_config(doc_type)
  -> chunk_text()
  -> VectorStore.add_documents()
  -> OpenAI embeddings
  -> Chroma collection smartdex_kb
```

### Document Type Mapping

Configured in `scripts/ingest_docs.py`:

```python
{
    "company_info.txt": "company",
    "faq.txt": "faq",
    "pricing_guide.txt": "pricing",
    "pricing_info.txt": "pricing",
    "services_detailed.txt": "services",
    "rules.txt": "rules",
    "technical_stack.txt": "technical",
    "knowledge_base.txt": "general",
}
```

Every other file defaults to `general`.

Important consequence:

- `pricing_breakdown.txt` defaults to `general`.
- `qualification_flow.txt` defaults to `general`.
- `sales_style.txt` defaults to `general`.
- `objections.txt` defaults to `general`.
- `use_cases.txt` defaults to `general`.

### Chunk Size and Overlap

Configured by document type:

| Doc type | Chunk size | Overlap |
|---|---:|---:|
| faq | 350 | 50 |
| rules | 300 | 40 |
| pricing | 500 | 80 |
| services | 600 | 100 |
| technical | 700 | 120 |
| company | 450 | 70 |
| general | 550 | 90 |

Chunking is character-based with paragraph/sentence boundary attempts.

### Embedding Model

Used for ingestion and query embedding:

- `text-embedding-3-small`

Locations:

- `core/ai/rag/vectorstore.py`
- `core/ai/rag/retriever.py`

### Vector Store

Chroma:

- persistent client
- path: `settings.CHROMA_DIR`
- default path: `chroma_db`
- collection name: `smartdex_kb`

Read-only inspection with the project virtualenv found:

```text
count: 75 chunks
doc_types:
  company: 9
  faq: 13
  general: 20
  pricing: 10
  rules: 16
  services: 7
sources:
  company_info.txt: 9
  faq.txt: 13
  objections.txt: 4
  pricing_breakdown.txt: 6
  pricing_guide.txt: 10
  qualification_flow.txt: 4
  rules.txt: 16
  sales_style.txt: 2
  services_detailed.txt: 7
  use_cases.txt: 4
```

### Retrieval

Location:

- `core/ai/rag/retriever.py`

Default search:

- `top_k=8`
- query embedded with `text-embedding-3-small`
- Chroma query with optional metadata filter

If embedding search fails:

- falls back to lexical search over Chroma documents.

Lexical fallback scoring:

- normalize text to lowercase alphanumeric terms
- remove terms with length <= 2
- score by term occurrence count in document text + source + doc_type
- sort descending by score
- return top `top_k`

### Intent Detection

Location:

- `RAGChain._detect_intent()`

Method:

- simple keyword matching
- categories: `pricing`, `technical`, `company`, `services`, `general`

Only pricing intent changes retrieval:

```python
pricing -> {"doc_type": "pricing"}
all other intents -> None
```

### Filtering and Reranking

Distance filtering:

- default `max_distance=1.8`
- keep docs with missing distance or distance <= 1.8
- if all are weak, fallback to first 3 docs

Reranking:

- default `rerank_top_n=4`
- score based on query term presence in:
  - chunk text
  - source filename
  - doc_type
- distance is secondary
- returns top 4 docs

### Similarity Threshold

There is no true similarity threshold. The code uses Chroma distance and a `max_distance` cutoff of `1.8`, then falls back to the first 3 retrieved docs if all fail.

### Max Retrieved Chunks

- Chroma initial retrieval: 8
- final chunks included in prompt: 4
- local fallback snippets: first 3 docs

## 4. Context Builder and Final Prompt Order

Current `RAGChain.run()` order:

```text
1. User message from API
2. sanitize_query()
3. optional LLM query rewrite using recent history
4. intent detection on rewritten query
5. retrieval using rewritten query
6. distance filtering
7. lexical reranking
8. build history text from recent history
9. build context from final docs
10. build prompt from template
11. send OpenAI messages
12. return answer and source metadata
```

Final OpenAI payload:

```text
messages = [
  {
    role: "system",
    content: "You are a Smartdex AI assistant. Be accurate, grounded, natural, and sales-oriented."
  },
  {
    role: "user",
    content:
      active prompt template:
        SmartDex consultant identity
        sales response instructions
        strict rules
        CONTEXT: retrieved docs
        QUESTION: current sanitized user question
        final instructions
  }
]
```

Actual final prompt assembly:

```text
System message
  ↓
User message containing:
  consultant instructions
  ↓
  retrieved knowledge context
  ↓
  user question
  ↓
LLM
```

Important: conversation history is loaded and formatted but not included in the active prompt file. It is only used for query rewriting.

## 5. Memory and Conversation Management

### Session Handling

The backend uses explicit `conversation_id`, not anonymous browser session state.

If `conversation_id` is provided:

- load `Conversation` by UUID
- return 404 if not found

If omitted:

- create a new `Conversation(title="New conversation")`

### Persistence

Models:

- `Conversation`
  - UUID primary key
  - title
  - created_at
  - updated_at
- `ChatMessage`
  - FK to Conversation
  - role: `user` or `assistant`
  - content
  - created_at

User messages are stored before RAG execution. Assistant messages are stored after generation.

### History Length

The API loads the full conversation history from the database, then passes all previous messages to `RAGChain`.

Inside `RAGChain`:

- `_build_history_text()` keeps only the last 6 messages.
- Query rewrite sees at most those last 6 messages.
- Final generation currently sees no history because active `prompt_template.txt` has no `{history}` placeholder.

### Token Limits

No explicit token budget exists.

No code sets:

- `max_tokens`
- context token limit
- history token limit
- retrieved context character/token limit beyond chunk counts

### Summarization and Truncation

No summarization exists.

Truncation is limited to:

- history display: last 6 messages in `_build_history_text()`
- retrieval context: top 4 chunks after reranking
- local fallback: first 450 characters of up to 3 docs

## 6. Pricing Logic

### Chatbot Pricing

The chatbot does not call the deterministic pricing engine.

Pricing in chatbot answers comes from:

1. Retrieved RAG chunks.
2. Active prompt rule: give ranges, not fixed prices.
3. Model generation.

Pricing-intent retrieval filters to:

```python
{"doc_type": "pricing"}
```

Because only `pricing_guide.txt` is classified as `pricing`, pricing answers prioritize `pricing_guide.txt`.

### Pricing Documents

Pricing knowledge exists in:

- `static/documents/pricing_guide.txt`
- `static/documents/pricing_breakdown.txt`
- pricing-related sections inside `rules.txt`
- pricing-related lines inside `company_info.txt`
- potentially FAQ/use-case docs depending on content

Only `pricing_guide.txt` is reliably retrieved for pricing-intent questions because of metadata filtering.

### Deterministic Pricing Engine

Located in:

- `core/pricing/config.py`
- `core/pricing/catalog.py`
- `core/pricing/estimator.py`
- `core/pricing/quote_builder.py`
- `core/pricing/service.py`

Used by:

- `apps/devis`

Not used by:

- `apps/chatbot`
- `core/ai/rag/chain.py`

This means chatbot estimates and devis estimates can diverge.

### Why the Chatbot Invents or Changes Prices

Root causes:

- Detailed pricing is split across multiple sources with inconsistent doc_type metadata.
- `pricing_breakdown.txt` is excluded from pricing-filtered retrieval.
- Only 4 chunks enter the final prompt, so relevant ranges may be absent.
- The final prompt says "Always give price ranges" even when the retrieved context is incomplete, creating pressure to estimate.
- The model is not constrained by a deterministic pricing function.
- There is no citation requirement tying each price to a source.
- There is no validation pass that rejects prices not present in retrieved context.
- Chroma ingestion uses random UUIDs and `collection.add()`, so repeated ingestion can duplicate chunks and change retrieval results over time.

## 7. Sales Logic

### Current Behavior Support

The chatbot has sales-consultant behavior from three places:

1. Active prompt template:
   - act like a consultant
   - guide user
   - ask one smart follow-up question
   - provide price range and next step

2. Retrieved documents:
   - `qualification_flow.txt`
   - `sales_style.txt`
   - `objections.txt`
   - `rules.txt`
   - `company_info.txt`

3. Final system message:
   - "sales-oriented"

### Qualification

Qualification rules exist in `qualification_flow.txt`, but the chatbot does not run an explicit qualification state machine.

There is no code-level tracking of:

- business type
- project type
- budget
- timeline
- urgency
- decision maker
- contact details
- lead score
- qualification stage

### One Question at a Time

The prompt says to ask one smart follow-up question, but `qualification_flow.txt` says ask 1-2 targeted questions. Since both are lower-priority or retrieved instructions, enforcement is inconsistent.

### Recommendations and Upselling

Upselling guidance exists in:

- `rules.txt`
- `pricing_guide.txt`
- `company_info.txt`

But no deterministic recommendation engine exists. Recommendations are generated by the model from the current prompt and retrieved chunks.

### SmartDex Positioning

Positioning appears in:

- `company_info.txt`
- `services_detailed.txt`
- `rules.txt`
- `pricing_guide.txt`

The chatbot can know this if the chunks are retrieved. It is not fully guaranteed by the final system message.

## 8. Prompt Hierarchy

Actual priority at final answer time:

```text
OpenAI/API platform and model behavior
  ↓
OpenAI system message in _generate()
  ↓
User-message prompt template
  ↓
Retrieved knowledge pasted inside user-message prompt
  ↓
Current user question pasted inside user-message prompt
  ↓
Model internal knowledge and learned priors
```

Practical consequence:

- The large SmartDex consultant prompt is not a true system prompt.
- Retrieved knowledge is not a separate tool result or protected source channel; it is plain text in the user message.
- The user question appears after context, so an adversarial or conflicting user message may compete strongly with retrieved context.
- The model can still use its internal priors when context is incomplete despite the prompt saying "Use ONLY the provided context."

## 9. Response Generation

### Final Answer Generation

Location:

- `RAGChain._generate()`

Settings:

- provider: OpenAI
- model: `gpt-4.1-mini`
- temperature: `0.4`
- `max_tokens`: not set
- `top_p`: not set
- streaming: no
- retries: no explicit application retry
- timeout: no explicit application timeout
- fallback: local extractive fallback if generation raises an exception

### Query Rewrite Generation

Location:

- `RAGChain._rewrite_query_with_history()`

Settings:

- provider: OpenAI
- model: same as RAGChain model, default `gpt-4.1-mini`
- temperature: `0`
- `max_tokens`: not set
- `top_p`: not set
- streaming: no
- retries: no explicit application retry
- fallback: return original query

### Embeddings

Location:

- `Retriever.embed_query()`
- `VectorStore.embed_texts()`

Settings:

- provider: OpenAI
- model: `text-embedding-3-small`

### Retrieval Fallback

If embedding search fails:

- retriever logs a warning
- falls back to lexical search against existing Chroma documents

If retriever as a whole fails in `RAGChain.run()`:

- answer: "I could not retrieve relevant information right now."

If no docs are returned:

- answer: "I could not find enough relevant information to answer that accurately."

If final LLM generation fails:

- local fallback summarizes up to 3 retrieved chunks.

## 10. Failure Analysis

### Hallucinated or Wrong Pricing

Why it happens:

- pricing source split across `pricing_guide.txt`, `pricing_breakdown.txt`, and deterministic `core/pricing`
- only `pricing_guide.txt` has `doc_type=pricing`
- chatbot does not use deterministic pricing
- no post-generation price validation
- prompt pressures the model to always provide ranges

### Ignoring Documentation

Why it happens:

- relevant documents may not be retrieved
- pricing intent excludes general docs, including `pricing_breakdown.txt`
- only top 4 reranked chunks are injected
- final prompt is a user message, not the highest-priority instruction

### Generic ChatGPT Behavior

Why it happens:

- final system message is generic: "Smartdex AI assistant"
- no explicit stateful sales funnel
- no lead qualification memory slots
- no deterministic conversation policy
- many sales rules are normal retrieved text

### Verbose Answers

Why it happens:

- prompt asks for acknowledgment, explanation, features, pricing, next step, and follow-up
- no max token limit
- no response length controller
- no concise-answer rule enforced in code

### Multiple Questions

Why it happens:

- active prompt says one smart follow-up question
- `qualification_flow.txt` says ask 1-2 targeted questions
- no output validator checks question count

### Inconsistent Tone

Why it happens:

- prompt asks for conversational style
- `rules.txt` says avoid overly casual responses and no slang
- `sales_style.txt` suggests casual phrases
- retrieval may include different tone instructions per turn

### Weak Retrieval

Why it happens:

- intent detection is keyword-based
- only pricing has metadata filtering
- no hybrid vector + lexical scoring in normal successful path
- reranker checks term presence, not semantic relevance
- no source priority policy
- no deduplication after repeated ingestion

### Missing Citations

Why it happens:

- API returns `sources` metadata separately
- prompt does not require citations in the answer
- generation does not bind statements or prices to source IDs

### Prompt Leakage Risk

Why it happens:

- full prompt and source markers are placed in the user message
- no guardrail prevents the assistant from describing internal instructions
- no output filtering

### Prompt Injection Risk

Why it happens:

- retrieved documents and user question share the same user-message channel
- no malicious-instruction stripping from retrieved chunks
- no role separation between knowledge and instructions

### Conversation Memory Gap

Why it happens:

- history is only used for short-query rewrite
- active prompt template omits `{history}`
- no structured memory
- no summarization

### Operational Risk

Why it happens:

- no explicit OpenAI timeout
- no explicit retry/backoff at application level
- no rate limiting
- no authentication on chatbot endpoint
- no chatbot tests
- no ingestion idempotency

## 11. Current Behavior Baseline

The chatbot currently behaves as follows:

1. It receives one message at a time.
2. It persists the user message.
3. It optionally rewrites short follow-ups using previous messages.
4. It detects intent with keyword matching.
5. It retrieves Chroma chunks.
6. For pricing intent, it only searches chunks tagged `pricing`.
7. It filters weak results by distance and reranks by lexical overlap.
8. It passes retrieved context and the current question into the prompt template.
9. It calls OpenAI with a short system message and the full RAG prompt as a user message.
10. It stores and returns the assistant answer.

## Root Causes Summary

The chatbot's current weaknesses come from architectural ambiguity rather than one isolated bug:

- sales behavior is prompt/RAG-driven, not state-machine-driven
- pricing is RAG-generated, not calculated
- knowledge documents are inconsistently classified
- detailed prompt instructions are lower priority than they appear
- conversation history is not included in the active final prompt
- retrieval has no explicit source authority or citation policy
- the system has no validation layer after generation

## Evidence References

- `apps/chatbot/views.py`: API orchestration, persistence, RAG call, response payload.
- `apps/chatbot/models.py`: conversation and message schema.
- `apps/chatbot/serializers.py`: message and conversation_id validation.
- `core/ai/rag/chain.py`: intent detection, query rewriting, prompt building, model call, fallback behavior.
- `core/ai/rag/retriever.py`: embedding search and lexical fallback.
- `core/ai/rag/vectorstore.py`: embedding creation and Chroma insertion.
- `scripts/ingest_docs.py`: source loading, doc_type mapping, chunking config, Chroma ingestion.
- `core/ai/rag/prompts/prompt_template.txt`: active chatbot prompt template.
- `static/documents/*.txt`: knowledge, pricing, qualification, sales style, rules, objections.
- `core/pricing/*`: deterministic pricing used by devis, not by chatbot.
