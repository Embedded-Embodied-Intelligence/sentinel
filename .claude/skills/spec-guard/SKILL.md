---
name: spec-guard
description: Handle ambiguity, contradiction or a needed change in docs/spec/model.md. Use whenever the implementation would require interpreting, deviating from or extending the formal model.
---

# Spec guard

`docs/spec/model.md` defines the semantics the papers describe. Silent deviations would make
the published method differ from the code. Therefore:

1. **Never edit `docs/spec/`** unless the WP prompt explicitly asks for it.
2. **Ambiguity** (spec allows several readings): choose the simplest reading that is easy to
   change later, isolate it in one function or parameter, mark it in code with
   `# SPEC-Q: <short question>`, and list it under "Spec questions" in the WP report with the
   reading used.
3. **Contradiction or impossibility** (spec cannot be implemented as written, or conflicts
   with data such as PSPLIB): stop that part of the task, implement the rest, and report it
   under "Spec questions" with evidence (e.g. a failing example). Do not invent a workaround
   that changes semantics.
4. **Extension** (something the spec does not cover, e.g. an implementation detail): decide,
   keep it local, and record it in the report's "Decisions"; use the `adr` skill if a reviewer
   would ask why.

The architect resolves spec questions and updates the spec in a later WP.
