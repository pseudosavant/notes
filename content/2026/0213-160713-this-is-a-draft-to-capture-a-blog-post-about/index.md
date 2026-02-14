---
title: "Agentic Product Management"
date: "2026-02-13"
draft: true
---

# Agentic Product Management: Designing for Context and Feedback

Most product work doesn’t fail because of bad ideas.  
It fails because context evaporates.

Specs stretch across days or weeks. Feedback lands asynchronously. Decisions get made in meetings, comments, side threads, PRs. When you come back to the work, the hardest part isn’t writing the next sentence. It’s reconstructing where you were and why.

That’s the problem agentic tools have quietly helped me solve, not by writing for me, but by helping me *resume* work with continuity.

## Why I don’t do this in ChatGPT

The obvious question is why not just use ChatGPT for all of this.

I do use it sometimes. But for ongoing product work, it breaks down quickly.

You end up copy-pasting context over and over. Specs. Comments. Tables. Screenshots. Schema notes. Every session starts with re-teaching the model what you already worked through yesterday. Local files are invisible. History is fragile.

ChatGPT is great for conversations.  
Agentic work needs a workspace.

I want the agent to see what I see: the repo, the specs, the notes, the artifacts, the patterns that already exist. I want to pick up work where I left off, not rehydrate it from memory every time.

## What I mean by agentic product management

When I say “agentic product management,” I’m not talking about handing decisions to an AI.

I mean designing an environment where an agent can:

- interrogate assumptions
- surface gaps
- validate ideas against real constraints
- maintain continuity across time

The agent isn’t the author. It’s a reviewer, a collaborator, a system that keeps asking “are you sure?” while having access to the same context I do.

## Markdown as the universal substrate

The backbone of all of this is Markdown.

It’s portable. Diffable. Easy to paste into tickets and docs. Easy for agents to reason about. Most importantly, it preserves structure.

Plaintext loses meaning. Tables collapse. Hierarchy disappears. Lists flatten. That structure matters. Those cues help models understand what’s important and how ideas relate.

Markdown ends up being a kind of universal substrate for agentic work.

## Designing for continuity

For each work item, I keep a simple Markdown file. Analysis, tradeoffs, open questions, notes from discussions. Nothing fancy.

When I come back to the work a day later, the agent reads that file and instantly knows where we were. What’s been decided. What’s unresolved. What assumptions are in play.

The agent never starts from zero, because I never do.

## Simple CLI tools as agent interfaces

Instead of deep integrations or complex frameworks, I build small command-line tools.

Each tool does one thing well and can be called by a human or an agent.

Some pull work items and comment threads. Some pull documentation. Some normalize content into Markdown. Some query data.

These tools are intentionally boring. Narrow. Composable.

Agents don’t need magical access to everything. They need reliable doors into the parts of the system that matter.

## Letting agents observe reality, safely

One of the most useful tools I’ve built is a read-only data query script.

The agent can propose a SQL query, run it against a dev database, and see what actually comes back. Guardrails matter here. Read-only access. Destructive commands blocked. Scoped credentials.

This changes the quality of work dramatically.

Specs stop being hypothetical. Assumptions get tested. Edge cases surface naturally. The agent can say, “I expected ten rows but got one. Something is off.”

Reasoning improves when the agent can verify reality instead of guessing.

This idea generalizes far beyond SQL. It could be any data store or API you already have access to, via a personal access token. Slack. Snowflake. Internal services. The specifics vary, but the pattern holds.

## Tight feedback loops beat perfect first attempts

LLMs don’t usually get things right on the first try. That’s not a failure, it’s a design constraint.

The goal isn’t perfect output. It’s fast iteration with good feedback.

When agents can check their work, inspect results, and adjust, they converge quickly. The loop tightens. Less time is spent correcting misunderstandings later.

Accuracy emerges from iteration, not brilliance.

## From writing to reviewing

This workflow changes how the work feels.

It’s less like writing from scratch and more like reviewing a PR. The agent produces a draft. I review it. I push back. I ask for changes. I refine tone and intent.

This is where human judgment matters most.

AI-written text can fall into an uncanny valley. Too polished. Too symmetrical. Technically correct but oddly inhuman. Iteration fixes that. Taste fixes that.

The agent accelerates typing. I own the meaning.

## Consistency through context awareness

One unexpected benefit is consistency.

Because the agent can see the codebase, localization files, existing UI patterns, it can answer questions like:

- Do we already have a string like this?
- How do we usually label buttons in this context?
- What patterns do we use on mobile vs desktop?

Instead of inventing new conventions, the work snaps into existing ones.

Consistency emerges when the agent can see the whole system.

## Composability is the real superpower

None of these tools are impressive on their own.

Markdown files. Small CLIs. Read-only queries. Local context.

Together, they create something powerful: maximal context and tight feedback loops.

That’s the heart of agentic work. Not prompts. Not magic. Environment design.

## A reference scaffold

To make this easier to adopt, I’m putting together a small open-source scaffolding repo that captures these patterns.

Astral uv setup. PEP 723 metadata. CLI conventions. Safety defaults. A README written for humans and agents.

Agents are much better at extending patterns than inventing them. A good reference gives them somewhere solid to start.

## The takeaway

Agentic work isn’t about letting AI think for you.

It’s about building an environment where systems can continuously review, question, and validate your thinking, while you stay fully accountable for the result.

Maximal context plus tight feedback loops turn agents from autocomplete into collaborators.

And once you feel that shift, it’s hard to go back.
