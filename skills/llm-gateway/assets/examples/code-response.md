# Example Response: How to use claude-sonnet-4-5

## Setup

```bash
pip install anthropic
```

## Environment

```bash
export AMD_LLM_API_KEY=your_gateway_api_key
```

## Prerequisites

- AMD VPN connection required
- Valid API key from AMD LLM Gateway Portal

## Basic Usage

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
    model="claude-sonnet-4-5@20250929",
    max_tokens=1000,
    messages=[{"role": "user", "content": "Hello! Can you help me?"}]
)

print(response.content[0].text)
```

## Advanced Usage

```python
# With system message and streaming
import os
from anthropic import Anthropic

client = Anthropic(
    api_key="dummy",
    base_url="https://llm-api.amd.com/Anthropic",
    default_headers={
        "Ocp-Apim-Subscription-Key": os.getenv("AMD_LLM_API_KEY")
    }
)

# Streaming response
with client.messages.stream(
    model="claude-sonnet-4-5@20250929",
    max_tokens=1500,
    system="You are a helpful Python programming assistant.",
    messages=[
        {"role": "user", "content": "Write a function to calculate fibonacci numbers"},
        {"role": "assistant", "content": "I'll write a recursive fibonacci function for you."},
        {"role": "user", "content": "Now optimize it with memoization"}
    ]
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
```

## Capabilities

- Chat completion
- Streaming responses
- Tool/function calling
- Vision (image input)
- System messages

## Tips

- Use streaming for long responses to improve perceived latency
- Set appropriate `max_tokens` based on expected response length
- The model name includes version suffix for reproducibility

---
Ask me to 'validate claude-sonnet-4-5@20250929' if you want me to test this example.
