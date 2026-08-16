# Archon

Archon is an AI-powered software architecture and codebase intelligence platform.

> **Principle:** Structure first. Intelligence second.

Archon parses source code to build a deterministic knowledge graph of your software architecture, then empowers an AI analyst to reason over that graph to answer complex architectural questions.

## Getting Started

1. Copy `.env.example` to `.env` and fill in your LLM API keys.
2. Run `docker-compose up -d --build`
3. Access the Archon Dashboard at `http://localhost:3000`

## Architecture

See [archon_architecture.md](archon_architecture.md) for the complete technical design.
