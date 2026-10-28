# Feedback log: Nebius Token Factory, NVIDIA Nemotron, Tavily

Only things that actually happened while building CourtroomAI, with dates and the
evidence file or command. Nothing here is estimated.

## Token Factory

**2026-10-27 — Two base URLs both work.** `GET /v1/models` returned HTTP 200 with the same
30 models on both `https://api.tokenfactory.nebius.com/v1` and `https://api.studio.nebius.com/v1`
(curl with the same key). The docs and console show different hosts, which made the
"which base URL is canonical" question unclear at first. We use the `tokenfactory` host.

**2026-10-27 — Structured output works on all three Nemotron models.** `scripts/probe_structured.py`
sent the same tiny prompt in four modes (plain, `response_format: json_object`,
`response_format: json_schema` strict, forced tool call) to Nano, Super and Ultra: 12/12
returned HTTP 200 with valid JSON, about 1.1–2.9 s each. Evidence: `logs/probe_structured_2026-10-27T183332.json`
(not committed; logs are git-ignored). Positive feedback: this let us use schema-constrained
output instead of a parse-and-repair loop.

**2026-10-27 — Reasoning tokens are billed inside `completion_tokens`.** Responses carry a separate
reasoning field and `usage.completion_tokens_details.reasoning_tokens` (Super and Ultra), and
those tokens count toward `completion_tokens`. Example from the probe: Ultra, tiny prompt,
`completion_tokens: 54` of which `reasoning_tokens: 45`. Consequence: `max_tokens` must leave
room for reasoning or the JSON answer gets truncated. Nano's usage block had
`completion_tokens_details: null`, so its reasoning share is not reported.

**2026-10-27 — Forced tool calls cost noticeably more prompt tokens.** Same prompt, Nano:
`json_schema` 128 total tokens vs forced tool call 688 total tokens (probe file above).

## Nemotron 3 Ultra (`nvidia/Nemotron-3-Ultra-550b-a55b`) as a judge

**2026-10-27 — Stitched quotes.** In audit mode, asked to return a verbatim supporting quote,
Ultra returned `verdict: "supports"` with a quote that joined two sentences from different
places in the judgment (skipping the sentence between them). Our verbatim check caught it:
the longest matching prefix was 341 of 509 characters (`runs/audit_draft_audit_demo_20261027T184215.json`).
Fix on our side: judge prompt v2 asks for one contiguous passage, plus one retry that states
why the quote failed. The next run returned a contiguous quote and the claim passed
(`runs/audit_draft_audit_demo_20261027T184329.json`). Suggestion: a documented
"extractive quote" mode would help any verification use case.

**2026-10-27 — Empty quote on `not_addressed`.** With prompt v1, Ultra returned `quote: ""` for a
`not_addressed` verdict, which our fail-closed rule turns into "unverified". Prompt v2 asks for
the closest passage instead.

**2026-10-27 — Latency.** First live judge call (adversarial test): 3.69 s, 350 prompt + 486
completion tokens (`logs/llm_calls.jsonl`). Audit of three citations: extraction 6.98 s (Nano),
verification 15.88 s for three parallel judge calls including one quote retry (Ultra).

## Tavily

**2026-10-27 — Results for cases that do not exist.** Searching a deliberately fabricated case
("Imaginary Kumar v. State of Nowhere, (2031) 4 SCC 777") returned three results: a US Supreme
Court docket PDF, a judicial academy PDF and an unrelated Indian case page. Treating "any result"
as "found online" made a fake citation look half-real. Fix on our side: a hit counts only if it
names every distinctive party word or the exact citation (`core/audit.py: mentions_case`).

## Tooling

**2026-10-27 — `openai` SDK major version.** `pip install openai` resolved to 3.40.0. We checked the
installed source before use: `OpenAI(api_key, base_url, timeout, max_retries)` and
`chat.completions.create(model, messages, temperature, max_tokens, response_format)` are present.

## Nemotron 3 Nano (`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`)

**2026-10-27 — Thinking mode consumed the whole budget on a simple extraction.** Intake prompt
(~520 prompt tokens) with default settings: `finish_reason=length`, empty `content`, 42–90 s,
all completion tokens used by reasoning (also seen as a 90 s client timeout). Same prompt, live
comparison: system message `/no_think` → 12.3 s, 2,743 tokens, valid JSON;
`extra_body={"chat_template_kwargs": {"enable_thinking": false}}` → **2.0 s, 494 tokens**, valid JSON;
`reasoning_effort: "low"` → 48.7 s, 3,000 tokens, truncated. We use `enable_thinking: false` for
extraction. A clear doc note on per-request reasoning control for Nemotron on Token Factory would
have saved an hour.

**2026-10-28 — Citation normalised despite "copy exactly".** Asked to copy citations exactly, Nano
returned "(2013) 15 SCC 240" for a draft that wrote "2013 (15) SCC 240". Harmless for us because
citation matching ignores brackets and spacing, but worth knowing for extraction tasks.

## Nemotron 3 Super (`nvidia/nemotron-3-super-120b-a12b`)

**2026-10-27 — Optional schema fields get skipped.** With `quote` optional in the drafting schema,
Super returned precedent claims with no quote (both claims in the first sample run), so every one
failed verification. Making `case_id`, `quote` and `text` required in the JSON schema fixed it on the
next run (`scripts/run_brief.py` on the sample FIRs).

## Tavily Extract

**2026-10-28 — Basic extract fails on Indian Kanoon; advanced works and is faithful.**
`POST /extract` with `{"urls":["https://indiankanoon.org/doc/101107975/"]}` returned HTTP 200 with
`failed_results: [{"error": "Failed to fetch url"}]`. The same call with `"extract_depth": "advanced"`
returned the full judgment (23,442 characters) in 4.3 s. After stripping the markdown Tavily adds
(links, images, emphasis), three known verbatim quotes from that judgment all matched exactly, so the
text is usable for word-for-word verification. Suggestion: say in the docs which sites need advanced
depth; we found out by trial.

**2026-10-28 — Search + Extract verified a case outside our library.** For a draft citing
"Arnesh Kumar v. State of Bihar, (2014) 8 SCC 273", Tavily Search returned the Indian Kanoon page among
blogs and a Scribd copy; we extract only trusted full-judgment hosts, and Nemotron Ultra's supporting
quote was found verbatim in the extracted text (`runs/audit_draft_audit_web_20261027T205708.json`).
The extracted page starts with site navigation ("Document Options Get in PDF Print it!…"), which we strip.

**2026-10-28 — Nano can loop under schema-constrained decoding.** On one synthetic FIR (eval case E06,
~406 prompt tokens), Nano with `enable_thinking: false` and `response_format: json_schema` produced 6,000
completion tokens in ~52 s (the full limit) and the JSON never closed; it happened on two separate runs.
Bounding the schema's arrays (`maxItems`) and lowering `max_tokens` to 2,500 fixed it on the next run
(intake 4.9 s). We also fall back to Nemotron Super for extraction if Nano's JSON is invalid twice.
