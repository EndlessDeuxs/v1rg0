# Where the review call is built, and how an image provider would fit (map only, live Phase 18)

## Review call: tools/route_chain.py
- REVIEW_ASK text: line 226.
- Review block: lines 479-502. Skip rules 483-488 (providers not restored / 6-call limit without long run / token cap).
- Prompt assembled 492-495 (preface + task + steps log + stop reason + replies + either YOUR TASK [--review-replaces-ask] or REVIEW QUESTION + REVIEW_ASK).
- Call made 497 via call(..., START_SYSTEM, start_suit, prompt, "review"); review_text set 500 only on PASS.
- After it: prices + readout 503-516 (cost_from_usage 153, write_readout 168). Flags in main() from 522.
- Natural hook: right after line 500, only when status == PASS, only if the new flag is on. Nothing in the routed loop (379-473) can reach it.

## How every chat call travels today
call()/_call() 311-355 -> oc.process_task (V1rG0_specific/v1rg0_orchestrator_core.py 359) -> suit_tx.transmit
(unvalidated/v1rg0_transmission_suit.py 179) -> _select_endpoint (same file 135; Mistral/Grok/Gemini in
V1rG0_specific/v1rg0_extra_providers.py 33-60) -> requests.post to a /chat/completions URL.
The gate reads the answer as choices[0].message.content (unvalidated/v1rg0_validation_gate.py 67-78).

## Why an image service should NOT go through that path
- The gate expects chat text; an image reply has none, so it would come back FAIL/EMPTY.
- Routing picks from `providers` in v1rg0_providers.json (built at route_chain 266, checked in check_route 110).
  Anything listed there is pickable by a routed step.
- load_provider_config (orchestrator_core 40) validates enabled_providers against `providers`.

## Suggested fit (for Daemonstra.tor's plan)
- Image providers in their own file, v1rg0_image_providers.json (team choice), so routing, enabled_providers and ProviderWindow never see them and the providers file stays 28f8f072.
- New small module (e.g. V1rG0_specific/v1rg0_image_provider.py) with its own post + response parsing.
- Called only from the review hook above, once, from the review's description block. Count kept in summary
  ("image": {calls, max 1, file, est_cost}); refuse a second call in code.
- Its own price entry (per image) beside the token prices in v1rg0_prices.json; cost_from_usage is token-only today.
- Binary save into run_dir needs a bytes writer; _write_new (140) is text-only and refuses overwrite (keep that rule).
- Readout: one line with the image path. Offline tests: mock the new module like transmit, keys unset.
- Still to confirm from xAI docs, not guessed here: image endpoint, model name, price per image, response format (URL vs base64).
