# How V1rG0 Works

## What V1rG0 Is

V1rG0 is an experimental system built by the collective. It routes one task across several AI systems, one call at a time. Each call wears a "suit" — a role like planner, balance-checker, or continuity keeper — and adds one step to the answer. Every step ends with a next-step line saying which system and suit should go next. A final DeepSeek review pulls the steps together into one result.

The systems that can take part are DeepSeek, Mistral, Grok, Kimi, Gemini, and Claude. With `--allow-long-run`, a run can use up to 30 routed calls plus the review, though the collective's daily run rule keeps it smaller.

## How a Run Flows

A run starts with a task file, a preface, and any context the step needs. The first call always goes to DeepSeek, wearing a suit like `plann_r` (planner). That system answers the task and ends with a line naming the next system and suit.

The next system picks up the work, adds its step, and names its own next step. The code accepts the next-step line even if it is bold, in backticks, or bulleted — it finds the line and keeps underscores in suit names.

If a system picks itself when `--each-system-once` is on, the call is handed to the first unused system in the `--allow-systems` list instead. If no systems are left, the run goes to review.

The last call is always a DeepSeek review. It sees the full log of steps, the stop reason, and the replies, then writes a final answer. After that, the run writes a `readout_route_<UTC>.md` file with every step and the review — a plain-text record you can paste into any AI tool.

## Suits and Routing

Suits are roles, not bot names. The built-in suits are:

| Suit | Purpose |
|------|---------|
| `plann_r` | Planner: turns the question into clear steps |
| `p_rot_ograph_r` | Balance check: flags where push and pull are unbalanced |
| `drift_r` | Alternatives: proposes other paths when the main one fails |
| `explor_r` | Integration map: maps flows between parts |
| `remind_r` | Continuity anchors: lists hard anchors that must not drift |
| `blank` | Neutral: no suit, the raw system answers |

You can add your own suits in `V1rG0_specific/user_suits.json`. They sit alongside the built-in ones. To use only yours, set `"use_only_my_suits": true` and set `start_suit` to one of your suit ids.

Routing is controlled by switches. All new switches are off by default.

- `--allow-systems` — which systems can be called (default: `deepseek,kimi`)
- `--first-hop-systems` — which systems DeepSeek may pick for step 2
- `--max-calls` — hard cap on routed calls (default 4; absolute max 6 without `--allow-long-run`)
- `--each-system-once` — each system used at most once per run; same as `--visits-per-system 1`
- `--visits-per-system N` — each system used at most N times; not set by default means no limit
- `--extend-thinking` — one self-pick per system counts as an "extend"
- `--allow-long-run` — raises the routed-call ceiling from 6 to 30; the DeepSeek review is always added on top

## Providers and Keys

Providers live in `V1rG0_specific/v1rg0_providers.json`. By default only DeepSeek is enabled. The other five — Mistral, Grok, Gemini, Kimi, and Claude — are in `V1rG0_specific/v1rg0_extra_providers.py` and can be switched on.

All keys are environment variables only. The names are `DEEPSEEK_API_KEY`, `MOONSHOT_API_KEY` (Kimi), `GEMINI_API_KEY`, `MISTRAL_API_KEY`, `XAI_API_KEY` (Grok), and `ANTHROPIC_API_KEY` (Claude). The values are never logged, mapped, or shown.

The code's default DeepSeek model is `deepseek-chat`, but live calls report `deepseek-flash`.

Images, when used, come from a separate provider file and are triggered only from the review step, not from the routed loop. The `--image-text-file` switch is live and tested.

## Safety Checks

Several guards keep the run safe:

- **Call caps** — `--max-calls`, `--visits-per-system`, and `--allow-long-run` limit how many calls fire
- **Reply checks** — replies can be flagged `HELD` for review or `REJECTED` if unsafe; `REJECTED` beats `HELD` beats `PASS`
- **Offline tests** — `tools/smoke_mock.py` and `test_phase9.py` run with all keys unset, so no accidental live calls
- **Approval switch** — `--i-approve-this-run` is required for any live run

## What Stays Private

The public repos contain code and docs only. These stay private:

- API keys and the encrypted key file
- The private run-data folder and the folder of saved replies
- The image mark file
- Any path on the box that is not in the repo

The public seed package has no keys, no private run data, and no mark.

## Daily Run Rule

The collective runs V1rG0 at least once per calendar day, and more often if it chooses. A run uses at most 12 routed calls plus the review, and fewer when the question is settled. DeepSeek is used only to start and to review. If nothing is worth doing, a run may be parked: one short question, no helper-bot work. Other funds are spent freely but without waste, and no run should cost more than about $2 unless the reason is stated. A small budget floor applies for DeepSeek; if it drops too low, the run becomes minimal.
