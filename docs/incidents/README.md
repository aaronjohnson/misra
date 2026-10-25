# Incidents

Episodes misra was built from or caught, each with its evidence (`facts.lp`, scrubbed
to the power readings), how the rules answered (`explain.png`, drawn by
`misra explain`), and the story. Re-run any of them: `misra explain <folder>/facts.lp`.
New ones start from a snapshot: `misra episode <snapshot> <slug>`.

| Date | Episode | Status | In short |
| --- | --- | --- | --- |
| 2026-10-17 | [battery-lost-after-hibernate](2026-10-17-battery-lost-after-hibernate/) | open | After a hibernate resume the firmware's battery and charger methods fail; the bar showed 0 % and 100 W charging. The case misra was built from. |
