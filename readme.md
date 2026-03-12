# AI Terms & Conditions Analyzer and Change Tracker

An AI-powered web app and browser extension that helps users understand Terms & Conditions and Privacy Policies, track the versions they agreed to, and receive alerts when important terms change.

## Overview

Most users accept digital agreements without reading or understanding them. Even fewer notice when those agreements are updated later.

This project solves that problem by combining:

- AI-powered summarization of legal text
- version tracking of policies over time
- change detection for updated terms
- notifications when material changes occur

The platform is designed for:

- personal users
- enterprise users
- legal teams
- terms and conditions authors

## Core Features

- Analyze Terms & Conditions and Privacy Policies in plain language
- Highlight risky clauses such as:
  - auto-renewal
  - data sharing
  - arbitration
  - liability limitations
- Store the version of a policy a user agreed to
- Monitor tracked policies for changes
- Summarize what changed and why it matters
- Send alerts when material updates are detected

## Architecture

This project uses a microservices and event-driven architecture.

Main components include:

- React frontend
- Chrome/browser extension
- FastAPI backend services
- PostgreSQL (Supabase)
- Redis
- Kafka
- Cloudflare
- JWT authentication
- OpenTelemetry
- Sentry

## Development Workflow

- Use GitHub Issues for stories and tasks
- Use pull requests for all changes
- Follow the code style and naming convention docs
- Keep PRs small and linked to a story
- Make sure CI passes before merging

## Current Status

This project is currently in very early development.

## Documentation

See the `docs/` folder for:

- code style
- naming conventions

## Team Notes

This repository is structured to support both rapid MVP development and future enterprise scaling. The initial implementation may begin with simpler service boundaries, but the architecture is designed to evolve into a more complete event-driven system.
