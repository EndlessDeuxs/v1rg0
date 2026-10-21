# Where providers get registered (map for the Anthropic/Claude adapter; live code after Phase 20b)
Key: env var ANTHROPIC_API_KEY only. Never echo, log or map its value.

## 1. Providers file: V1rG0_specific/v1rg0_providers.json (hash 28f8f072)
- "providers": {name: {model_ids, role, env_key}}; "enabled_providers": ["deepseek"]; "judge_model": "deepseek_chat".
- A new "claude" entry (e.g. model_ids ["claude_..."], env_key ANTHROPIC_API_KEY) changes the hash; propose, don't edit in place.
- Read by: route_chain line 266 (system -> model_ids[0]), orchestrator_core load_provider_config line 40 (model_to_provider, allowlist), check_provider ~63 (refuses disabled).
- ProviderWindow (route_chain 47-80) switches a system on only for its own call, only if in --allow-systems (default "deepseek,kimi", line 608).

## 2. Endpoint registry (two layers)
- unvalidated/v1rg0_transmission_suit.py _select_endpoint line 135: deepseek_chat, kimi_k2_6.
  Gate at its top: provider_family(model_id) must return a family from CHAT_COMPLETIONS_FAMILIES (line 10).
  "claude"/"anthropic" is NOT in that list, so a claude model_id returns None before any registry lookup.
- V1rG0_specific/v1rg0_extra_providers.py _select_endpoint line 33: mistral, grok, gemini. All share
  Authorization: Bearer headers and _format_openai_prompt (lines 60-62). This is the natural home for Claude,
  but it needs its own headers and format_fn, not the shared OpenAI ones.
- Keys: EXTRA_ENV_KEYS (extra_providers line 9) maps model_id -> env var; add ANTHROPIC_API_KEY there.

## 3. Anthropic differences the adapter must handle
- URL https://api.anthropic.com/v1/messages (confirm from Anthropic docs).
- Headers: x-api-key (transmit line 187 already supports it) plus anthropic-version (no code sets it today).
- Request: _format_claude_prompt already exists (transmission_suit line 155: system + messages + max_tokens). Unused so far.
- Reply text: validation_gate extract_content line 71 already reads content[0].text when "claude" is in model_id.
  So the model_id must contain "claude". But if "claude" is added to CHAT_COMPLETIONS_FAMILIES, the claude branch
  still runs first, so that is fine; test_phase9 line 32 asserts every family is in that tuple.
- Returned model: route_chain _returned_model line 188 reads "model"; Anthropic replies include it. Works as is.
- Usage: Anthropic reports input_tokens / output_tokens, not prompt_tokens / completion_tokens / total_tokens.
  _numeric_usage keeps them, but usage_by_system (route_chain ~call()) only sums prompt/completion/total,
  and cost_from_usage (line 153) uses prompt_tokens and total_tokens. Claude totals and cost would show 0
  unless mapped (input -> prompt, output -> completion, total = input + output).
- Prices: v1rg0_prices.json has no "claude" row (all rows still null).

## 4. Other places that name systems
- route_chain --allow-systems default (608) and --first-hop-systems (602): Claude only runs if named there.
- round2_chain.py: check whether it should know Claude at all (probably not for the first patch).
- Comment at transmission_suit line 138 ("Claude -> DeepSeek") is stale wording from the original remap.

## 5. Offline tests to mirror
- test_phase9.py lines 16-35: provider_family / registry checks.
- Mock transmit like the existing suites; all six *_API_KEY vars unset (now including ANTHROPIC_API_KEY).
