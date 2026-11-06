# AMD LLM Gateway - API Endpoints Reference

## Base URL

```
https://llm-api.amd.com
```

## Provider Endpoints

### Anthropic (Claude Models)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/Anthropic/v1/messages` | POST | Chat completion |
| `/Anthropic/v1/messages` | POST | Streaming (with stream=true) |

**Models**: `claude-sonnet-4-5@20250929`, `claude-3-opus`, `claude-3-haiku`

### OpenAI (GPT Models)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/OpenAI/v1/chat/completions` | POST | Chat completion |
| `/openai/deployments/{id}/chat/completions` | POST | Deployment-specific |
| `/OpenAI/v1/embeddings` | POST | Embeddings |

**Models**: `gpt-4`, `gpt-4-turbo`, `gpt-3.5-turbo`, `o1-mini`

### OnPrem (Jina, Local Models)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/OnPrem/deployments/{model}/embeddings` | POST | Embeddings |
| `/api/OnPrem/deployments/{model}/v1/embeddings` | POST | OpenAI-compatible |
| `/OnPrem/rerank` | POST | Reranking |

**Models**: `jina-embeddings-v3`, `sentence-transformers/*`, `re2g-reranker-nq`

## Discovery Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/models` | GET | List all available models |
| `/api/Home/AvailableDeployment/{model}` | GET | Get deployments for model |

## Request Examples

### Claude Chat Completion

```bash
curl -X POST "https://llm-api.amd.com/Anthropic/v1/messages" \
  -H "Content-Type: application/json" \
  -H "Ocp-Apim-Subscription-Key: $AMD_LLM_API_KEY" \
  -d '{
    "model": "claude-sonnet-4-5@20250929",
    "max_tokens": 1000,
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### GPT Chat Completion

```bash
curl -X POST "https://llm-api.amd.com/OpenAI/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Ocp-Apim-Subscription-Key: $AMD_LLM_API_KEY" \
  -d '{
    "model": "gpt-4",
    "max_tokens": 1000,
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### Jina Embeddings

```bash
curl -X POST "https://llm-api.amd.com/api/OnPrem/deployments/jina-embeddings-v3/embeddings" \
  -H "Content-Type: application/json" \
  -H "Ocp-Apim-Subscription-Key: $AMD_LLM_API_KEY" \
  -d '{
    "input": ["Text to embed"],
    "model": "jina-embeddings-v3"
  }'
```

### Rerank

```bash
curl -X POST "https://llm-api.amd.com/OnPrem/rerank" \
  -H "Content-Type: application/json" \
  -H "Ocp-Apim-Subscription-Key: $AMD_LLM_API_KEY" \
  -d '{
    "model": "ibm-research/re2g-reranker-nq",
    "query": "What is machine learning?",
    "documents": [
      "Machine learning is a subset of AI.",
      "The weather today is sunny.",
      "Deep learning uses neural networks."
    ],
    "top_n": 3
  }'
```

## Response Formats

### Chat Completion (Claude)

```json
{
  "id": "msg_xxx",
  "type": "message",
  "role": "assistant",
  "content": [
    {
      "type": "text",
      "text": "Hello! How can I help you?"
    }
  ],
  "model": "claude-sonnet-4-5@20250929",
  "stop_reason": "end_turn",
  "usage": {
    "input_tokens": 10,
    "output_tokens": 25
  }
}
```

### Chat Completion (GPT)

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "model": "gpt-4",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! How can I help you?"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 25,
    "total_tokens": 35
  }
}
```

### Embeddings

```json
{
  "object": "list",
  "data": [
    {
      "object": "embedding",
      "index": 0,
      "embedding": [0.123, -0.456, ...]
    }
  ],
  "model": "jina-embeddings-v3",
  "usage": {
    "prompt_tokens": 5,
    "total_tokens": 5
  }
}
```

### Rerank

```json
{
  "id": "rerank--<uuid>",
  "results": [
    {
      "index": 2,
      "document": { "text": "Most relevant document text" },
      "relevance_score": 5.89
    },
    {
      "index": 0,
      "document": { "text": "Less relevant document text" },
      "relevance_score": -0.22
    }
  ],
  "meta": {
    "api_version": { "version": "1" }
  }
}
```

## Error Responses

| Status | Meaning | Solution |
|--------|---------|----------|
| 401 | Unauthorized | Check API key |
| 403 | Forbidden | Verify VPN connection |
| 404 | Not Found | Check model/endpoint name |
| 429 | Rate Limited | Reduce request frequency |
| 500 | Server Error | Retry with backoff |
| 503 | Service Unavailable | Gateway maintenance |
