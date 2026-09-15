# Skill Quality and Performance Baseline

## Problem redefinition

TaxueSkills is a multi-skill decision system. The relevant engineering question is not whether an individual SKILL.md is longer, shorter, or faster to load. The measurable objective is:

> Maximize useful decision progress per unit of model context and execution cost, while preserving routing correctness, reasoning quality, and actionable continuity.

Every future optimization should identify which part of that objective it improves.

## MECE decomposition

Evaluate the system across five independent dimensions:

1. **Routing**: trigger precision, false activation, missed skill cases, fallback behavior.
2. **Reasoning quality**: problem definition, evidence use, contradiction handling, decision quality.
3. **Context efficiency**: prompt size, duplicated instructions, unnecessary reads, output-to-token ratio.
4. **Workflow continuity**: whether a response reliably moves the user to the next useful action without forcing irrelevant steps.
5. **Reliability**: malformed inputs, ambiguous requests, missing context, conflicting skills, and regression behavior.

Do not treat prompt length or response length as standalone quality metrics.

## Measurement model

Maintain a fixed evaluation set covering:

- clear single-skill requests
- ambiguous requests
- boundary cases between adjacent skills
- adversarial or misleading wording
- incomplete user context
- multi-step workflows

Track at minimum:

- routing accuracy and false-positive activation rate
- task success rate
- actionable-next-step rate
- median and tail token consumption where measurable
- unnecessary skill activation/read rate
- regression rate against the fixed corpus

Compare distributions and deltas, not isolated examples.

## Optimization gate

A P1 optimization requires:

1. evidence that the target path is material
2. one explicit optimization hypothesis
3. an ablation or before/after comparison
4. unchanged behavior on unaffected cases
5. a quality gate for decision usefulness
6. a regression test added to the fixed corpus

For prompt or skill refactors, the smallest sufficient change should be preferred. Removing text is only a win when quality and coverage remain stable.

## Recommended experiment loop

`baseline -> profile -> hypothesis -> single-variable change -> ablation -> quality regression -> retain/revert`

This document establishes the measurement contract. Individual P1 changes should be submitted separately so their effect remains attributable and reversible.
