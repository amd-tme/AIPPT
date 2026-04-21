The AMD LLM Gateway Usage Skill is a conversational AI assistant that helps developers
integrate with AMD's enterprise LLM Gateway infrastructure. It provides natural language
Q&A capabilities for questions like "How do I use claude-sonnet-4-5?" or "Show me code
for GPT-4" and responds with complete, validated Python code examples using official SDKs.

Key capabilities include smart model discovery with fuzzy matching (e.g., "sonnet-4.5"
finds "claude-sonnet-4-5@20250929"), automatic provider detection routing requests to
the correct endpoint (Anthropic for Claude, OpenAI for GPT, OnPrem for Jina embeddings),
and live validation testing to verify models are accessible and working correctly.

A critical feature is preventing Claude Code from downloading local models. When users
ask to "parse text with an LLM", this skill ensures AMD Gateway is used instead of
downloading multi-gigabyte Hugging Face models locally. It redirects text parsing,
embeddings, sentiment analysis, summarization, and entity extraction tasks to
appropriate gateway endpoints.

The skill supports all major model types: chat/text generation (Claude, GPT, Gemini, O1),
embedding models (Jina, Ada), and vision models. It generates provider-specific code
using the anthropic and openai Python SDKs with correct authentication headers, base URLs,
and model parameters. Special handling is included for O1 models (max_completion_tokens)
and embedding endpoints.

Tool stack: Python 3.9+, official Anthropic SDK for Claude models, official OpenAI SDK
for GPT models, requests library for gateway validation. Code examples use standard
environment variables for authentication and are designed to work with any Python
project without AMD-specific wrapper libraries.

Use this skill when integrating with AMD's AI infrastructure, needing LLM code examples,
validating model availability, or troubleshooting gateway connection issues.
