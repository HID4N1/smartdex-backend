# SmartDex Production AI Sales Consultant Architecture

Date: 2026-07-29  
Status: implemented internally with the existing `/api/chatbot/chat/` API preserved.

## 1. Architecture Diagram

```text
Client
  |
  | POST /api/chatbot/chat/
  v
ChatbotAPIView
  |
  | stores user message
  | loads previous conversation messages
  v
RAGChain Orchestrator
  |
  +--> BusinessLogicEngine
  |      | extracts deterministic sales facts
  |      | classifies project type
  |      | matches official SmartDex service
  |      | selects package
  |      | calls deterministic pricing engine
  |
  +--> SalesStateMachine
  |      | chooses GREETING, DISCOVERY, QUALIFICATION,
  |      | SERVICE_SELECTION, RECOMMENDATION,
  |      | OBJECTION_HANDLING, PRICING,
  |      | LEAD_CAPTURE, or HANDOFF
  |
  +--> Retriever
  |      | retrieves SmartDex knowledge from Chroma
  |      | reranks with official source priority
  |
  +--> PromptBuilder
  |      | builds strict system prompt hierarchy
  |      | injects state, business output, knowledge,
  |      | history, and current user message
  |
  +--> OpenAI LLM
  |      | generates wording only
  |
  +--> ResponseValidator
         | validates one question, length, pricing gate,
         | tone, and unsupported-service risks
         | regenerates once or falls back deterministically
```

## 2. Folder Structure

```text
apps/chatbot/services/
  business_logic.py        deterministic facts, service matching, package and pricing decisions
  prompting.py             production system prompt hierarchy and message assembly
  state_machine.py         conversation states, policies, and transition selection
  validation.py            post-generation validation and deterministic fallback

core/ai/rag/
  chain.py                 orchestrates business logic, state, retrieval, LLM, validation
  retriever.py             embeddings, Chroma search, lexical fallback
  loader.py                recursive .txt/.md knowledge loading

static/documents/chatbot_structured/
  01_identity.md
  02_company.md
  03_services.md
  04_pricing.md
  05_sales_playbook.md
  06_qualification.md
  07_objections.md
  08_case_studies.md
  09_process.md
  10_faq.md
  11_rules.md

docs/chatbot/
  current-chatbot-architecture.md
  production-sales-consultant-architecture.md
```

## 3. Prompt Architecture

The new hierarchy is:

```text
SYSTEM
  SmartDex Identity
  Business Rules
  Sales Rules
  Pricing Rules
  Conversation Rules
  Response Rules
  Safety Rules
    ↓
Conversation State
    ↓
Business Logic Output
    ↓
Retrieved Knowledge
    ↓
Conversation History
    ↓
Current User Message
    ↓
LLM wording
```

Business rules are now in `apps/chatbot/services/prompting.py` as the actual OpenAI `system` message. Knowledge documents are not treated as business rules. They provide supporting facts only.

The LLM is explicitly told that deterministic decisions were already made by the application and must not be changed.

## 4. Business Logic Layer

`BusinessLogicEngine` runs before retrieval and before the LLM.

It deterministically handles:

- project classification
- feature detection
- integration detection
- complexity hints
- urgency hints
- official SmartDex service matching
- package selection
- pricing engine call
- missing-information detection
- recommended next step

The LLM no longer decides these things. It only explains the result.

## 5. State Machine

States are defined in `apps/chatbot/services/state_machine.py`.

| State | Objective | Pricing allowed |
|---|---|---|
| GREETING | Open conversation and identify business context | No |
| DISCOVERY | Understand business and project goal | No |
| QUALIFICATION | Collect scope signals | No |
| SERVICE_SELECTION | Match need to official service | No |
| RECOMMENDATION | Recommend package and next step | No fixed quote |
| OBJECTION_HANDLING | Handle hesitation professionally | No new price |
| PRICING | Explain official deterministic range | Yes |
| LEAD_CAPTURE | Collect contact or handoff details | No new price |
| HANDOFF | Prepare human follow-up | No new scope/price |

Pricing state is only selected when the user asks for pricing and enough scope exists for deterministic pricing.

## 6. Knowledge Base

The structured KB lives in:

```text
static/documents/chatbot_structured/
```

Files:

1. `01_identity.md`
2. `02_company.md`
3. `03_services.md`
4. `04_pricing.md`
5. `05_sales_playbook.md`
6. `06_qualification.md`
7. `07_objections.md`
8. `08_case_studies.md`
9. `09_process.md`
10. `10_faq.md`
11. `11_rules.md`

`core/ai/rag/loader.py` now supports recursive `.txt` and `.md` files. `scripts/ingest_docs.py` maps structured files to specific `doc_type` values.

Important metadata correction:

- `pricing_breakdown.txt` now maps to `doc_type=pricing`.
- qualification, sales, objections, and use-case files now get specific doc types.

## 7. Retrieval Priorities

Retrieval still uses Chroma and OpenAI embeddings, but reranking now gives priority to official SmartDex sources:

1. `04_pricing.md`
2. `11_rules.md`
3. `01_identity.md`
4. `05_sales_playbook.md`
5. `06_qualification.md`
6. `pricing_guide.txt`
7. `03_services.md`
8. `02_company.md`
9. `pricing_breakdown.txt`
10. `07_objections.md`
11. legacy service, company, FAQ, style, objection, and use-case files

Structured `.md` files are preferred after ingestion because they are organized as canonical chatbot knowledge.

Business rules do not depend on retrieval.

## 8. Pricing Flow

```text
User pricing question
  |
  v
BusinessLogicEngine extracts known scope
  |
  v
SalesStateMachine checks if pricing is allowed
  |
  +-- insufficient scope --> QUALIFICATION --> ask one missing detail
  |
  +-- sufficient scope
        |
        v
  core.pricing.estimate_project()
        |
        v
  official range + package
        |
        v
  LLM explains range without changing it
        |
        v
  ResponseValidator checks pricing gate
```

The chatbot does not calculate prices in the prompt.

## 9. Conversation Flow

```text
GREETING
  -> DISCOVERY
  -> QUALIFICATION
  -> SERVICE_SELECTION
  -> RECOMMENDATION
  -> PRICING
  -> LEAD_CAPTURE
  -> HANDOFF
```

The flow can adapt to user input, but deterministic policy prevents pricing before enough scope is collected.

Default answer shape:

```text
Short acknowledgement.
Useful answer or explanation.
One follow-up question.
```

## 10. Quote Architecture

The chatbot does not generate quotes directly.

Quote flow remains separated:

```text
Conversation
  -> collected structured data
  -> business logic
  -> pricing engine
  -> quote generator/devis module
  -> LLM formats explanation
```

For actual quote generation, the existing `apps/devis` architecture remains the correct path.

## 11. Validation Layer

`ResponseValidator` checks:

- answer is non-empty
- one question maximum
- response is not too long
- pricing is not mentioned before allowed
- generic assistant phrases are avoided
- unsupported-service risks are blocked

If validation fails:

1. The orchestrator asks the LLM to regenerate once with the validation reasons.
2. If validation still fails, the system returns a deterministic fallback from business logic.

## 12. API Compatibility

The endpoint remains:

```text
POST /api/chatbot/chat/
```

The response still includes:

- `conversation_id`
- `message_id`
- `query`
- `rewritten_query`
- `intent`
- `answer`
- `sources`

Internally, `RAGChain.run()` also returns `state` and `business_decision`, but the view currently preserves the existing frontend response shape.

## 13. Migration Notes

1. Reingest the knowledge base before production use so Chroma includes the new structured `.md` files and corrected metadata.
2. Do not run ingestion repeatedly without clearing or upserting the collection, because the current ingestion script still uses random UUID chunk IDs.
3. Frontend changes are not required for compatibility.
4. Future frontend improvements can display `state`, missing information, or lead capture status if the API response is expanded.
5. The deterministic business layer is heuristic. For production, add richer extraction and explicit structured memory fields if the sales process becomes more complex.

## 14. Testing Checklist

Completed:

- `venv/bin/python -m py_compile core/ai/rag/chain.py core/ai/rag/loader.py scripts/ingest_docs.py apps/chatbot/services/state_machine.py apps/chatbot/services/business_logic.py apps/chatbot/services/prompting.py apps/chatbot/services/validation.py`
- `venv/bin/python manage.py test apps.chatbot.tests`

Manual checks to run after reingestion:

- Vague greeting should ask business type.
- "How much does it cost?" with no scope should ask one qualification question and not mention price.
- Known booking-system scope plus price question should expose deterministic MAD range.
- Website request should recommend qualification before pricing.
- Objection about price should suggest MVP/phasing without inventing discounts.
- Response should contain at most one question.
- Response should stay concise.

## 15. Architectural Decisions

- Keep `RAGChain` as compatibility coordinator to avoid breaking the existing endpoint.
- Move sales decisions into `apps/chatbot/services`.
- Use the existing `core/pricing` engine instead of introducing a second pricing source.
- Keep knowledge retrieval as supporting context, not authority for business rules.
- Add validation after LLM generation because prompt rules alone are not reliable enough.
- Keep structured KB files separate from legacy `.txt` files so migration is clear and reversible.
