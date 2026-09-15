# P1 measurement: skill context footprint

## Problem redefinition

The likely daily-cost bottleneck is not the number of skills alone. It is how much instruction and reference material becomes active for a request, how often overlapping material is loaded, and whether inactive skills impose measurable context cost.

## Hypothesis

A meaningful share of token/context cost may come from duplicated or unnecessarily broad skill material. Before changing skill content, measure active-context footprint separately from answer quality.

## Measurement matrix

Use a fixed corpus covering: one clearly matched skill, two near matches, ambiguous requests, multi-skill requests, and unrelated requests.

Record for each case:

- selected skills and false activations
- SKILL.md bytes/tokens loaded
- reference bytes/tokens loaded
- repeated-content ratio
- number of files read
- end-to-end tool/runtime steps
- task-success and actionable-next-step scores

Run each case three times and report median plus range. Keep the model/provider fixed when comparing variants.

## Ablation plan

Compare the current routing/context behavior against one change at a time:

1. current behavior
2. remove duplicate reference material only
3. narrow inactive reference loading only
4. change routing threshold only

Do not combine these changes in the same measurement.

## P1 gate

Proceed to production optimization only if a candidate materially reduces context footprint or tool work while preserving task success and routing precision. If the footprint is small relative to model/tool cost, reject this hypothesis and profile another stage.

This PR is measurement-only. It intentionally does not alter skill behavior.
