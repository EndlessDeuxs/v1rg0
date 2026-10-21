# Tethering an agent (optional)

You never have to use an agent. V1rG0 works fine by hand.

If you want one, there are only two folders:

- `tether/inbox/` is where an agent may drop a task file (plain text or markdown).
- `tether/outbox/` is where you copy a run's readout (`readout_route_<tag>.md`) for the agent to read.

## Steps

1. Pick an agent, or make a new one, that does **nothing else** (see Safety below).
2. Give it access to `tether/inbox/` (write) and `tether/outbox/` (read). Nothing else in this folder.
3. When it drops a task in `tether/inbox/`, read it yourself. If you're happy with it, run it:
   `python3 tools/route_chain.py --i-approve-this-run --task-file tether/inbox/<file>.md`
4. Copy the readout from the run folder into `tether/outbox/`.

The agent never starts a run. You do, every time.

Anything in `tether/outbox/` is opinion only. Check it before you act on it.

## Safety: keep agents apart

- The agent that changes your copy of V1rG0, including writing custom suits, must be its **own agent**.
- Don't use that agent for anything else: no email, no accounts, no browsing, no other projects.
- Any agent you use for outside work must **not** be able to touch your V1rG0 copy.
- These agents must **never talk to each other**: no shared chat, no shared folders, no passing messages.

This way, if an outside agent reads something bad in an email or a web page, it can't reach the agent that changes how V1rG0 works.
