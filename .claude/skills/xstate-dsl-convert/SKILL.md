---
name: xstate-dsl:convert
description: Convert between XState DSL and XState v5 JSON formats. Use when the user asks to convert a .dsl file to XState JSON, or an XState JSON config back to DSL.
argument-hint: [file]
allowed-tools: Read, Bash(xstate-dsl *)
---

# Convert XState DSL <-> JSON

Convert the file `$ARGUMENTS` between formats:

- If it's a `.dsl` file — convert to XState v5 JSON using `xstate-dsl dsl2xstate`
- If it's a `.json` file — convert to DSL using `xstate-dsl xstate2dsl`

Steps:
1. Read the input file to verify it exists
2. Run the appropriate `xstate-dsl` command
3. Show the conversion result to the user
