# AI Inference Platform

A single-host, CPU-native AI inference serving platform compatible with OpenAI APIs.

## Overview

This platform provides a self-hosted alternative to proprietary LLM APIs, designed for deployment on local development machines or internal servers. It uses **Ollama** as the inference engine and adds a robust, production-ready gateway providing:

- **OpenAI Compatibility:** Drop-in replacement for OpenAI SDKs (`/v1/chat/completions`).
- **Multi-Tenancy:** Hardened isolation between organizations, users, and API keys.
- **RBAC:** Four-tiered access control (Super Admin, Org Admin, Team Lead, User).
- **Streaming:** Server-Sent Events (SSE) streaming of tokens.
- **Observability:** Prometheus metrics, Grafana dashboards, and structured JSON logs.
- **Admin UI:** React dashboard for managing users, keys, and tracking usage.

## Quickstart

See `specs/001-ai-inference-platform/quickstart.md` for a comprehensive step-by-step guide to running the platform locally in under 5 minutes.

## Operations and Maintenance

See `runbook.md` for instructions on performing key operational tasks like cold-starting the platform, swapping models, and rotating API keys.
