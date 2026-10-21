# V1rG0 (start here)

V1rG0 is highly experimental and designed to be much more careful with its decision making process; however, there is no guarantee it will generate money until it has been tested by multiple users and reliability can be assured.

It sends one task through several AI systems in turn (DeepSeek, Kimi, Mistral, Grok, Gemini). Each one adds its notes and picks who goes next, and DeepSeek reviews everything at the end. You get one readout file you can paste into any AI tool.

## What it costs

- We suggest **at most $5 per system key, $25 in total**.
- Spend limits are set **on each provider's own website**, not in V1rG0. For prepaid providers, only putting $5 of credit on the account is the limit.
- So far, one 7-call run cost about $0.02 in total.
- After every run, the summary file lists each system's tokens. If you fill in `V1rG0_specific/v1rg0_prices.json` from each provider's own pricing page, it also shows an estimated cost. V1rG0 never guesses prices.
- Honest note: nothing we tested reliably earns back $25 in the first month. Treat your first $25 as funding a test you can afford to lose.

## What stays with you

Your keys, your data and your run replies stay on your machine. Only the prompt goes to each provider. V1rG0 never gets its own keys or money, signs up for accounts, accepts terms, or drives agents by itself.

## Install

You need Python 3.10 or newer. In this folder, run:

`pip install -r requirements.txt`

## How to set your keys

1. Make a key on each provider's site (start with DeepSeek only):
   - DeepSeek: [DeepSeek API keys](https://platform.deepseek.com/api_keys)
   - Kimi: [Moonshot API keys](https://platform.kimi.ai/console/api-keys)
   - Mistral: [Mistral API keys](https://console.mistral.ai/api-keys)
   - Grok: [xAI console](https://console.x.ai)
   - Gemini: [Google AI Studio API keys](https://aistudio.google.com/app/apikey)
2. On that same site, set your $5 limit (or add only $5 of credit).
3. In the terminal you'll run V1rG0 from, set the key and a master password of your choice:
   - Mac or Linux: `export DEEPSEEK_API_KEY="your-key"` and `export V1RG0_MASTER_PW="any-password-you-pick"`
   - Windows PowerShell: `$env:DEEPSEEK_API_KEY="your-key"` and `$env:V1RG0_MASTER_PW="any-password-you-pick"`
4. The other names are `MOONSHOT_API_KEY` (Kimi), `MISTRAL_API_KEY`, `XAI_API_KEY` (Grok), `GEMINI_API_KEY` and `ANTHROPIC_API_KEY` (Claude).

These settings last until you close that terminal, so nothing is saved to disk.

### Where to keep your keys at first

- Keep each key in a password manager (or another safe place only you can open), and copy it into the terminal when you run V1rG0.
- Don't save keys in a file inside this folder, and never paste a key into a task file, a suit, or an AI chat.
- If a key ever leaks, delete it on the provider's site and make a new one.

You can also ask an agent to help you set your keys up securely. Ask your agent of choice what the risks of giving them the keys are so you understand them.

Only `deepseek` is switched on in `V1rG0_specific/v1rg0_providers.json` to start with.

## First run

1. Write your task in a text file, for example `my_task.md`.
2. Run DeepSeek only first:
   `python3 tools/route_chain.py --i-approve-this-run --task-file my_task.md --allow-systems deepseek`
3. Open `readout_route_<tag>.md` in the run folder (under `_prot_replies/route/`).
4. Add other systems one at a time once that works.

**About `--i-approve-this-run`:** this is the safety switch. Without it, V1rG0 refuses to make any paid call. Adding it means *you* have read the task and approve this one run. Without it, V1rG0 just prints a refusal and sends nothing.

## Suits

A suit is the role a system plays on a call. Every run starts with DeepSeek as **Plann.r** (`plann_r`), and the systems pick suits from there. The built-in suit ids are:

- `plann_r`: planner, turns the question into a clear structure and ordered steps (the start suit).
- `p_rot_ograph_r`: balance check.
- `drift_r`: alternatives when the main path fails or drifts.
- `explor_r`: maps how pieces connect.
- `remind_r`: lists the fixed points that must not drift.
- `blank`: no suit, a neutral prompt.

### Your own suits

To add yours, copy `V1rG0_specific/user_suits.example.json` to `user_suits.json` in the same folder and edit it. Your suits sit alongside the built-in ones.

If you'd rather use only yours, set `"use_only_my_suits": true` and set `start_suit` to one of your suit **ids** (the key, like `news_r`), not its display name (like `News.r`).

Since this IS an experimental system developed by a very small team, unknown errors will occur. Work with the agent(s) you have assigned to work on editing the system specifically to address them. We cannot provide help with this.

A bad suits file stops the run before any call, with a plain reason.

## Agents (optional)

See `tether/README.md`. Short version: keep the agent that changes V1rG0 separate from agents that do anything else, and never let them talk to each other.
