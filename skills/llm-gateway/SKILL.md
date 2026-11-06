---
name: llm-gateway
description: Conversational AI skill for AMD's LLM Gateway - answers 'How do I use
  [model]?' questions with validated, working code examples. Use when you need to
  interact with or get help using LLM models through AMD's gateway.
license: Copyright © Advanced Micro Devices, Inc., or its affiliates. All rights reserved.
  Portions of this content consists of AI generated content.
metadata:
  author: ctung
  version: "1.0.1"
  category: infrastructure
  tags:
  - llm
  - api
  - gateway
  - ml
  - ai
  - code-generation
  compliance_scan:
    status: PASSED
    risk_score: 24
    risk_level: LOW
    scan_date: '2026-03-10T04:40:08.083830+00:00'
compatibility:
  universal: true
---
# AMD LLM Gateway Usage Skill

A conversational AI skill that helps you use AI models through AMD's LLM Gateway.

## CRITICAL: Action-Based Responses

**When the user asks to "list models", "list available models", "show models", or similar:**

1. **DO NOT show code examples**
2. **DO NOT explain how to list models**
3. **Execute the script and return the output**

**When the user asks to "validate [model]" or "[model] not working":**

1. **Execute the validation script and return the output**

**When the user asks "how do I use [model]?":**
- Generate a code example (this is the only case where showing code is appropriate)

---

## Script Execution Instructions

**Universal instructions for all AI clients.**

Skills are installed to the project root via slai-marketplace. The script location is:

**Standard location:**
- `skills/llm-gateway/scripts/main.py`

**Execute the script:**

```bash
# List models
python3 skills/llm-gateway/scripts/main.py --action list

# Validate a model
python3 skills/llm-gateway/scripts/main.py --action validate --model <model_name>

# Troubleshoot connection
python3 skills/llm-gateway/scripts/main.py --action troubleshoot
```

**Auto-find and execute one-liner:**
```bash
SCRIPT=$(find skills -name "main.py" -path "*llm-gateway*" 2>/dev/null | head -1) && python3 "$SCRIPT" --action list
```

**If script not found:**
1. Check if skill is installed: `slai-marketplace list`
2. Install if missing: `slai-marketplace install llm-gateway`
3. Verify location: `find . -name "*llm-gateway*" -type d`

---

## Purpose

This skill solves a critical problem: **preventing Claude Code from downloading local models**. When you ask Claude Code to "parse text with an LLM", this skill ensures it uses AMD Gateway instead of downloading Hugging Face models locally.

## Universal Instructions

**IMPORTANT: For list/validate/troubleshoot requests, EXECUTE the script and return real results. Do NOT just show code.**

### Step 1: Analyze the Query

Identify what the user is asking about:

1. **Usage questions**: "How do I use [model]?" → Generate code example
2. **Validation requests**: "Validate [model]" or "[model] isn't working" → **RUN the validation script**
3. **Discovery questions**: "What models are available?" or "list models" → **RUN the list script**
4. **Troubleshooting**: "Gateway not working" or connection issues → **RUN diagnostics**

### Step 1a: Execute Scripts for Live Data

For requests that need live data from the gateway, **execute the script and return results**.

The script is located at `scripts/main.py` relative to this skill's installation directory.

**Commands to execute:**
```bash
# List available models
python3 scripts/main.py --action list

# Validate a model
python3 scripts/main.py --action validate --model <model_name>

# Troubleshoot connection
python3 scripts/main.py --action troubleshoot
```

**Do NOT just show code examples for list/validate/troubleshoot requests. Actually run the script and show the user the real results.**

See the **Client-Specific Instructions** section below for exact paths per client.

### Step 2: Determine the Model Provider

Match the model name to its provider:

| Pattern | Provider | SDK | Endpoint |
|---------|----------|-----|----------|
| `claude-*` | anthropic | `anthropic` | `/Anthropic` |
| `gpt-*`, `o1-*` | openai | `openai` | `/openai/deployments/{deployment}` |
| `gemini-*` | google | `openai` | `/vertex/gemini/deployments/{model}` |
| `jina-*`, `sentence-*` | onprem | `openai` | `/api/OnPrem/deployments/{model}` |
| `*rerank*` | onprem | `urllib`/`fetch` | `/OnPrem/rerank` |

**OpenAI Deployment Pattern:**
- Base URL: `https://llm-api.amd.com/openai/deployments/{deployment-id}`
- **Deployment IDs are discovered dynamically** from the `/models` endpoint
- The SDK automatically appends `/chat/completions?api-version=2024-02-01`

**Dynamic Discovery:**
The skill fetches deployment IDs from `https://llm-api.amd.com/models` which returns:
```json
{"model": "gpt-4o", "id": "pdue-aoai-004-gpt4o", ...}
```
Where `id` is the deployment ID to use in the URL. This ensures the correct deployment is always used.

### Step 3: Generate the Response

For **usage questions**, generate a complete code example:

```python
# For Claude models
import os
from anthropic import Anthropic

client = Anthropic(
    api_key="dummy",
    base_url="https://llm-api.amd.com/Anthropic",
    default_headers={
        "Ocp-Apim-Subscription-Key": os.getenv("AMD_LLM_API_KEY")
    }
)

response = client.messages.create(
    model="claude-sonnet-4-5@20250929",
    max_tokens=1000,
    messages=[{"role": "user", "content": "Hello!"}]
)

print(response.content[0].text)
```

```python
# For GPT models (deployment ID discovered from /models endpoint)
import os
from openai import OpenAI

# Get API key from environment
api_key = os.getenv("AMD_LLM_API_KEY")

# The deployment ID comes from the /models endpoint
# e.g., {"model": "gpt-4o", "id": "pdue-aoai-004-gpt4o"}
# Use the 'id' field as the deployment in the URL
deployment_id = "pdue-aoai-004-gpt4o"  # Discovered from /models

client = OpenAI(
    base_url=f"https://llm-api.amd.com/openai/deployments/{deployment_id}",
    api_key="dummy-key-not-used",  # AMD Gateway uses header authentication
    default_headers={
        "Ocp-Apim-Subscription-Key": api_key
    }
)

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"}
    ]
)

print(response.choices[0].message.content)
```

```python
# For Gemini models (using OpenAI SDK with Vertex endpoint)
import os
from openai import OpenAI

# Get API key from environment
api_key = os.getenv("AMD_LLM_API_KEY")

# Gemini uses /vertex/gemini/deployments/{model} with OpenAI-compatible format
client = OpenAI(
    base_url="https://llm-api.amd.com/vertex/gemini/deployments/gemini-2.5-pro",
    api_key="dummy-key-not-used",  # AMD Gateway uses header authentication
    default_headers={
        "Ocp-Apim-Subscription-Key": api_key
    }
)

response = client.chat.completions.create(
    model="gemini-2.5-pro",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"}
    ]
)

print(response.choices[0].message.content)
```

```javascript
// For Claude models (JavaScript/Node.js)
import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic({
  apiKey: "dummy",
  baseURL: "https://llm-api.amd.com/Anthropic",
  defaultHeaders: {
    "Ocp-Apim-Subscription-Key": process.env.AMD_LLM_API_KEY,
  },
});

const response = await client.messages.create({
  model: "claude-sonnet-4-5@20250929",
  max_tokens: 1000,
  messages: [{ role: "user", content: "Hello!" }],
});

console.log(response.content[0].text);
```

```typescript
// For GPT models (TypeScript)
import OpenAI from "openai";

const deploymentId: string = "pdue-aoai-004-gpt4o"; // From /models endpoint

const client = new OpenAI({
  baseURL: `https://llm-api.amd.com/openai/deployments/${deploymentId}`,
  apiKey: "dummy-key-not-used",
  defaultHeaders: {
    "Ocp-Apim-Subscription-Key": process.env.AMD_LLM_API_KEY,
  },
});

async function main(): Promise<void> {
  const response = await client.chat.completions.create({
    model: "gpt-4o",
    messages: [
      { role: "system", content: "You are a helpful assistant." },
      { role: "user", content: "Hello!" },
    ],
  });

  console.log(response.choices[0].message.content);
}

main();
```

For **validation requests**, execute `scripts/main.py --action validate --model <model>` and return the actual results.

For **discovery questions** (list models), execute `scripts/main.py --action list` and return the actual model list.

### Step 4: Include Setup Instructions

Always include:

1. **Environment setup**:
   ```bash
   export AMD_LLM_API_KEY=your_gateway_api_key
   ```

2. **Dependencies**:
   ```bash
   # Python
   pip install anthropic openai

   # JavaScript/TypeScript
   npm install openai @anthropic-ai/sdk
   ```

3. **Prerequisites**:
   - AMD VPN connection required
   - Valid API key from AMD LLM Gateway portal

## Examples

### Input Example: Usage Question

```json
{
  "query": "How do I use claude-sonnet-4-5?",
  "action": "usage",
  "output_format": "markdown"
}
```

### Output Example: Usage Response

```markdown
# How to use Claude Sonnet 4.5

## Setup
pip install anthropic

## Environment
export AMD_LLM_API_KEY=your_gateway_api_key

## Code
[Complete Python example with client setup and API call]

## Tips
- Use streaming for long responses
- Set appropriate max_tokens
```

### Input Example: Validation

```json
{
  "query": "Validate claude-sonnet-4-5",
  "action": "validate"
}
```

### Output Example: Validation

```markdown
## Validation Results for claude-sonnet-4-5

- Model found and accessible
- Response time: 1247ms
- Capabilities: chat, streaming, tool_use
- Status: PASS
```

## Client-Specific Instructions

### For Claude Code / Cline (MCP Integration)

When the user asks about using LLMs or AI models:
1. Check if they're asking about AMD Gateway models
2. Use this skill to generate AMD Gateway code instead of local model code
3. Prevent suggestions to download transformers or local models

### For Cursor (Agent Skills)

Triggers automatically when detecting:
- Questions about LLM usage
- Model names (claude, gpt, gemini)
- API integration questions

### For Copilot (VS Code Extension)

Access via Command Palette: `AMD SLAI: LLM Gateway Usage`

## Notes

- All examples use official SDKs (anthropic, openai, google-generativeai) - never AMD wrapper libraries
- Tool/function calling is fully supported through these endpoints
- O1 models use `max_completion_tokens` instead of `max_tokens`
- Embedding models use the embeddings API, not chat completions
- **Rerank models** use `POST /OnPrem/rerank` with `{model, query, documents, top_n}` — no SDK wrapper needed, use raw HTTP
- **OpenAI/GPT models use deployment-specific URLs**: `/openai/deployments/{deployment-id}`
  - Deployment IDs are discovered dynamically from the `/models` endpoint
  - The SDK automatically appends `?api-version=2024-02-01`
- OnPrem embeddings (jina, sentence-transformers) use `/api/OnPrem/deployments/{model}`
- Authentication uses `Ocp-Apim-Subscription-Key` header, not the `api_key` parameter

## Alternative: SLAI.Models (Slodels)

For a simpler interface, you can use **SLAI.Models (Slodels)** - a lightweight LLM provider that auto-routes to the appropriate SDK based on the model name.

**Documentation**: https://amd.atlassian.net/wiki/spaces/SLA/pages/1031343395/SLAI.Models+Slodels+-+Lightweight+LLM+Provider+OpenAI+Google+Anthropic+Python+SDK+via+AMD+LLM+Gateway

### How Slodels Works

Slodels automatically routes your request to the appropriate SDK (OpenAI or Anthropic) based on the model you specify. This simplifies client setup since you don't need to configure different base URLs or headers for each provider.

### Important: SDK Compatibility

**Slodels auto-selects the SDK, but your code must be compatible with that SDK's input/output format.**

- If you switch from an OpenAI model (e.g., `gpt-4o`) to an Anthropic model (e.g., `claude-sonnet-4-5`), you will need to refactor your code to use the Anthropic SDK's request/response format
- The inputs and outputs must match the auto-selected SDK's expectations
- This means changing models across providers is not a drop-in replacement

### When to Use Slodels vs Direct SDK

| Use Case | Recommendation |
|----------|----------------|
| Sticking to one provider (e.g., all Claude models) | Slodels - simpler setup |
| Frequently switching between providers | Direct SDK - more control over format |
| Rapid prototyping | Slodels - faster to get started |
| Production code with specific SDK features | Direct SDK - explicit configuration |

## Model Categories

Available models are fetched dynamically from the gateway. Use `--action list` to see current models.

Models are categorized by capability:
- **Chat/Text Generation**: Claude, GPT, Gemini, O1 models
- **Embedding Models**: Jina, text-embedding-ada, sentence-transformers
- **Vision Models**: Models with image input support (claude-sonnet, gpt-4-vision)
- **Rerank Models**: Cross-encoder rerankers for search relevance scoring (re2g-reranker-nq)

Common model shortcuts:
- `sonnet` → `claude-sonnet-4-5@20250929`
- `opus` → `claude-3-opus`
- `haiku` → `claude-3-haiku`
- `gemini` → `gemini-pro`
- `gpt4` → `gpt-4`

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Model not found | Check model name spelling, run "list models" |
| Connection failed | Verify AMD VPN connection and API key |
| Timeout errors | Check network, try simpler prompt |
| Wrong API response | Verify using correct SDK for model type |

## API Reference

For detailed API specifications, parameter documentation, and debugging API calls, refer to the official AMD LLM Gateway API documentation:

**https://llm.amd.com/api-details#api=amd-llm-webapi-prod**

Use this reference when:
- Searching for compatible API interfaces
- Debugging request/response parameters
- Understanding available endpoints and their schemas
- Troubleshooting authentication or payload issues
