# LLM Gateway Usage Response Template

When generating a usage response for a model, follow this structure:

## Response Format

```markdown
# How to use {MODEL_NAME}

## Setup

```bash
pip install {SDK_PACKAGE}
```

## Environment

```bash
export AMD_LLM_API_KEY=your_gateway_api_key
```

## Prerequisites

- AMD VPN connection required
- Valid API key from [AMD LLM Gateway Portal](https://llm-api.amd.com)

## Basic Usage

```python
{BASIC_CODE_EXAMPLE}
```

## Advanced Usage

```python
{ADVANCED_CODE_EXAMPLE}
```

## Capabilities

- {CAPABILITY_1}
- {CAPABILITY_2}

## Tips

- {TIP_1}
- {TIP_2}

---
Ask me to 'validate {MODEL_NAME}' if you want me to test this example.
```

## Provider-Specific Templates

### Claude Models (Anthropic SDK)

```python
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
    model="{MODEL_NAME}",
    max_tokens=1000,
    messages=[{"role": "user", "content": "Your prompt here"}]
)

print(response.content[0].text)
```

### GPT Models (OpenAI SDK)

```python
import os
import getpass
from openai import OpenAI

client = OpenAI(
    api_key="dummy",
    base_url="https://llm-api.amd.com/openai/deployments/{DEPLOYMENT_ID}",
    default_headers={
        "Ocp-Apim-Subscription-Key": os.getenv("AMD_LLM_API_KEY"),
        "user": getpass.getuser()
    }
)

response = client.chat.completions.create(
    model="{MODEL_NAME}",
    max_tokens=1000,
    messages=[{"role": "user", "content": "Your prompt here"}]
)

print(response.choices[0].message.content)
```

### O1 Models (Special Parameters)

```python
# O1 models use max_completion_tokens instead of max_tokens
response = client.chat.completions.create(
    model="o1-mini",
    max_completion_tokens=1000,  # Note: different parameter
    messages=[{"role": "user", "content": "Your prompt here"}]
)
```

### Embedding Models

```python
response = client.embeddings.create(
    input=["Text to embed"],
    model="{MODEL_NAME}"
)

embeddings = [data.embedding for data in response.data]
```
