# Review standards

One rule for reviewing a change, with the mistake it comes from (2026-11-15). Its one home is `tools/brain/docs/rules.md` ("A test reaches the caller"); this page keeps its example for a reviewer.

## A test reaches the code that uses the change

Why: a test that pins only a new helper still passes when the caller never uses it.

Example: #131's test checked `healthCheckWorkerCount` but not that the coordinator passes its value to the health-check workers (both deleted since, #191). The test should have gone through the coordinator, or through the batch call it makes.
