# Development workflow

Every milestone follows the same gated loop:

1. Code the approved scope.
2. Run unit, integration, regression, and acceptance checks appropriate to the change.
3. Self-review correctness, data leakage, financial assumptions, failure handling,
   security, licensing, provenance, and the complete diff.
4. Pause with a `READY FOR REVIEW` report or a `BLOCKED` flag.
5. Address reviewer feedback through the same loop.
6. After approval, write the milestone closure document and close the task.

Starting another milestone requires explicit authorization. Closure documents belong in
`docs/milestones/` and record scope, decisions, changed files, test evidence, limitations,
approval date, and downstream dependencies.

