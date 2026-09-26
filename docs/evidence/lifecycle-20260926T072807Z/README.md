# Current-date SIMULATED lifecycle preview

Backend replay PASSED; CP-SAT OPTIMAL; 2 requests completed; software handback released simulated reservations.

Input dates were shifted before backend processing; no computed results were shifted or fabricated. Synthetic observation times use a controlled replay clock earlier today. The external API uses the real clock.

Separate backend: localhost:8001. Frontend must be started on port 3001 with RAILSYNC_API_ORIGIN pointing to port 8001. Existing preview on 3000/8000 is unchanged.

Demo-only fixture credentials: PLANNER (inspect), ENGINEERING (department), TRD (department), CONTROLLER (decisions/execution), AUDITOR (read). These fixed fixture credentials are for this local simulated database only.

Browser capture and interaction acceptance remain pending. This dataset contains already executed work for inspection, not a pending approval to repeat. The full A–B–C–D judge scenario remains open.
