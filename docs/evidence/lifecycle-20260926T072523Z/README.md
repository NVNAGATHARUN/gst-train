# RailSync simulated lifecycle replay

**Result: PASSED**

This is a separate-database backend replay using the explicit 21 September 2026 fixture clock. It is not current-data browser acceptance or the complete A–B–C–D judge demo.

## Verified results

- Actual solver status: OPTIMAL
- Completed requests: 2
- Simulated reservation released: True
- Railway control issued: False

## Recorded workflow

| Step | API result |
|---|---|
| /api/v1/maintenance-requests | 201 |
| /api/v1/maintenance-requests/f141a179-dc04-4815-92d6-49c7f7d79ae0/transitions | 200 |
| /api/v1/maintenance-requests/f141a179-dc04-4815-92d6-49c7f7d79ae0/transitions | 200 |
| /api/v1/planning-runs | 202 |
| /api/v1/maintenance-requests/f141a179-dc04-4815-92d6-49c7f7d79ae0/transitions | 200 |
| /api/v1/maintenance-requests/f141a179-dc04-4815-92d6-49c7f7d79ae0/transitions | 200 |
| /api/v1/maintenance-requests | 201 |
| /api/v1/maintenance-requests/6f440ab0-678e-41c6-a696-e3d1b1657a84/transitions | 200 |
| /api/v1/maintenance-requests/6f440ab0-678e-41c6-a696-e3d1b1657a84/transitions | 200 |
| /api/v1/planning-runs | 202 |
| /api/v1/validation-reports | 201 |
| /api/v1/plan-revisions/af017ad0-92bb-4a51-99ca-d2c11c562071/decisions | 201 |
| /api/v1/plan-revisions/af017ad0-92bb-4a51-99ca-d2c11c562071/execution-records | 201 |
| /api/v1/plan-revisions/af017ad0-92bb-4a51-99ca-d2c11c562071/execution-records | 201 |
| /api/v1/plan-revisions/af017ad0-92bb-4a51-99ca-d2c11c562071/execution-records | 201 |
| /api/v1/plan-revisions/af017ad0-92bb-4a51-99ca-d2c11c562071/execution-records | 201 |
| /api/v1/possession-releases | 201 |

Full inputs and API outputs are preserved in `lifecycle.json`. Synthetic observations are explicitly labeled and passed through real validation. Preview data was not cleared or changed.

Remaining: fresh-current-date UI walkthrough, same-snapshot comparison in this replay, S&T/competing-resource A–B–C–D scenario, deliberate validation failure and disruption/replan demonstration.