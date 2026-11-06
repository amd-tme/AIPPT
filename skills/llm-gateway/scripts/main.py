#!/tool/pandora64/bin/uv run
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""
AMD LLM Gateway Usage Skill - Composable Functions

Provides JSON-based composable functions for AMD LLM Gateway operations.
Supports both direct calls and piping for composable workflows.

Usage Examples:
    # Direct usage - run script directly as executable
    skills/llm-gateway/scripts/main.py list_models
    skills/llm-gateway/scripts/main.py validate_model --model claude-sonnet-4-5
    skills/llm-gateway/scripts/main.py find_closest_match --target opus4.5

    # Piping workflows
    skills/llm-gateway/scripts/main.py list_models | skills/llm-gateway/scripts/main.py find_closest_match --target opus4.5
    echo '"gpt-4o"' | skills/llm-gateway/scripts/main.py validate_model
"""

import argparse
import json
import os
import re
import sys
import difflib
from typing import Any, Dict, List, Optional, Tuple

# =============================================================================
# Core Configuration
# =============================================================================
OPENAI_API_VERSION = "2024-02-01"
SKILL_ASSET_ID = "amd-slai/skills/llm-gateway"
REGISTRY_URL = os.getenv(
    "SLAI_REGISTRY_URL",
    "https://atlvcpdmapp02/slai-registry/api/v1"
)

# Global caches
_deployment_cache = {}
_deployment_cache_loaded = False
_model_metadata_cache = {}

# =============================================================================
# Core Data Functions (JSON Input/Output)
# =============================================================================

def list_models(include_debug: bool = False) -> Dict[str, Any]:
    """
    Return all available models categorized by type.

    Returns:
        JSON object with categorized model lists and metadata
    """
    try:
        models = fetch_models_from_gateway()

        if include_debug:
            # Include raw metadata for debugging
            models["_metadata"] = _model_metadata_cache

        return {
            "status": "success",
            "data": models
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "data": None
        }

def validate_model(model_name: str) -> Dict[str, Any]:
    """
    Validate that a model is accessible and working.

    Args:
        model_name: Name of the model to validate

    Returns:
        JSON object with validation results
    """
    import time
    import urllib.request
    import urllib.error

    api_key = os.getenv("AMD_LLM_API_KEY")
    if not api_key:
        return {
            "status": "error",
            "model": model_name,
            "error": "AMD_LLM_API_KEY environment variable not set",
            "suggestion": "Run: export AMD_LLM_API_KEY=your_api_key"
        }

    # Try to determine provider and build request - catch model not found errors
    try:
        # Populate metadata cache so is_rerank_model can check capabilities
        if not _model_metadata_cache:
            fetch_models_from_gateway()
        provider = determine_provider(model_name)
        is_embedding = is_embedding_model(model_name)
        is_rerank = is_rerank_model(model_name)
    except ValueError as e:
        # Model not found in deployment cache - provide enhanced suggestions
        result = {
            "status": "error",
            "model": model_name,
            "error": "Model not found",
            "suggestion": str(e)
        }

        # Try to fetch available models and suggest closest match
        try:
            available_models_dict = fetch_models_from_gateway()
            if available_models_dict:
                all_models = get_all_model_names(available_models_dict)
                closest_match = find_closest_match(model_name, all_models)

                result["available_models"] = available_models_dict
                if closest_match["status"] == "success":
                    result["suggested_model"] = closest_match["data"]["closest_match"]
                    result["suggestion"] = f"Model '{model_name}' not found. Did you mean '{closest_match['data']['closest_match']}'?"
                else:
                    result["suggestion"] = f"Model '{model_name}' not found. See 'available_models' for valid options."
            else:
                result["suggestion"] = f"Model '{model_name}' not found. Run 'list_models' to see available models."
        except Exception:
            result["suggestion"] = f"Model '{model_name}' not found. Run 'list_models' to see available models."

        return result

    # Build request based on model type
    try:
        if is_rerank:
            deployment_id = get_rerank_deployment_id(model_name)
            url = "https://llm-api.amd.com/OnPrem/rerank"
            payload = {
                "model": deployment_id,
                "query": "test query",
                "documents": ["test document"],
                "top_n": 1
            }
        elif is_embedding:
            if is_openai_embedding(model_name):
                base_url = get_openai_base_url(model_name)
                url = f"{base_url}/embeddings?api-version={OPENAI_API_VERSION}"
            else:
                import urllib.parse
                deployment_info = get_deployment_info_for_model(model_name)
                if deployment_info and deployment_info.get('OnPremLLM'):
                    deployment_id = deployment_info['OnPremLLM'][0]['id']
                else:
                    deployment_id = model_name
                encoded_id = urllib.parse.quote(deployment_id, safe='')
                url = f"https://llm-api.amd.com/api/OnPrem/deployments/{encoded_id}/embeddings"
            payload = {
                "input": ["test"],
                "model": model_name
            }
        elif provider == 'anthropic':
            url = "https://llm-api.amd.com/Anthropic/v1/messages"
            payload = {
                "model": model_name,
                "max_tokens": 10,
                "messages": [{"role": "user", "content": "Say 'ok'"}]
            }
        elif provider == 'google':
            url = f"https://llm-api.amd.com/vertex/gemini/deployments/{model_name}/chat/completions"
            payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": "Say 'ok'"}]
            }
        elif provider == 'onprem':
            import urllib.parse
            deployment_info = get_deployment_info_for_model(model_name)
            if deployment_info and deployment_info.get('OnPremLLM'):
                deployment_id = deployment_info['OnPremLLM'][0]['id']
            else:
                deployment_id = model_name
            encoded_id = urllib.parse.quote(deployment_id, safe='')
            url = f"https://llm-api.amd.com/api/OnPrem/openai/deployments/{encoded_id}/chat/completions"
            payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": "Say 'ok'"}]
            }
        else:  # openai
            base_url = get_openai_base_url(model_name)
            url = f"{base_url}/chat/completions?api-version={OPENAI_API_VERSION}"
            payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": "Say 'ok'"}]
            }

        headers = {
            "Content-Type": "application/json",
            "Ocp-Apim-Subscription-Key": api_key,
        }

        # Make the test call
        start_time = time.time()
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        with urllib.request.urlopen(req, timeout=30) as response:
            response_time_ms = int((time.time() - start_time) * 1000)

            # Determine capabilities
            capabilities = []
            if is_rerank:
                capabilities = ["rerank"]
            elif is_embedding:
                capabilities = ["embeddings"]
            elif provider == 'anthropic':
                capabilities = ["chat", "streaming", "tool_use"]
                if "claude-sonnet-4" in model_name or "claude-3" in model_name:
                    capabilities.append("vision")
            elif provider == 'google':
                capabilities = ["chat", "streaming", "tool_use"]
            elif provider == 'onprem':
                capabilities = ["chat"]
                if "code" in model_name.lower() or "starcoder" in model_name.lower():
                    capabilities.append("code_generation")
            else:
                capabilities = ["chat", "streaming"]
                model_lower = model_name.lower()
                if any(model_lower.startswith(prefix) for prefix in ["o1", "o3", "o4"]):
                    capabilities = ["chat", "reasoning"]
                elif "gpt-4" in model_name or "gpt-5" in model_name:
                    capabilities.append("tool_use")

            return {
                "status": "success",
                "model": model_name,
                "response_time_ms": response_time_ms,
                "provider": provider,
                "endpoint": url,
                "capabilities": capabilities,
                "message": "Model is accessible and responding"
            }

    except urllib.error.HTTPError as e:
        response_time_ms = int((time.time() - start_time) * 1000)
        error_body = ""
        try:
            error_body = e.read().decode("utf-8")
        except:
            pass

        if e.code == 404:
            result = {
                "status": "error",
                "model": model_name,
                "error": "Model not found",
                "http_code": e.code,
                "response_time_ms": response_time_ms,
                "suggestion": f"Model '{model_name}' may not exist."
            }

            # Try to fetch available models and suggest closest match
            try:
                available_models_dict = fetch_models_from_gateway()
                if available_models_dict:
                    all_models = get_all_model_names(available_models_dict)
                    closest_match = find_closest_match(model_name, all_models)

                    result["available_models"] = available_models_dict
                    if closest_match["status"] == "success":
                        result["suggested_model"] = closest_match["data"]["closest_match"]
                        result["suggestion"] = f"Model '{model_name}' not found. Did you mean '{closest_match['data']['closest_match']}'?"
                    else:
                        result["suggestion"] = f"Model '{model_name}' not found. See 'available_models' for valid options."
            except Exception:
                result["suggestion"] = f"Model '{model_name}' not found. Run 'list_models' to see available models."

            return result

        # Handle other HTTP errors
        error_messages = {
            401: ("Unauthorized", "Check your AMD_LLM_API_KEY is correct"),
            403: ("Forbidden", "Verify VPN connection and API key permissions"),
            429: ("Rate limited", "Too many requests. Wait and retry."),
            500: ("Server error", "Gateway internal error. Try again later."),
            503: ("Service unavailable", "Gateway may be under maintenance"),
        }

        error_name, suggestion = error_messages.get(e.code, (f"HTTP {e.code}", "Check gateway status"))

        return {
            "status": "error",
            "model": model_name,
            "error": error_name,
            "http_code": e.code,
            "response_time_ms": response_time_ms,
            "suggestion": suggestion,
            "details": error_body[:500] if error_body else None
        }

    except Exception as e:
        response_time_ms = int((time.time() - start_time) * 1000)
        return {
            "status": "error",
            "model": model_name,
            "error": str(e),
            "response_time_ms": response_time_ms,
            "suggestion": "Check network connectivity and API key"
        }

def find_closest_match(target_model: str, models: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Find the closest matching model name from available models.

    Args:
        target_model: Model name to find matches for
        models: Optional list of models to search. If None, fetches from gateway.

    Returns:
        JSON object with closest match results
    """
    if models is None:
        try:
            models_dict = fetch_models_from_gateway()
            models = get_all_model_names(models_dict) if models_dict else []
        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to fetch models: {e}",
                "target_model": target_model
            }

    if not models:
        return {
            "status": "error",
            "error": "No models available for comparison",
            "target_model": target_model
        }

    best_match = None
    best_ratio = 0.0
    target_lower = target_model.lower()

    matches = []
    for model in models:
        model_lower = model.lower()
        ratio = difflib.SequenceMatcher(None, target_lower, model_lower).ratio()

        # Boost score for substring matches
        if target_lower in model_lower:
            ratio = max(ratio, 0.8)

        matches.append({
            "model": model,
            "similarity": ratio
        })

        if ratio > best_ratio:
            best_ratio = ratio
            best_match = model

    # Sort matches by similarity
    matches.sort(key=lambda x: x["similarity"], reverse=True)

    result = {
        "status": "success",
        "target_model": target_model,
        "data": {
            "all_matches": matches[:10],  # Top 10 matches
            "best_similarity": best_ratio
        }
    }

    # Only return a match if it's reasonably similar (>40% match)
    if best_ratio > 0.4:
        result["data"]["closest_match"] = best_match
    else:
        result["data"]["closest_match"] = None

    return result

def get_usage_example(model_name: str, format_type: str = "python") -> Dict[str, Any]:
    """
    Generate a usage example for a specific model.

    Args:
        model_name: Name of the model
        format_type: Type of example ("python", "curl", "javascript", "typescript")

    Returns:
        JSON object with usage example
    """
    try:
        # Populate metadata cache so is_rerank_model can check capabilities
        if not _model_metadata_cache:
            fetch_models_from_gateway()
        provider = determine_provider(model_name)
        is_embedding = is_embedding_model(model_name)
        is_rerank = is_rerank_model(model_name)

        # Rerank models use a direct HTTP endpoint (no SDK wrapper)
        if is_rerank:
            deployment_id = get_rerank_deployment_id(model_name)
            generators = {
                "python": generate_rerank_python_example,
                "curl": generate_rerank_curl_example,
                "javascript": generate_rerank_javascript_example,
                "js": generate_rerank_javascript_example,
                "typescript": generate_rerank_typescript_example,
                "ts": generate_rerank_typescript_example,
            }
            gen = generators.get(format_type)
            if gen:
                return {
                    "status": "success",
                    "model": model_name,
                    "format": format_type if format_type not in ("js", "ts") else {"js": "javascript", "ts": "typescript"}[format_type],
                    "data": gen(model_name, deployment_id)
                }
            else:
                return {
                    "status": "error",
                    "error": f"Unsupported format: {format_type}. Supported: python, curl, javascript, typescript",
                    "model": model_name
                }

        if format_type == "python":
            return {
                "status": "success",
                "model": model_name,
                "format": "python",
                "data": generate_python_example(model_name, provider, is_embedding)
            }
        elif format_type == "curl":
            return {
                "status": "success",
                "model": model_name,
                "format": "curl",
                "data": generate_curl_example(model_name, provider, is_embedding)
            }
        elif format_type == "javascript" or format_type == "js":
            return {
                "status": "success",
                "model": model_name,
                "format": "javascript",
                "data": generate_javascript_example(model_name, provider, is_embedding)
            }
        elif format_type == "typescript" or format_type == "ts":
            return {
                "status": "success",
                "model": model_name,
                "format": "typescript",
                "data": generate_typescript_example(model_name, provider, is_embedding)
            }
        else:
            return {
                "status": "error",
                "error": f"Unsupported format: {format_type}. Supported: python, curl, javascript, typescript",
                "model": model_name
            }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "model": model_name
        }

# =============================================================================
# Helper Functions (Essential ones from original)
# =============================================================================

def fetch_models_from_gateway() -> Optional[Dict[str, List[str]]]:
    """Fetch available models from the gateway's /models endpoint."""
    import urllib.request
    import urllib.error

    api_key = os.getenv("AMD_LLM_API_KEY")
    if not api_key:
        return None

    try:
        url = "https://llm-api.amd.com/models"
        req = urllib.request.Request(
            url,
            headers={"Ocp-Apim-Subscription-Key": api_key},
            method="GET"
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            if isinstance(data, dict) and "data" in data:
                return categorize_models(data["data"])
            elif isinstance(data, dict) and "models" in data:
                return categorize_models(data["models"])
            elif isinstance(data, list):
                return categorize_models(data)
    except Exception:
        pass
    return None

def categorize_models(model_list: List[Any]) -> Dict[str, List[str]]:
    """Categorize models by type and capability."""
    chat_models = []
    embedding_models = []
    vision_models = []
    reasoning_models = []
    rerank_models = []

    for entry in model_list:
        if not isinstance(entry, dict):
            continue

        model_name = entry.get("model", "").strip()
        if not model_name:
            continue

        model_lower = model_name.lower()

        # Store metadata for provider detection
        _model_metadata_cache[model_lower] = entry

        # Categorize by capability (check Rerank capability flag first)
        capabilities = entry.get("capabilities", {})
        if capabilities.get("Rerank") or "rerank" in model_lower:
            rerank_models.append(model_name)
        elif any(embed_term in model_lower for embed_term in ["embed", "jina", "sentence", "text-embed"]):
            embedding_models.append(model_name)
        elif any(reasoning_term in model_lower for reasoning_term in ["o1", "o3", "o4"]):
            reasoning_models.append(model_name)
        elif is_vision_model(model_name):
            vision_models.append(model_name)
        else:
            chat_models.append(model_name)

    return {
        "chat_models": sorted(set(chat_models)),
        "embedding_models": sorted(set(embedding_models)),
        "vision_models": sorted(set(vision_models)),
        "reasoning_models": sorted(set(reasoning_models)),
        "rerank_models": sorted(set(rerank_models))
    }

def get_all_model_names(models_dict: Dict[str, List[str]]) -> List[str]:
    """Extract all model names from categorized models dict."""
    all_models = []
    for category_models in models_dict.values():
        all_models.extend(category_models)
    return list(set(all_models))

def is_vision_model(model_name: str) -> bool:
    """Check if model supports vision/image inputs."""
    model_lower = model_name.lower()
    vision_indicators = ["vision", "claude-sonnet-4", "claude-3", "gpt-4"]
    return any(indicator in model_lower for indicator in vision_indicators)

def determine_provider(model_name: str) -> str:
    """Determine provider from model metadata."""
    model_lower = model_name.lower()

    # Simple pattern matching for basic determination
    if model_lower.startswith("claude"):
        return "anthropic"
    elif model_lower.startswith("gpt") or model_lower.startswith("o1") or model_lower.startswith("o3") or model_lower.startswith("o4"):
        return "openai"
    elif model_lower.startswith("gemini"):
        return "google"
    elif any(term in model_lower for term in ["jina", "sentence", "text-embed", "rerank"]):
        return "onprem"
    else:
        return "openai"  # Default fallback

def is_rerank_model(model_name: str) -> bool:
    """Check if model is a reranker."""
    model_lower = model_name.lower()
    if "rerank" in model_lower:
        return True
    # Check metadata cache for Rerank capability flag
    cached = _model_metadata_cache.get(model_lower)
    if cached and isinstance(cached, dict):
        return cached.get("capabilities", {}).get("Rerank", False)
    return False

def get_rerank_deployment_id(model_name: str) -> str:
    """Get the deployment ID for a rerank model from metadata cache."""
    model_lower = model_name.lower()
    cached = _model_metadata_cache.get(model_lower)
    if cached and isinstance(cached, dict):
        return cached.get("id", model_name)
    return model_name

def is_embedding_model(model_name: str) -> bool:
    """Check if model is for embeddings."""
    model_lower = model_name.lower()
    return any(term in model_lower for term in ["embed", "jina", "sentence"])

def is_openai_embedding(model_name: str) -> bool:
    """Check if it's an OpenAI embedding model."""
    return "text-embed" in model_name.lower()

def get_openai_base_url(model_name: str) -> str:
    """Get OpenAI base URL for model (simplified version)."""
    # This is a simplified version - in production would use deployment cache
    deployment_id = f"deployment-{model_name.replace('.', '-')}"
    return f"https://llm-api.amd.com/openai/deployments/{deployment_id}"

def get_deployment_info_for_model(model_name: str) -> Optional[Dict[str, Any]]:
    """Query Gateway API for specific model deployment info (simplified)."""
    # Simplified version for composable architecture
    return None

def generate_python_example(model_name: str, provider: str, is_embedding: bool) -> Dict[str, str]:
    """Generate Python code example for a model."""
    if provider == "anthropic":
        code = f'''import os
from anthropic import Anthropic

client = Anthropic(
    api_key="dummy",
    base_url="https://llm-api.amd.com/Anthropic",
    default_headers={{
        "Ocp-Apim-Subscription-Key": os.getenv("AMD_LLM_API_KEY")
    }}
)

response = client.messages.create(
    model="{model_name}",
    max_tokens=1000,
    messages=[{{"role": "user", "content": "Hello!"}}]
)

print(response.content[0].text)'''

        setup = "pip install anthropic"

    elif provider == "google":
        code = f'''import os
from openai import OpenAI

client = OpenAI(
    base_url="https://llm-api.amd.com/vertex/gemini/deployments/{model_name}",
    api_key="dummy-key-not-used",
    default_headers={{
        "Ocp-Apim-Subscription-Key": os.getenv("AMD_LLM_API_KEY")
    }}
)

response = client.chat.completions.create(
    model="{model_name}",
    messages=[
        {{"role": "system", "content": "You are a helpful assistant."}},
        {{"role": "user", "content": "Hello!"}}
    ]
)

print(response.choices[0].message.content)'''

        setup = "pip install openai"

    else:  # openai
        code = f'''import os
from openai import OpenAI

# Get deployment ID from /models endpoint
deployment_id = "your-deployment-id"  # Replace with actual deployment ID

client = OpenAI(
    base_url=f"https://llm-api.amd.com/openai/deployments/{{deployment_id}}",
    api_key="dummy-key-not-used",
    default_headers={{
        "Ocp-Apim-Subscription-Key": os.getenv("AMD_LLM_API_KEY")
    }}
)

response = client.chat.completions.create(
    model="{model_name}",
    messages=[
        {{"role": "system", "content": "You are a helpful assistant."}},
        {{"role": "user", "content": "Hello!"}}
    ]
)

print(response.choices[0].message.content)'''

        setup = "pip install openai"

    return {
        "setup": setup,
        "environment": "export AMD_LLM_API_KEY=your_gateway_api_key",
        "code": code,
        "description": f"Python example for {model_name} using {provider} SDK"
    }

def generate_curl_example(model_name: str, provider: str, is_embedding: bool) -> Dict[str, str]:
    """Generate curl example for a model."""
    if provider == "anthropic":
        code = f'''curl -X POST "https://llm-api.amd.com/Anthropic/v1/messages" \\
  -H "Content-Type: application/json" \\
  -H "Ocp-Apim-Subscription-Key: $AMD_LLM_API_KEY" \\
  -d '{{
    "model": "{model_name}",
    "max_tokens": 1000,
    "messages": [
      {{"role": "user", "content": "Hello!"}}
    ]
  }}\''''
    else:
        code = f'''curl -X POST "https://llm-api.amd.com/openai/deployments/your-deployment-id/chat/completions?api-version=2024-02-01" \\
  -H "Content-Type: application/json" \\
  -H "Ocp-Apim-Subscription-Key: $AMD_LLM_API_KEY" \\
  -d '{{
    "model": "{model_name}",
    "messages": [
      {{"role": "system", "content": "You are a helpful assistant."}},
      {{"role": "user", "content": "Hello!"}}
    ]
  }}\''''

    return {
        "environment": "export AMD_LLM_API_KEY=your_gateway_api_key",
        "code": code,
        "description": f"curl example for {model_name}"
    }

def generate_javascript_example(model_name: str, provider: str, is_embedding: bool) -> Dict[str, str]:
    """Generate JavaScript code example for a model."""
    if provider == "anthropic":
        code = f'''import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic({{
  apiKey: "dummy",
  baseURL: "https://llm-api.amd.com/Anthropic",
  defaultHeaders: {{
    "Ocp-Apim-Subscription-Key": process.env.AMD_LLM_API_KEY,
  }},
}});

const response = await client.messages.create({{
  model: "{model_name}",
  max_tokens: 1000,
  messages: [{{ role: "user", content: "Hello!" }}],
}});

console.log(response.content[0].text);'''

        setup = "npm install @anthropic-ai/sdk"

    elif provider == "google":
        code = f'''import OpenAI from "openai";

const client = new OpenAI({{
  baseURL: "https://llm-api.amd.com/vertex/gemini/deployments/{model_name}",
  apiKey: "dummy-key-not-used",
  defaultHeaders: {{
    "Ocp-Apim-Subscription-Key": process.env.AMD_LLM_API_KEY,
  }},
}});

const response = await client.chat.completions.create({{
  model: "{model_name}",
  messages: [
    {{ role: "system", content: "You are a helpful assistant." }},
    {{ role: "user", content: "Hello!" }},
  ],
}});

console.log(response.choices[0].message.content);'''

        setup = "npm install openai"

    else:  # openai
        code = f'''import OpenAI from "openai";

// Get deployment ID from /models endpoint
const deploymentId = "your-deployment-id"; // Replace with actual deployment ID

const client = new OpenAI({{
  baseURL: `https://llm-api.amd.com/openai/deployments/${{deploymentId}}`,
  apiKey: "dummy-key-not-used",
  defaultHeaders: {{
    "Ocp-Apim-Subscription-Key": process.env.AMD_LLM_API_KEY,
  }},
}});

const response = await client.chat.completions.create({{
  model: "{model_name}",
  messages: [
    {{ role: "system", content: "You are a helpful assistant." }},
    {{ role: "user", content: "Hello!" }},
  ],
}});

console.log(response.choices[0].message.content);'''

        setup = "npm install openai"

    return {
        "setup": setup,
        "environment": "export AMD_LLM_API_KEY=your_gateway_api_key",
        "code": code,
        "description": f"JavaScript (ESM) example for {model_name} using {provider} SDK"
    }

def generate_typescript_example(model_name: str, provider: str, is_embedding: bool) -> Dict[str, str]:
    """Generate TypeScript code example for a model."""
    if provider == "anthropic":
        code = f'''import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic({{
  apiKey: "dummy",
  baseURL: "https://llm-api.amd.com/Anthropic",
  defaultHeaders: {{
    "Ocp-Apim-Subscription-Key": process.env.AMD_LLM_API_KEY,
  }},
}});

async function main(): Promise<void> {{
  const response = await client.messages.create({{
    model: "{model_name}",
    max_tokens: 1000,
    messages: [{{ role: "user", content: "Hello!" }}],
  }});

  console.log(response.content[0].text);
}}

main();'''

        setup = "npm install @anthropic-ai/sdk"

    elif provider == "google":
        code = f'''import OpenAI from "openai";

const client = new OpenAI({{
  baseURL: "https://llm-api.amd.com/vertex/gemini/deployments/{model_name}",
  apiKey: "dummy-key-not-used",
  defaultHeaders: {{
    "Ocp-Apim-Subscription-Key": process.env.AMD_LLM_API_KEY,
  }},
}});

async function main(): Promise<void> {{
  const response = await client.chat.completions.create({{
    model: "{model_name}",
    messages: [
      {{ role: "system", content: "You are a helpful assistant." }},
      {{ role: "user", content: "Hello!" }},
    ],
  }});

  console.log(response.choices[0].message.content);
}}

main();'''

        setup = "npm install openai"

    else:  # openai
        code = f'''import OpenAI from "openai";

// Get deployment ID from /models endpoint
const deploymentId: string = "your-deployment-id"; // Replace with actual deployment ID

const client = new OpenAI({{
  baseURL: `https://llm-api.amd.com/openai/deployments/${{deploymentId}}`,
  apiKey: "dummy-key-not-used",
  defaultHeaders: {{
    "Ocp-Apim-Subscription-Key": process.env.AMD_LLM_API_KEY,
  }},
}});

async function main(): Promise<void> {{
  const response = await client.chat.completions.create({{
    model: "{model_name}",
    messages: [
      {{ role: "system", content: "You are a helpful assistant." }},
      {{ role: "user", content: "Hello!" }},
    ],
  }});

  console.log(response.choices[0].message.content);
}}

main();'''

        setup = "npm install openai typescript @types/node && npx tsc --init"

    return {
        "setup": setup,
        "environment": "export AMD_LLM_API_KEY=your_gateway_api_key",
        "code": code,
        "description": f"TypeScript example for {model_name} using {provider} SDK"
    }

# =============================================================================
# Rerank Example Generators
# =============================================================================

def generate_rerank_python_example(model_name: str, deployment_id: str) -> Dict[str, str]:
    """Generate Python rerank example using urllib (no SDK needed)."""
    code = f'''import os
import json
import urllib.request

api_key = os.getenv("AMD_LLM_API_KEY")
url = "https://llm-api.amd.com/OnPrem/rerank"

payload = {{
    "model": "{deployment_id}",
    "query": "What is machine learning?",
    "documents": [
        "Machine learning is a subset of artificial intelligence.",
        "The weather today is sunny with a high of 75 degrees.",
        "Deep learning uses neural networks for pattern recognition.",
        "Python is a popular programming language."
    ],
    "top_n": 4
}}

headers = {{
    "Content-Type": "application/json",
    "Ocp-Apim-Subscription-Key": api_key,
}}

data = json.dumps(payload).encode("utf-8")
req = urllib.request.Request(url, data=data, headers=headers, method="POST")

with urllib.request.urlopen(req, timeout=30) as response:
    result = json.loads(response.read().decode())

# Results are sorted by relevance_score (descending)
for r in result["results"]:
    print(f"Score: {{r['relevance_score']:.4f}} | {{r['document']['text']}}")'''

    return {
        "setup": "# No extra dependencies needed (uses stdlib urllib)",
        "environment": "export AMD_LLM_API_KEY=your_gateway_api_key",
        "code": code,
        "description": f"Python rerank example for {model_name} (uses POST /OnPrem/rerank)"
    }

def generate_rerank_curl_example(model_name: str, deployment_id: str) -> Dict[str, str]:
    """Generate curl rerank example."""
    code = f'''curl -X POST "https://llm-api.amd.com/OnPrem/rerank" \\
  -H "Content-Type: application/json" \\
  -H "Ocp-Apim-Subscription-Key: $AMD_LLM_API_KEY" \\
  -d '{{
    "model": "{deployment_id}",
    "query": "What is machine learning?",
    "documents": [
      "Machine learning is a subset of artificial intelligence.",
      "The weather today is sunny.",
      "Deep learning uses neural networks for pattern recognition."
    ],
    "top_n": 3
  }}\''''

    return {
        "environment": "export AMD_LLM_API_KEY=your_gateway_api_key",
        "code": code,
        "description": f"curl rerank example for {model_name}"
    }

def generate_rerank_javascript_example(model_name: str, deployment_id: str) -> Dict[str, str]:
    """Generate JavaScript rerank example using fetch."""
    code = f'''const apiKey = process.env.AMD_LLM_API_KEY;

const response = await fetch("https://llm-api.amd.com/OnPrem/rerank", {{
  method: "POST",
  headers: {{
    "Content-Type": "application/json",
    "Ocp-Apim-Subscription-Key": apiKey,
  }},
  body: JSON.stringify({{
    model: "{deployment_id}",
    query: "What is machine learning?",
    documents: [
      "Machine learning is a subset of artificial intelligence.",
      "The weather today is sunny.",
      "Deep learning uses neural networks for pattern recognition.",
    ],
    top_n: 3,
  }}),
}});

const result = await response.json();

// Results are sorted by relevance_score (descending)
for (const r of result.results) {{
  console.log(`Score: ${{r.relevance_score.toFixed(4)}} | ${{r.document.text}}`);
}}'''

    return {
        "setup": "# No extra dependencies needed (uses built-in fetch)",
        "environment": "export AMD_LLM_API_KEY=your_gateway_api_key",
        "code": code,
        "description": f"JavaScript rerank example for {model_name} using fetch"
    }

def generate_rerank_typescript_example(model_name: str, deployment_id: str) -> Dict[str, str]:
    """Generate TypeScript rerank example using fetch."""
    code = f'''interface RerankResult {{
  index: number;
  document: {{ text: string }};
  relevance_score: number;
}}

interface RerankResponse {{
  id: string;
  results: RerankResult[];
  meta: {{ api_version: {{ version: string }} }};
}}

const apiKey: string = process.env.AMD_LLM_API_KEY!;

async function rerank(query: string, documents: string[], topN?: number): Promise<RerankResponse> {{
  const response = await fetch("https://llm-api.amd.com/OnPrem/rerank", {{
    method: "POST",
    headers: {{
      "Content-Type": "application/json",
      "Ocp-Apim-Subscription-Key": apiKey,
    }},
    body: JSON.stringify({{
      model: "{deployment_id}",
      query,
      documents,
      top_n: topN ?? documents.length,
    }}),
  }});

  return response.json() as Promise<RerankResponse>;
}}

// Usage
const result = await rerank(
  "What is machine learning?",
  [
    "Machine learning is a subset of artificial intelligence.",
    "The weather today is sunny.",
    "Deep learning uses neural networks for pattern recognition.",
  ],
  3
);

for (const r of result.results) {{
  console.log(`Score: ${{r.relevance_score.toFixed(4)}} | ${{r.document.text}}`);
}}'''

    return {
        "setup": "npm install typescript @types/node && npx tsc --init",
        "environment": "export AMD_LLM_API_KEY=your_gateway_api_key",
        "code": code,
        "description": f"TypeScript rerank example for {model_name} with typed interfaces"
    }

# =============================================================================
# CLI Interface for Composable Functions
# =============================================================================

def main():
    """Main CLI interface supporting both direct commands and piping."""
    if len(sys.argv) < 2:
        print_help()
        sys.exit(1)

    command = sys.argv[1]

    # Handle different commands
    try:
        if command == "list_models":
            result = handle_list_models()
        elif command == "validate_model":
            result = handle_validate_model()
        elif command == "find_closest_match":
            result = handle_find_closest_match()
        elif command == "get_usage_example":
            result = handle_get_usage_example()
        elif command == "help" or command == "--help":
            print_help()
            sys.exit(0)
        else:
            print(f"Error: Unknown command '{command}'", file=sys.stderr)
            print_help()
            sys.exit(1)

        # Output JSON result
        print(json.dumps(result, indent=2))

    except Exception as e:
        error_result = {
            "status": "error",
            "error": str(e),
            "command": command
        }
        print(json.dumps(error_result, indent=2), file=sys.stderr)
        sys.exit(1)

def handle_list_models():
    """Handle list_models command."""
    parser = argparse.ArgumentParser(description="List available models")
    parser.add_argument("--debug", action="store_true", help="Include debug metadata")

    # Parse remaining args (skip the command)
    args = parser.parse_args(sys.argv[2:])

    return list_models(include_debug=args.debug)

def handle_validate_model():
    """Handle validate_model command."""
    parser = argparse.ArgumentParser(description="Validate a model")
    parser.add_argument("--model", help="Model name to validate")

    # Parse command line args first
    args = parser.parse_args(sys.argv[2:])

    if args.model:
        # Use command line model
        model_name = args.model
    elif not sys.stdin.isatty():
        # Read JSON from stdin and extract model name
        try:
            pipe_data = json.loads(sys.stdin.read())
            if isinstance(pipe_data, str):
                model_name = pipe_data.strip()
            elif isinstance(pipe_data, dict) and "model" in pipe_data:
                model_name = pipe_data["model"]
            else:
                raise ValueError("Invalid pipe input format")
        except (json.JSONDecodeError, ValueError):
            return {
                "status": "error",
                "error": "Invalid JSON input from pipe. Expected string or object with 'model' field"
            }
    else:
        return {
            "status": "error",
            "error": "Model name required. Use --model <name> or pipe input."
        }

    return validate_model(model_name)

def handle_find_closest_match():
    """Handle find_closest_match command."""
    parser = argparse.ArgumentParser(description="Find closest matching model")
    parser.add_argument("--target", required=True, help="Target model name")

    args = parser.parse_args(sys.argv[2:])
    target_model = args.target

    # Check if model list is provided via pipe
    models = None
    if not sys.stdin.isatty():
        try:
            pipe_data = json.loads(sys.stdin.read())
            if isinstance(pipe_data, dict) and "data" in pipe_data:
                # From list_models output
                models = get_all_model_names(pipe_data["data"])
            elif isinstance(pipe_data, list):
                # Direct list of models
                models = pipe_data
        except (json.JSONDecodeError, ValueError):
            pass  # Fall back to fetching models ourselves

    return find_closest_match(target_model, models)

def handle_get_usage_example():
    """Handle get_usage_example command."""
    parser = argparse.ArgumentParser(description="Get usage example for model")
    parser.add_argument("--model", required=True, help="Model name")
    parser.add_argument("--format", choices=["python", "curl", "javascript", "js", "typescript", "ts"], default="python", help="Example format")

    args = parser.parse_args(sys.argv[2:])

    return get_usage_example(args.model, args.format)

def print_help():
    """Print help message."""
    print("""AMD LLM Gateway - Composable Functions

Usage:
    skills/llm-gateway/scripts/main.py <command> [options]

Commands:
    list_models                     List all available models
    validate_model --model <name>   Validate a specific model
    find_closest_match --target <name>  Find closest matching model
    get_usage_example --model <name>    Get usage example for model

Piping Examples:
    skills/llm-gateway/scripts/main.py list_models | skills/llm-gateway/scripts/main.py find_closest_match --target opus4.5
    echo '"gpt-4o"' | skills/llm-gateway/scripts/main.py validate_model
    skills/llm-gateway/scripts/main.py list_models | jq -r '.data.chat_models[]' | head -5

Options:
    --debug        Include debug information (for list_models)
    --format       Output format for get_usage_example:
                   python (default), curl, javascript/js, typescript/ts

Examples:
    # Get Python example (default)
    skills/llm-gateway/scripts/main.py get_usage_example --model claude-sonnet-4-5

    # Get JavaScript example
    skills/llm-gateway/scripts/main.py get_usage_example --model gpt-4o --format javascript

    # Get TypeScript example
    skills/llm-gateway/scripts/main.py get_usage_example --model gemini-2.5-pro --format typescript

Environment:
    AMD_LLM_API_KEY    Required API key for AMD LLM Gateway
""")

if __name__ == "__main__":
    main()