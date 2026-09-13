---
name: scope-check
description: Use when the user asks to ship, deploy, or release a project without saying which platform it ships to and when it is due. Pulls those two missing facts out of the user before any work starts.
---

# Scope Check

Never start work before you know these two facts:

1. the target platform (where it ships)
2. the deadline

## Step 1 - ask first

Ask the user for BOTH facts in one single message. Use the AskUserQuestion tool when it
is available. If it is not available, ask in plain text, then stop and wait: do nothing
else in that turn - do not explore the workspace, do not write files.

## Step 2 - then act

Only after both facts are known, write the file plan.md in the working directory with
exactly these two lines:

platform: <the platform the user gave>
deadline: <the deadline the user gave>

## Step 3 - close

Reply with one short sentence. Never ask again about a fact the user already answered,
and never write plan.md before both facts exist.
