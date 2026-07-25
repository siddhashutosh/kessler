# Space-Track reinstatement request — email draft

Send from your registered Space-Track email (siddhashutosh@gmail.com) to:
**admin@space-track.org** (cc: helpdesk if you have it). Suspensions are lifted
manually; a clear, honest note explaining the fix is what gets accounts back.

---

**Subject:** Request to reinstate account — automated login issue identified and fixed

Hello Space-Track team,

My account (username: siddhashutosh@gmail.com) was suspended, and I believe I understand
why. I run a small open-source, non-commercial conjunction-assessment project (KESSLER) that
reads the public `cdm_public` class. A bug in my client, combined with a server crash-restart
loop, caused it to **log in far too frequently** — it did not persist its session between
process restarts and re-authenticated on every transient error, which created a burst of login
requests. This was entirely unintentional and I'm sorry for the load it placed on your service.

I have already corrected the client so this cannot happen again:

- The login session cookie is now **persisted to disk**, so process restarts reuse the existing
  session instead of re-authenticating.
- Logins are **hard-rate-limited to at most once per 30 minutes**.
- A **circuit breaker** now detects an authentication failure that persists after a fresh login
  and stops all requests for 24 hours instead of retrying.
- The overall data-refresh interval was increased to **once every 4 hours** (well within your
  documented limits of <30 requests/minute and <300/hour), and the tool is cache-first by design.

The service has been switched to an offline demo mode in the meantime and is making **no
requests** to Space-Track. I only use basic SSA data (`cdm_public`) with proper attribution to
Space-Track/USSPACECOM, and I'm happy to make any further changes you'd recommend.

Could you please reinstate the account when you have a chance? I'll re-enable live access only
after confirming everything complies with your API guidelines.

Thank you for the free service and for your time.

Best regards,
Ashutosh
siddhashutosh@gmail.com

---

## After reinstatement — how to safely go live again

1. On the VPS, edit `/opt/kessler/backend/.env` and **remove** the line `KESSLER_DEMO_MODE=true`
   (or set it to `false`).
2. `sudo systemctl restart kessler`
3. Watch the first cycle: `journalctl -u kessler -f` — you should see **one** login, then queries
   succeed; the circuit breaker stays closed. If you see a 401 after login, the circuit opens for
   24 h automatically and no storm occurs.

The hardened client makes at most ~6 logins/day and ~6 CDM fetches/day — orders of magnitude
below any limit.
