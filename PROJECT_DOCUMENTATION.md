# Smartdex Backend Project Documentation

## 1. Project Overview

Smartdex Backend is a Django REST Framework project that powers an AI-assisted digital services platform. The system supports two main business capabilities:

1. An AI chatbot that answers client questions about Smartdex services, pricing, company information, and project recommendations.
2. A quote generation module, called `devis`, that receives project requirements and produces a structured commercial estimate.

The academic importance of this project is that it combines traditional backend engineering with modern AI techniques:

- REST API design with Django and Django REST Framework.
- Conversational AI using Large Language Models.
- Retrieval-Augmented Generation, also called RAG, for grounded chatbot responses.
- LangChain structured output for extracting project requirements from natural language.
- Vector search with ChromaDB and OpenAI embeddings.
- Rule-based pricing logic combined with LLM-based requirement understanding.

The project is organized as a backend API intended to be consumed by a frontend, likely a web interface running on smartdex.ma

## 2. Main Technologies

| Area | Technology |
| --- | --- |
| Backend framework | Django, Django REST Framework |
| Database | SQLite |
| AI provider | OpenAI |
| Chat model | `gpt-4.1-mini` |
| Embedding model | `text-embedding-3-small` |
| RAG vector database | ChromaDB |
| LLM orchestration | LangChain, LangChain OpenAI |
| Data validation | DRF serializers, Pydantic |
| PDF generation | ReportLab |
| Environment variables | python-dotenv |
| CORS | django-cors-headers |

## 3. High-Level Architecture

The project follows a layered architecture:

```text
Client / Frontend
      |
      v
Django REST API
      |
      +-- apps.chatbot
      |      |
      |      +-- Conversation persistence
      |      +-- RAGChain
      |             |
      |             +-- Retriever
      |             +-- ChromaDB
      |             +-- OpenAI embeddings
      |             +-- OpenAI chat completion
      |
      +-- apps.devis
      |      |
      |      +-- DevisRequest persistence
      |      +-- Core pricing service
      |      |      |
      |      |      +-- LangChain requirement extractor
      |      |      +-- Normalization
      |      |      +-- Estimation rules
      |      |      +-- Quote builder
      |      |
      |      +-- Optional PDF generation
      |
      +-- apps.health
             |
             +-- Health check endpoint
```

The design separates API concerns from AI and pricing concerns. The `apps` directory contains Django-facing code such as views, serializers, models, and URLs. The `core` directory contains reusable domain logic, including RAG and pricing.

## 4. Project Structure

```text
smartdex-backend/
  apps/
    chatbot/
      models.py
      serializers.py
      views.py
      urls.py
      admin.py
    devis/
      models.py
      serializers.py
      views.py
      urls.py
      services/
      presentation/
    health/
      views.py
      urls.py
  config/
    settings.py
    urls.py
    asgi.py
    wsgi.py
  core/
    ai/
      rag/
        chain.py
        retriever.py
        vectorstore.py
        loader.py
        prompts/
    pricing/
      extractor.py
      extractor_schema.py
      normalizer.py
      estimator.py
      selector.py
      quote_builder.py
      catalog.py
      config.py
    utils/
      clean_text.py
      chunker.py
      validators.py
  scripts/
    ingest_docs.py
  static/
    documents/
```

## 5. Django Configuration

The project entry point is `config/urls.py`. It exposes three API groups:

| Base URL | Purpose |
| --- | --- |
| `/api/chatbot/` | Conversational AI chatbot |
| `/api/devis/` | Quote request and quote generation |
| `/api/health/` | Health check endpoint |
| `/admin/` | Django admin panel |

The installed local applications are:

- `apps.chatbot`
- `apps.devis`
- `apps.health`

The project uses SQLite through `db.sqlite3`, JSON-only API rendering and parsing in Django REST Framework, and CORS access for:

- `http://localhost:3000`
- `http://127.0.0.1:3000`

The backend expects an `OPENAI_API_KEY` environment variable loaded with `python-dotenv`.

## 6. Chatbot Module

### 6.1 Purpose

The chatbot module allows users to ask questions about Smartdex services, prices, technologies, use cases, and company information. It stores conversations and messages in the database, then uses RAG to produce grounded answers.

### 6.2 API Endpoint

```text
POST /api/chatbot/chat/
```

Expected request body:

```json
{
  "message": "How much does an AI chatbot cost?",
  "conversation_id": "optional-existing-conversation-uuid"
}
```

Response body includes:

```json
{
  "conversation_id": "...",
  "message_id": 1,
  "query": "...",
  "rewritten_query": "...",
  "intent": "pricing",
  "answer": "...",
  "sources": []
}
```

### 6.3 Data Model

The chatbot uses two models:

| Model | Purpose |
| --- | --- |
| `Conversation` | Represents a chat session with a UUID primary key. |
| `ChatMessage` | Stores each user or assistant message linked to a conversation. |

`ChatMessage` has two roles:

- `user`
- `assistant`

Messages are ordered by `created_at`, which allows the chatbot to build recent conversation history.

### 6.4 Chat Flow

```text
User sends message
      |
      v
ChatRequestSerializer validates input
      |
      v
Find or create Conversation
      |
      v
Store user ChatMessage
      |
      v
Load previous conversation history
      |
      v
RAGChain.run(message, history)
      |
      v
Store assistant ChatMessage
      |
      v
Return answer, intent, sources, and rewritten query
```

## 7. RAG System

### 7.1 What RAG Means

Retrieval-Augmented Generation is an AI architecture where the system retrieves relevant external knowledge before generating an answer. Instead of relying only on the model's internal training data, the model receives project-specific context.

In this project, RAG helps the chatbot answer using Smartdex's own documents:

- Company information.
- Service descriptions.
- Pricing guides.
- FAQ.
- Objection handling.
- Qualification flows.
- Sales style.
- AI response rules.
- Use cases.

This makes the chatbot more reliable and business-specific.

### 7.2 Knowledge Base Documents

The source documents live in:

```text
static/documents/
```

Important files include:

| File | Purpose |
| --- | --- |
| `company_info.txt` | Smartdex identity, services, target clients, value proposition. |
| `services_detailed.txt` | Detailed description of Smartdex services. |
| `pricing_guide.txt` | Pricing ranges and commercial rules. |
| `pricing_breakdown.txt` | More detailed price breakdown information. |
| `faq.txt` | Frequently asked questions. |
| `qualification_flow.txt` | How to qualify vague client requests. |
| `rules.txt` | Rules for AI behavior and pricing communication. |
| `sales_style.txt` | Desired sales tone and communication style. |
| `use_cases.txt` | Example business cases and estimated ranges. |
| `objections.txt` | How to respond to client objections. |

### 7.3 Ingestion Pipeline

The ingestion script is:

```text
scripts/ingest_docs.py
```

Its job is to transform raw text files into searchable vector data.

```text
TXT documents
      |
      v
load_txt_files()
      |
      v
clean_text()
      |
      v
chunk_text()
      |
      v
OpenAI embeddings
      |
      v
ChromaDB collection: smartdex_kb
```

The script performs these steps:

1. Loads all `.txt` files from `static/documents`.
2. Classifies each document into a `doc_type`, such as `company`, `pricing`, `services`, or `faq`.
3. Cleans the text by normalizing spacing and removing unsupported characters.
4. Splits text into overlapping chunks.
5. Generates embeddings using OpenAI's `text-embedding-3-small`.
6. Stores chunks, embeddings, and metadata in ChromaDB.

Each stored chunk includes metadata:

```json
{
  "source": "pricing_guide.txt",
  "chunk_index": 0,
  "total_chunks": 5,
  "doc_type": "pricing"
}
```

### 7.4 Chunking Strategy

The chunker in `core/utils/chunker.py` splits text into overlapping pieces. It tries to preserve paragraph and sentence boundaries by splitting around:

- Blank lines.
- New lines.
- Sentence endings.

Different document types use different chunk sizes:

| Document type | Chunk size | Overlap |
| --- | ---: | ---: |
| FAQ | 350 | 50 |
| Rules | 300 | 40 |
| Pricing | 500 | 80 |
| Services | 600 | 100 |
| Technical | 700 | 120 |
| Company | 450 | 70 |
| General | 550 | 90 |

This is important because small chunks improve precision, while overlap helps preserve context across chunk boundaries.

### 7.5 Vector Store

The vector store is implemented in `core/ai/rag/vectorstore.py`.

It uses:

- `chromadb.PersistentClient`
- collection name `smartdex_kb`
- OpenAI embeddings

The persisted local vector database is stored in:

```text
chroma_db/
```

### 7.6 Retrieval

The retriever is implemented in `core/ai/rag/retriever.py`.

The retrieval process is:

1. Convert the user query into an embedding.
2. Search ChromaDB for similar document chunks.
3. Return documents, metadata, distances, and IDs.

The default search retrieves up to `top_k = 8` chunks.

### 7.7 Intent Detection

Before retrieval, `RAGChain` detects the user's intent using keyword matching. Supported intents are:

- `pricing`
- `technical`
- `company`
- `services`
- `general`

For pricing questions, the retriever applies a metadata filter:

```json
{
  "doc_type": "pricing"
}
```

This improves retrieval relevance when the user asks about costs, budgets, estimates, or `devis`.

### 7.8 Query Rewriting

Short follow-up questions can be ambiguous. For example:

```text
And how much does it cost?
```

The method `_rewrite_query_with_history()` uses the recent chat history and the LLM to rewrite the question into a standalone retrieval query. This improves search quality because vector databases work better with complete queries.

### 7.9 Reranking and Filtering

After retrieval, `RAGChain` filters weak documents using a maximum distance threshold. It then reranks the remaining documents using a simple lexical score based on:

- Terms appearing in the document text.
- Terms appearing in the source filename.
- Terms appearing in the document type.
- Vector distance.

Only the top reranked documents are placed in the final context.

### 7.10 Prompt Construction

The prompt template is located at:

```text
core/ai/rag/prompts/prompt_template.txt
```

The prompt instructs the assistant to:

- Act as a Smartdex AI consultant.
- Use only provided context.
- Avoid inventing information.
- Provide price ranges instead of fixed prices.
- Ask a smart follow-up question when the request is vague.
- Speak naturally and in a business-oriented way.

Final prompt variables include:

- `{context}`
- `{question}`

The code also has support for `{history}` in the fallback prompt, but the current prompt file mainly uses context and question.

### 7.11 LLM Generation

The final answer is generated using OpenAI chat completions. The default model is:

```text
gpt-4.1-mini
```

Temperature is set to `0.4`, which allows some natural language variation while keeping responses reasonably controlled.

## 8. Devis Module

### 8.1 Purpose

The `devis` module generates commercial quotes from client project descriptions. A client can submit a natural language description and optional structured hints such as project type, features, budget, and timeline.

The module combines:

- Database storage of quote requests.
- LLM-based extraction of project specifications.
- Rule-based pricing estimation.
- Component-based quote building.
- Optional PDF output.

### 8.2 API Endpoints

Create a quote request:

```text
POST /api/devis/requests/
```

Generate a quote:

```text
POST /api/devis/requests/<id>/generate/
```

Generate a PDF quote:

```text
POST /api/devis/requests/<id>/generate/?format=pdf
```

### 8.3 DevisRequest Model

The `DevisRequest` model stores:

| Field | Purpose |
| --- | --- |
| `description` | Main free-form project description. |
| `client_name` | Client name. |
| `client_email` | Client email. |
| `client_phone` | Client phone. |
| `budget_range` | Optional budget hint. |
| `timeline` | Optional timeline hint. |
| `project_type` | Optional project type hint. |
| `preferred_language` | Optional language preference. |
| `features` | Optional JSON list of selected features. |
| `extra_hints` | Optional JSON object for additional hints. |
| `status` | `pending`, `processed`, or `failed`. |

### 8.4 Devis Flow

```text
Client submits DevisRequest
      |
      v
Request is stored as pending
      |
      v
Generate endpoint loads request
      |
      v
apps.devis.services.DevisService
      |
      v
core.pricing.DevisService.generate_devis()
      |
      +-- Extract requirements with LangChain
      +-- Normalize features and project type
      +-- Estimate global price range
      +-- Select quote components
      +-- Build itemized quote
      |
      v
Format response for API
      |
      v
Mark request as processed
      |
      v
Return JSON or PDF
```

## 9. LangChain Requirement Extraction

### 9.1 Purpose

The project uses LangChain in `core/pricing/extractor.py` to transform an unstructured client request into a structured project specification.

This is necessary because users may write vague or non-technical descriptions such as:

```text
I need a booking platform for my clinic with reminders.
```

The system needs to infer:

- Project type.
- Business goal.
- Required features.
- Integrations.
- Complexity.
- Design level.
- Urgency.
- Missing information.

### 9.2 Structured Output

The extractor uses:

```python
ChatOpenAI(...).with_structured_output(
    ExtractedProjectSpec,
    method="json_schema",
)
```

The target schema is a Pydantic model called `ExtractedProjectSpec`.

Key fields include:

| Field | Example |
| --- | --- |
| `project_type` | `booking_system` |
| `business_goal` | `Allow patients to book appointments online.` |
| `features` | `["booking", "notifications", "admin dashboard"]` |
| `integrations` | `["whatsapp"]` |
| `complexity` | `medium` |
| `design_level` | `standard` |
| `urgency` | `normal` |
| `confidence` | `0.85` |
| `missing_information` | `["Number of users", "Payment requirement"]` |

This approach is academically relevant because it demonstrates LLMs being used not only for chat, but also for information extraction and decision support.

## 10. Pricing Pipeline

The pricing pipeline is located in:

```text
core/pricing/
```

It has four main stages.

### 10.1 Extraction

File:

```text
core/pricing/extractor.py
```

The LLM reads the client request and returns an `ExtractedProjectSpec`.

### 10.2 Normalization

File:

```text
core/pricing/normalizer.py
```

The normalizer converts different labels into internal standardized labels. For example:

| Input | Normalized value |
| --- | --- |
| `appointments` | `booking` |
| `online payments` | `payments` |
| `admin panel` | `admin_dashboard` |
| `whatsapp reminders` | `notifications` |

It also adds implied features:

- If `admin_dashboard_needed` is true, add `admin_dashboard`.
- If `user_accounts_needed` is true, add `authentication`.
- If `payment_needed` is true, add `payments`.
- If `notifications_needed` is true, add `notifications`.

### 10.3 Estimation

File:

```text
core/pricing/estimator.py
```

The estimator calculates a global project price range in MAD.

It starts with a base price range from `core/pricing/config.py`, for example:

| Project type | Base range |
| --- | ---: |
| Website | 5,000 to 20,000 MAD |
| Web application | 15,000 to 60,000 MAD |
| SaaS | 60,000 to 150,000 MAD |
| E-commerce | 20,000 to 80,000 MAD |
| AI system | 20,000 to 100,000 MAD |
| Booking system | 15,000 to 50,000 MAD |

Then it adjusts the range using:

- Feature modifiers.
- Integration modifiers.
- Complexity multipliers.
- Design multipliers.
- Urgency multipliers.

The estimator also classifies the project:

| Estimated max | Classification |
| ---: | --- |
| Up to 30,000 MAD | `small_project` |
| Up to 100,000 MAD | `mid_project` |
| Above 100,000 MAD | `large_project` |

### 10.4 Quote Building

Files:

```text
core/pricing/selector.py
core/pricing/quote_builder.py
core/pricing/catalog.py
```

The selector chooses quote components from `QUOTE_CATALOG`. Components include:

- Website / Frontend.
- Admin Dashboard.
- User Authentication.
- Booking System.
- Online Payments.
- Notifications System.
- WhatsApp Integration.
- Analytics Dashboard.
- AI Chatbot.
- Deployment.
- Maintenance.
- Hosting.

The quote builder applies the same complexity, design, and urgency multipliers to component prices, then groups items into:

- `core`
- `integration`
- `optional`
- `delivery`
- `recurring`

The final quote contains:

- Included groups.
- Optional items.
- Recurring items.
- Totals.
- Notes.
- Missing information.

## 11. PDF Generation

The project can generate a PDF quote when the user calls:

```text
POST /api/devis/requests/<id>/generate/?format=pdf
```

The PDF generation process uses:

| File | Purpose |
| --- | --- |
| `apps/devis/services/pdf_context_builder.py` | Converts API payload into a PDF-friendly context. |
| `apps/devis/services/pdf_generator.py` | Uses ReportLab to build the PDF document. |

The PDF includes:

- Quote number.
- Date.
- Client information.
- Project information.
- Global estimate.
- Cost drivers.
- Included services.
- Optional services.
- Recurring costs.
- Totals.
- Notes.
- Missing information to confirm.

## 12. Admin Interface

The Django admin is configured for both main modules.

For the chatbot:

- Conversations can be listed and searched.
- Messages are visible inline inside each conversation.
- Messages can be filtered by role and date.

For devis:

- Requests can be listed by ID, client, status, and creation date.
- Admin users can search by client information or description.
- Requests can be filtered by status and creation date.

## 13. Health Module

The health module exposes:

```text
GET /api/health/
```

Response:

```json
{
  "status": "ok"
}
```

This endpoint is useful for checking whether the backend is running.

## 14. Data Flow Summary

### 14.1 Chatbot Data Flow

```text
Question
  -> Sanitization
  -> Optional query rewriting
  -> Intent detection
  -> Vector search
  -> Weak document filtering
  -> Reranking
  -> Prompt construction
  -> LLM answer generation
  -> Database persistence
  -> API response
```

### 14.2 Devis Data Flow

```text
Project description
  -> LLM structured extraction
  -> Normalization
  -> Base price selection
  -> Feature and integration modifiers
  -> Complexity, design, urgency multipliers
  -> Component selection
  -> Quote formatting
  -> JSON or PDF response
```

## 15. Academic Interpretation

This project is a practical example of an AI-enhanced backend system. It does not treat the LLM as a standalone chatbot only. Instead, it uses LLMs in two complementary ways.

First, the chatbot uses RAG to ground answers in a controlled knowledge base. This reduces hallucination and allows Smartdex to control the assistant's business knowledge, pricing rules, tone, and qualification behavior.

Second, the devis pipeline uses LangChain structured output to convert natural language into machine-readable requirements. This allows the backend to combine human-like understanding with deterministic pricing rules. The LLM extracts meaning, but the final price logic remains transparent and rule-based.

This division is important:

- The LLM handles ambiguity and language understanding.
- The vector database handles knowledge retrieval.
- The pricing engine handles business rules.
- Django handles persistence, validation, routing, and API delivery.

As a result, the project demonstrates an applied architecture for building AI systems that are more controllable than a simple prompt-only chatbot.

## 16. Strengths of the Project

- Clear separation between Django apps and reusable core logic.
- Persistent chat history for multi-turn conversations.
- RAG architecture with source metadata.
- Query rewriting for follow-up questions.
- Intent detection to improve retrieval for pricing questions.
- LangChain structured output for reliable requirement extraction.
- Rule-based pricing engine, making estimates explainable.
- Support for both JSON and PDF quote output.
- Admin interface for inspecting conversations and requests.
- Local ChromaDB persistence for the knowledge base.

## 17. Current Limitations

- `README.md` is currently empty, so project setup instructions are not documented there.
- `rules.py` is empty, which suggests planned pricing rules may not yet be implemented.
- The current prompt file does not include `{history}`, although the chain prepares chat history.
- `knowledge_base.txt` is empty, so one configured knowledge document contributes no information.
- The quote service builds `hints` in `apps/devis/services/devis_services.py`, but that local variable is not used directly afterward.
- `ReportLab` is used by the PDF generator, but it should be confirmed that it is included in the final dependency list.
- The Django settings comment mentions Django 5.1.7, while `requirements.txt` pins Django 6.0.4.
- `ALLOWED_HOSTS` is empty and `DEBUG = True`, so production hardening is still needed.
- Error handling in quote generation marks a request as failed, then re-raises the exception without returning a user-friendly API response.
- Tests exist as files, but no meaningful test coverage is currently implemented.

## 18. Recommended Improvements

For future academic or production development, the following improvements would strengthen the project:

1. Add full setup instructions to `README.md`.
2. Add automated tests for the chatbot endpoint, RAG utility functions, pricing pipeline, and devis endpoints.
3. Add a management command for document ingestion instead of only a standalone script.
4. Include chat history in the final RAG prompt template or remove unused history formatting.
5. Add source citations in chatbot answers when appropriate.
6. Add authentication and authorization if quote requests or conversation history contain sensitive client information.
7. Add production settings for `DEBUG`, `SECRET_KEY`, `ALLOWED_HOSTS`, CORS, and database configuration.
8. Add logging and monitoring around OpenAI failures, ChromaDB retrieval failures, and quote generation failures.
9. Add a document re-ingestion strategy that avoids duplicate chunks in ChromaDB.
10. Add validation for uploaded or edited knowledge-base documents if document management becomes user-facing.

## 19. Conclusion

Smartdex Backend is an AI-powered Django REST API designed for digital service consultation and automated quote generation. Its chatbot uses Retrieval-Augmented Generation to answer questions from a Smartdex-specific knowledge base, while its devis module uses LangChain and structured LLM output to transform client requirements into a normalized project specification.

The most important architectural quality of the project is the combination of probabilistic AI and deterministic business logic. The LLM understands language and context, the RAG system retrieves relevant knowledge, and the pricing engine applies explicit rules to produce explainable estimates. This makes the project suitable as an academic case study in applied LLM engineering, RAG systems, and AI-assisted business automation.
