# AMD LLM Gateway - Authentication Setup

## Prerequisites

1. **AMD VPN Connection** - Gateway only accessible from AMD network
2. **API Key** - Obtain from AMD LLM Gateway Portal

Before configuring a client, determine whether the portal issued a **personal** or **application** key. Do not paste the key into chat or logs.

- A personal key uses only `Ocp-Apim-Subscription-Key`.
- An application key also requires `user: <calling user's AMD NTID>` on every request.

## Environment Configuration

### Required Environment Variable

```bash
export AMD_LLM_API_KEY=your_gateway_api_key
```

Set the variable only for the process or shell that needs it. Do not place the key in source control, chat, logs, or shared shell profiles. Production applications should use their established secret-management mechanism.

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
from openai import OpenAI

client = OpenAI(
    api_key="dummy",  # Required but not used
    base_url="https://llm-api.amd.com/openai/deployments/gpt-4o",
    default_headers={
        "Ocp-Apim-Subscription-Key": os.getenv("AMD_LLM_API_KEY")
    }
)
```

## Authentication Headers

| Header | Value | Purpose |
|--------|-------|---------|
| `Ocp-Apim-Subscription-Key` | Your API key | Authentication |
| `Content-Type` | `application/json` | Request format |
| `user` | Calling user's AMD NTID (application keys only) | Per-user attribution |

## Application-key identity

For a local validation test, prefer an explicit NTID:

```bash
export AMD_LLM_USER_NTID=your_amd_ntid
python3.10 scripts/main.py validate_model --model gpt-4o --key-type application
```

For a local test, `getpass.getuser()` can help discover the OS login name. Confirm that it is the tester's AMD NTID, then pass the confirmed value through `--ntid` or `AMD_LLM_USER_NTID`. The validator does not send an unconfirmed OS login automatically.

Production applications must put the actual calling user's AMD NTID in the `user` header. How an application authenticates its users, validates identity, or obtains the correct NTID is outside this Gateway reference skill's scope; use the application's established identity mechanism.

When a key declared personal receives 401/403, or HTTP 400 explicitly reports a missing/required `user`, `validate_model` retries once with the local-test NTID. If that succeeds, report that the key behaves like an application key and confirm its type in the portal. No key value or complete header set is logged.

## Troubleshooting

### "Unauthorized" Error
- Verify API key is correct
- Check whether the environment variable is set without printing its value
- Confirm whether the key is personal or application; application keys require `user: <AMD NTID>`
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
