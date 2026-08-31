# Project Workflow Rules

## 1. Project State File
- Maintain a running state file (`PROJECT_STATE.md`) in the repo root.
- Update it after every completed step with:
  - What's been completed
  - What's in progress
  - Constraints
  - Decisions made (with rationale)
- Read this file before starting any new step. Do not proceed without reading it first.

## 2. Task Decomposition
- Before executing complex work, break it into discrete chunks of 5-7 steps.
- Write the chunk plan into the state file before starting execution.
- Do not execute steps that aren't part of a defined chunk.

## 3. Validation Checkpoints
- After completing each chunk, stop.
- Provide a summary: what was done, what changed, any open questions/risks.
- Wait for explicit approval before starting the next chunk.

## 4. Troubleshooting vs. Assumptions
- When debugging, either troubleshoot (gather evidence, test hypotheses) or state assumptions explicitly and proceed - never mix the two silently.
- If troubleshooting is incomplete, do not make assumptions to fill the gap without flagging it.

## 5. SOLID Programming Principles
- Always make sure code falls under the SOLID programming design principles.
