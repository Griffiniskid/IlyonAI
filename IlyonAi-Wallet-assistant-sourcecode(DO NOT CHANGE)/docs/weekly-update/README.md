# Weekly Update Handoff Pack

## Purpose

This document set is a handoff pack for another agent that will not have code access.

Its job is to explain this repository as a feature module and companion surface for the larger product that lives on another machine.

The most important framing rule is this:

- this repository is not the whole product
- this repository is an addition, expansion, and experimental feature layer around the broader project
- when this material is later used in a weekly update, it should be described as a new module or extension to the main project, not as a complete replacement for the main project

## Scope Guard

These documents describe only what is present in this repository.

They do not assume anything about the main codebase that exists on the other device.

If a future narrator or writer needs to merge this information into a single project-wide update, the safe framing is:

- the main project continues to exist elsewhere
- this codebase adds a new AI-driven wallet, DeFi, and browser-extension feature layer
- some features here are fully implemented, some are partially implemented, and some are groundwork for future work

## What Exists In This Repository

At a high level, this repository contains:

- a React main application that behaves like an AI-native DeFi control surface
- a Chrome extension package with popup, sidepanel, and background worker entry points
- a FastAPI backend that handles auth, chats, portfolio scanning, and AI-agent orchestration
- a large crypto-agent module that builds swap, bridge, staking, LP, transfer, and market-analysis responses
- a Solidity contract and deployment script for affiliate-fee logic on PancakeSwap Infinity / V4 style concentrated-liquidity pools
- early groundwork for BNB Greenfield-backed memory persistence

## Document Map

- `01-product-and-feature-dossier.md`
  - Product intent, user journeys, screens, features, UX behavior, and current implementation status.

- `02-technical-architecture-dossier.md`
  - Code structure, APIs, data model, integrations, runtime behavior, security caveats, and test coverage.

- `03-feature-matrix-and-demo-checklist.md`
  - Feature-by-feature inventory, implementation status, best demo candidates, and overclaim-prevention notes.

## How To Use This Pack

Use this pack in this order:

1. Read `01-product-and-feature-dossier.md` to understand what this module is trying to be from the product side.
2. Read `02-technical-architecture-dossier.md` to understand what is really implemented and how it works.
3. Use `03-feature-matrix-and-demo-checklist.md` as the final verification layer before turning any of this into a public-facing update or voiceover.

## Critical Communication Rules

When this repository is summarized for a weekly update, keep these distinctions explicit:

- Fully implemented: backend chat flow, wallet auth, multi-chain balance scan, structured transaction previews, EVM and Solana execution paths, chat persistence, bridge/stake/pool/yield routing.
- Partially implemented: extension sidepanel and popup, some marketing claims in UI copy, Greenfield memory status in the UI, broader ecosystem messaging around integrations.
- Standalone but not yet integrated into the user app: the PancakeSwap affiliate hook contract and the Greenfield storage service.

## Short Summary

If someone needs a one-paragraph orientation before reading the rest:

This repository adds an AI-driven DeFi companion module to the wider project. It includes a polished React app, a browser-extension shell, a FastAPI backend, wallet authentication for MetaMask and Phantom, persistent chat history, multi-chain portfolio scanning, AI-assisted swap and bridge preparation, staking and liquidity discovery, and a separate smart-contract track for affiliate-fee routing. It is strongest today as a conversational DeFi execution layer and weakest in the popup/sidepanel polish, Greenfield wiring, and production-hardening details.
