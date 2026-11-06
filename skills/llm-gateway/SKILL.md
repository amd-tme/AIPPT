---
name: llm-gateway
description: Conversational AI skill for AMD's LLM Gateway - answers 'How do I use
  [model]?' questions with validated, working code examples. Use when you need to
  interact with or get help using LLM models through AMD's gateway.
license: Copyright © Advanced Micro Devices, Inc., or its affiliates. All rights reserved.
  Portions of this content consists of AI generated content.
metadata:
  author: ctung
  version: "1.0.10"
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
    compliance_risk_score: 72
    waived_compliance_risk_score: 0
    risk_level: LOW
    scan_date: '2026-08-27T13:08:25.547446+00:00'
compatibility:
  universal: true
---
# AMD LLM Gateway Usage Skill

A conversational AI skill that helps you use AI models through AMD's LLM Gateway.

## CRITICAL: Action-Based Responses

**When the user asks to "list models", "list available models", "show models", or similar:**

1. Ask whether the key is personal or application if not already known; do not ask for the key value.
2. **DO NOT show code examples**
3. **DO NOT explain how to list models**
4. **Execute the script with `--key-type` and return the output**

**When the user asks to "validate [model]" or "[model] not working":**

1. Ask whether the key is personal or application if not already known; do not ask for the key value.
2. **Execute the validation script with `--key-type` and return the output**

**When the user asks "how do I use [model]?":**
- Ask whether the key is personal or application, then generate the matching code example (this is the only case where showing code is appropriate)

---

## Script Execution Instructions

**Universal instructions for all AI clients.**

Skills are installed to the project root via slai-marketplace. The script location is:

**Standard location:**
- `skills/llm-gateway/scripts/main.py`

**Execute the script:**

```bash
# List models
python3.10 skills/llm-gateway/scripts/main.py list_models --key-type <personal|application>

# Validate a model
python3.10 skills/llm-gateway/scripts/main.py validate_model --model <model_name> --key-type <personal|application>

# Closest match / usage example (see script --help)
python3.10 skills/llm-gateway/scripts/main.py find_closest_match --target <name> --key-type <personal|application>
python3.10 skills/llm-gateway/scripts/main.py get_usage_example --model <model_name> --key-type <personal|application>
```

**Runtime:** Use Python 3.10 or newer. Prefer `python3.10` explicitly because `python3` can resolve to older system interpreters on some platforms.

**`validate_model` behavior (Azure OpenAI):** The script calls **Chat Completions** first (`.../deployments/{id}/chat/completions`). If the catalog marks the SKU as **Responses-only** (`capabilities.responses=true`, `capabilities.chat=false`), or Chat Completions returns **HTTP 400** with no deployment for Chat Completions, it retries **`POST /openai/responses`** with **`api-version=2025-03-01-preview`**. Successful checks include **`api_surface`** (`chat_completions` implied when absent, or **`responses`** when validated via the Responses API).

**Auto-find and execute one-liner:**
```bash
SCRIPT=$(find skills -name "main.py" -path "*llm-gateway*" 2>/dev/null | head -1) && python3.10 "$SCRIPT" list_models --key-type personal
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
python3.10 scripts/main.py list_models --key-type <personal|application>

# Validate a model
python3.10 scripts/main.py validate_model --model <model_name> --key-type <personal|application> [--ntid <amd_ntid>]
```

**Do NOT just show code examples for list/validate/troubleshoot requests. Actually run the script and show the user the real results.**

See the **Client-Specific Instructions** section below for exact paths per client.

### Step 1b: Ask Which Key Type Is Being Used

Before generating an example or validating a request, ask: **“Is the AMD LLM Gateway key personal or application?”** Do not ask the user to paste the key.

- **Personal key:** send `Ocp-Apim-Subscription-Key`; the `user` header is not required.
- **Application key:** send the literal header `user: <calling user's AMD NTID>` on **every** gateway request, in addition to `Ocp-Apim-Subscription-Key`.
- **Local testing only:** `getpass.getuser()` may supply the NTID only after confirming the OS login name is the tester's AMD NTID. Prefer `--ntid` or `AMD_LLM_USER_NTID` for the validator.
- **Production:** supply the actual calling user's AMD NTID from the application's existing identity context. How the application authenticates users or obtains that NTID is outside this skill's scope.

If validation of a declared personal key returns 401/403, or HTTP 400 explicitly says the `user` field is missing or required, the validator retries exactly once with the local-test NTID. A successful retry means the key **behaves like an application key**; tell the user to confirm its type in the gateway portal. It is not definitive key-type discovery. Do not perform this retry for timeouts, 404, 409, 429, or 5xx responses.

See [Authentication Setup](references/authentication-setup.md) for the Gateway header contract and local testing guidance.

### Step 2: Determine the Model Provider

Match the model name to its provider and **API surface** (Chat Completions vs Responses vs other). Prefer the live `/models` metadata over name patterns: if `owned_by` is `OnPremLLM`, use the OnPrem routes even when the model name starts with `gpt-` (for example, `GPT-oss-120B`).

| Pattern | Provider | SDK | Primary path |
|---------|----------|-----|--------------|
| `claude-*` | anthropic | `anthropic` | `/Anthropic` |
| `gpt-*`, `o1-*`, `o3-*`, `o4-*` (chat-capable, Azure-owned) | openai | `openai` | `/openai/deployments/{catalog id}/...` (see below) |
| `owned_by=OnPremLLM` (including `GPT-oss-*`) | onprem | `openai` | `/api/OnPrem/openai/deployments/{catalog id}/chat/completions` |
| `*-codex*`, `codex-mini` when `responses: true` | openai | `openai` / HTTP | `/openai/responses` (not Chat Completions) |
| `gemini-*` | google | `openai` | `/vertex/gemini/deployments/{model}` |
| `jina-*`, `sentence-*` | onprem | `openai` | `/api/OnPrem/deployments/{model}` |
| `*rerank*` | onprem | `urllib`/`fetch` | `/OnPrem/rerank` |

### Deployment paths and API surfaces (Azure OpenAI via the gateway)

**Model catalog:** `GET https://llm-api.amd.com/models` returns a list of model objects. Each entry has an **`id`** (canonical name). Use that string everywhere the API expects a model or deployment **path segment**—the older `model` field name may not be present.

#### Chat Completions (typical `gpt-*` / `o-*` chat models)

- **Base URL (OpenAI SDK):** `https://llm-api.amd.com/openai/deployments/{deployment-segment}`
- **Path segment:** The **same value as the catalog `id`** (e.g. `gpt-4o`, `gpt-4.1`, `gpt-5`). The SDK appends `/chat/completions?api-version=2024-02-01` (or set `default_query` / client options to match your SKU).
- **Invalid patterns:** Do **not** synthesize names like `deployment-gpt-4o` or rewrite `gpt-4.1` → `gpt-4-1` for the URL—they do not match Azure deployments and return HTTP 400.
- **Hard-coded vendor strings:** Internal Azure resource names (e.g. `pdue-aoai-...`) from examples or other tenants are **not** portable; prefer the **`id`** from **your** `/models` response.

#### Responses API (Codex and other `responses: true`, `chat: false` models)

Catalog entries such as **`gpt-5-codex`**, **`gpt-5.1-codex`**, **`gpt-5.1-codex-max`**, **`codex-mini`** expose **Responses**, not Chat Completions under that id.

- **URL:** `POST https://llm-api.amd.com/openai/responses?api-version=2025-03-01-preview` (minimum **2025-03-01-preview**; older `api-version` values return BadRequest for Responses on this gateway).
- **Body:** JSON with **`model`** set to the catalog **`id`** and **`input`** per Azure OpenAI Responses. The gateway does **not** expose `.../openai/deployments/{id}/responses` as a working route here (404)—use the **global** `/openai/responses` URL.
- **Optional:** Some responses echo an internal deployment name (e.g. `dvue-aoai-001-gpt-5-codex`); using catalog **`id`** in **`model`** is preferred.

#### api-version and parameters

| Surface | Typical `api-version` | Notes |
|---------|----------------------|--------|
| Chat Completions | `2024-02-01` | Default for many GPT chat deployments |
| Some `o3-*` / newer chat SKUs | `2024-12-01-preview` or later | Follow error message if gateway rejects `2024-02-01` |
| Responses (Codex) | `2025-03-01-preview` or later | Required for `/openai/responses` |
| GPT-5–style chat | (same as Chat Completions for path) | Prefer **`max_completion_tokens`** when **`max_tokens`** is rejected |

### Step 3: Generate the Response

For **usage questions**, generate a complete code example:

The examples below show personal-key authentication. For an application key, also add `"user": authenticated_user_ntid` to `default_headers` (or `user: <NTID>` in raw HTTP). In production, the application is responsible for supplying the actual calling user's AMD NTID; obtaining or validating that identity is outside this skill's scope.

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
# For GPT chat models (Chat Completions)
import os
from openai import OpenAI

api_key = os.getenv("AMD_LLM_API_KEY")

# Path segment = catalog model id from GET https://llm-api.amd.com/models (field "id").
# Use that exact string—not "deployment-{name}" or dot-to-dash mangling.
deployment_segment = "gpt-4o"

client = OpenAI(
    base_url=f"https://llm-api.amd.com/openai/deployments/{deployment_segment}",
    api_key="dummy-key-not-used",
    default_headers={"Ocp-Apim-Subscription-Key": api_key},
)

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"},
    ],
)

print(response.choices[0].message.content)
```

```python
# For Codex / Responses-only models (capabilities.responses=true, chat=false on /models)
import json
import os
import urllib.request

url = "https://llm-api.amd.com/openai/responses?api-version=2025-03-01-preview"
payload = {"model": "gpt-5-codex", "input": "Reply with the single word: ok"}
req = urllib.request.Request(
    url,
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "Content-Type": "application/json",
        "Ocp-Apim-Subscription-Key": os.environ["AMD_LLM_API_KEY"],
    },
    method="POST",
)
with urllib.request.urlopen(req, timeout=120) as resp:
    body = json.loads(resp.read().decode("utf-8"))
print(body.get("output") or body)
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
// For GPT chat models (TypeScript / Chat Completions)
import OpenAI from "openai";

// Same string as catalog "id" from GET /models (e.g. gpt-4o), not deployment-{name}.
const deploymentSegment = "gpt-4o";

const client = new OpenAI({
  baseURL: `https://llm-api.amd.com/openai/deployments/${deploymentSegment}`,
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

For **validation requests**, execute `scripts/main.py validate_model --model <model> --key-type <personal|application>` and return the actual results.

For **discovery questions** (list models), execute `scripts/main.py list_models --key-type <personal|application>` and return the actual model list.

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
   - Python 3.10 or newer
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
- **Chat Completions (Azure OpenAI):** `POST /openai/deployments/{catalog-id}/chat/completions` — the **path segment** must be the **`id`** from `GET /models`, **not** synthetic names like `deployment-gpt-4o`
- **Responses (Codex):** `POST /openai/responses?api-version=2025-03-01-preview` with **`model`** = catalog **`id`** — **not** the Chat Completions deployment URL pattern
- OnPrem embeddings (jina, sentence-transformers) use `/api/OnPrem/deployments/{model}`
- Authentication uses `Ocp-Apim-Subscription-Key` header, not the `api_key` parameter
- Application keys additionally require `user: <calling user's AMD NTID>` on every request

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

Available models are fetched dynamically from the gateway. Run `list_models` (see script commands above) to see current models.

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
| Model not found | Check model name spelling, run `list_models` |
| HTTP 400 “deployment ... not found” on Chat Completions | Use catalog **`id`** as the **only** path segment after `/deployments/`; avoid `deployment-{name}`; confirm the model has **`chat: true`** on `/models` |
| Codex / `*-codex` fails on Chat Completions | Use **`POST /openai/responses`** with **`api-version=2025-03-01-preview`**, not `chat/completions` |
| Responses returns wrong `api-version` | Bump to **`2025-03-01-preview`** or later |
| `max_tokens` unsupported (GPT-5–class) | Use **`max_completion_tokens`** where required |
| Connection failed | Verify AMD VPN connection and API key |
| Personal key rejected, then succeeds with `user` | Key behaves like an application key; confirm in the gateway portal and send the actual calling user's NTID |
| Timeout errors | Check network, try simpler prompt |
| Wrong API response | Verify Chat Completions vs Responses vs Anthropic vs Vertex per `/models` capabilities |

## API Reference

For detailed API specifications, parameter documentation, and debugging API calls, refer to the official AMD LLM Gateway API documentation:

**https://llm.amd.com/api-details#api=amd-llm-webapi-prod**

Use this reference when:
- Searching for compatible API interfaces
- Debugging request/response parameters
- Understanding available endpoints and their schemas
- Troubleshooting authentication or payload issues
