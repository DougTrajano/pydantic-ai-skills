---
name: text-utils
description: Utility skill for analysing and transforming plain text. Uses only the Python standard library — compatible with sandboxed (Pyodide) execution.
---

# Text Utils Skill

This skill provides basic text analysis and transformation scripts that run
exclusively on the Python standard library, making them safe to execute inside
a Pyodide/WASM sandbox.

## Skill Scripts

### word_count

Counts the words, lines, and characters in a piece of text.

**Named arguments:**

- `--text` (required): The text to analyse.

**Example output:**

```
Lines   : 3
Words   : 12
Chars   : 67
```
