# AMD LLM Gateway - Model Selection Guide

## Quick Decision Matrix

| Use Case | Recommended Model | Reasoning |
|----------|------------------|-----------|
| **Code Generation & Analysis** | Claude Sonnet 4.5 | Best coding capabilities, excellent reasoning |
| **Creative Writing** | Claude 3 Opus | Highest creativity and nuanced writing |
| **Data Analysis & Reasoning** | GPT-4 | Strong analytical capabilities, good with structured data |
| **Image Analysis** | Claude Sonnet 4.5 or GPT-4V | Both excellent vision capabilities |
| **Quick Tasks & Drafts** | Claude 3 Haiku or GPT-3.5 | Fast, cost-effective for simpler tasks |
| **Function Calling** | Claude Sonnet 4.5 or GPT-4 | Best tool use capabilities |
| **Long Context** | Claude 3 Opus | Largest context window (200K tokens) |
| **Reasoning Tasks** | O1-mini | Specialized for complex reasoning |
| **Embeddings** | Jina Embeddings v3 | High-quality vector embeddings |
| **Reranking / Search Relevance** | re2g-reranker-nq | Cross-encoder reranking for RAG pipelines |

## Model Capabilities Comparison

### Chat/Text Generation Models

| Model | Context Window | Strengths | Best For |
|-------|---------------|-----------|----------|
| claude-sonnet-4-5@20250929 | 200K | Coding, analysis | General tasks, programming |
| claude-3-opus | 200K | Creative, complex reasoning | Long documents, creative writing |
| claude-3-haiku | 200K | Fast, efficient | Quick tasks, high volume |
| gpt-4 | 8K-32K | Structured data, analysis | Data processing, conversation |
| gpt-4-turbo | 128K | Large documents | Document processing |
| gpt-3.5-turbo | 16K | Cost-effective | Simple tasks, high volume |
| o1-mini | 128K | Reasoning | Complex problem solving |

### Embedding Models

| Model | Dimensions | Use Case |
|-------|-----------|----------|
| jina-embeddings-v3 | 1024 | Semantic search, RAG |
| text-embedding-ada-002 | 1536 | General embeddings |

### Rerank Models

| Model | Use Case | Endpoint |
|-------|----------|----------|
| re2g-reranker-nq | Cross-encoder reranking for search/RAG | `POST /OnPrem/rerank` |

## Selection Criteria

### By Task Type

**Coding Tasks**
- First choice: `claude-sonnet-4-5@20250929`
- Alternative: `gpt-4`

**Document Processing**
- Large documents: `claude-3-opus` (200K context)
- Medium documents: `gpt-4-turbo` (128K context)

**Embeddings/Search**
- Semantic search: `jina-embeddings-v3`
- Compatibility: `text-embedding-ada-002`
- Reranking: `re2g-reranker-nq` (improves search result ordering in RAG pipelines)

**Quick Operations**
- High volume: `claude-3-haiku`
- Budget: `gpt-3.5-turbo`

### By Performance Requirements

| Requirement | Recommended | Avoid |
|-------------|-------------|-------|
| Fastest response | Haiku, GPT-3.5 | Opus, O1 |
| Highest quality | Opus, GPT-4 | Haiku, GPT-3.5 |
| Longest context | Opus (200K), GPT-4-Turbo (128K) | GPT-4 (8K) |
| Best reasoning | O1-mini, Opus | Haiku |

## Provider-Specific Notes

### Claude Models (Anthropic SDK)
- All Claude models use the same endpoint pattern
- Support streaming, tool use, and vision
- Consistent 200K context window

### GPT Models (OpenAI SDK)
- Deployment ID lookup may be required
- O1 models use `max_completion_tokens` instead of `max_tokens`
- Vision requires specific model variant

### OnPrem Models
- Jina embeddings hosted on-premise
- Lower latency for embedding operations
- Model name in URL path

## Security & Compliance

- All traffic through AMD Gateway (VPN required)
- No data sent to external providers
- API key authentication via `Ocp-Apim-Subscription-Key`
- Audit logging available
