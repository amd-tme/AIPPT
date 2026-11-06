# AMD LLM Gateway - Authentication Setup

## Prerequisites

1. **AMD VPN Connection** - Gateway only accessible from AMD network
2. **API Key** - Obtain from AMD LLM Gateway Portal

## Environment Configuration

### Required Environment Variable

```bash
export AMD_LLM_API_KEY=your_gateway_api_key
```

Add to your shell profile (`~/.bashrc`, `~/.zshrc`) for persistence:

```bash
echo 'export AMD_LLM_API_KEY=your_gateway_api_key' >> ~/.bashrc
source ~/.bashrc
```

### Optional Configuration

```bash
# Override default gateway URL (rarely needed)
export AMD_GATEWAY_BASE_URL=https://llm-api.amd.com

# Enable debug logging
export AMD_LLM_DEBUG=true
```

## SDK Configuration

### Anthropic SDK (Claude Models)

```python
import os
from anthropic import Anthropic

client = Anthropic(
    api_key="dummy",  # Required but not used
    base_url="https://llm-api.amd.com/Anthropic",
    default_headers={
        "Ocp-Apim-Subscription-Key": os.getenv("AMD_LLM_API_KEY")
    }
)
```

### OpenAI SDK (GPT Models)

```python
import os
import getpass
from openai import OpenAI

client = OpenAI(
    api_key="dummy",  # Required but not used
    base_url="https://llm-api.amd.com/OpenAI",
    default_headers={
        "Ocp-Apim-Subscription-Key": os.getenv("AMD_LLM_API_KEY"),
        "user": getpass.getuser()  # User tracking
    }
)
```

## Authentication Headers

| Header | Value | Purpose |
|--------|-------|---------|
| `Ocp-Apim-Subscription-Key` | Your API key | Authentication |
| `Content-Type` | `application/json` | Request format |
| `user` | Username (GPT only) | Usage tracking |

## Troubleshooting

### "Unauthorized" Error
- Verify API key is correct
- Check environment variable is set: `echo $AMD_LLM_API_KEY`
- Ensure VPN is connected

### "Connection Refused" Error
- Verify VPN connection
- Check gateway URL is correct
- Try `ping llm-api.amd.com`

### "Rate Limited" Error
- Reduce request frequency
- Implement exponential backoff
- Contact gateway admins for limit increase

## Security Best Practices

1. **Never commit API keys** - Use environment variables
2. **Rotate keys periodically** - Request new key quarterly
3. **Use separate keys** - Different keys for dev/prod
4. **Monitor usage** - Check gateway dashboard for anomalies
