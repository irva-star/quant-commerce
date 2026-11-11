# Quantitative Commerce Terminal

A functional local hackathon MVP: React + TypeScript + Vite + Tailwind + AG Grid Community, with FastAPI/Pydantic, Playwright evidence collection, deterministic governance, Channel3 discovery, structured LLM claim assessment, and PayPal **Sandbox only** settlement.

## Run

From this directory in PowerShell, using Node 22+ and Python 3.11+:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
npm.cmd install
# Keep your existing .env. Only copy the example when .env does not exist:
if (!(Test-Path .env)) { Copy-Item .env.example .env }
npm.cmd run api
```

In a second terminal:

```powershell
npm.cmd run dev
```

Open **http://127.0.0.1:5173**. API docs: **http://127.0.0.1:8000/docs**. Keep one FastAPI worker. After `npm.cmd run build`, restarting FastAPI also serves the built terminal at port 8000; set `APP_URL=http://127.0.0.1:8000` if using that address for PayPal approval returns. Restart FastAPI after editing `.env`.

This workspace's current buyer-facing URL is **http://127.0.0.1:8765**, with `APP_URL` set to that exact origin. It serves the built terminal and API together:

```powershell
npm.cmd run build
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8765
```

Keep the internal API on port 8000 running for the controlled storefront URLs. PayPal returns to `/api/paypal/return` or `/api/paypal/cancel` at the configured `APP_URL`. The server links the returned order to its saved audit and redirects to the terminal. Refresh, token-only legacy links, and reopening the terminal recover the existing checkout from the backend; they do not automatically run another audit or create/capture an order. The browser confirms actual PayPal status before offering capture. An expired audit remains visible but requires explicit re-auditing before a fresh checkout. For checkout login, use a separate **Personal Sandbox buyer**; the app's **Business Sandbox account** is the seller. Existing PayPal orders retain the return URL they were created with, so configuration changes apply to new orders.

## Demo flow

1. **Clean purchase:** $68 item + $4 shipping + $4 tax = $76 merchant payable; ~4.808 kg CO2e. Default mandates PASS. Inspect evidence, sources, and claim explanations.
2. **Anchor + drip pricing:** $199 slashed reference; $59 item becomes $93 payable, with $19 checkout fees and $9.99 recurring terms. BLOCK for fees/subscriptions; REVIEW findings for anchor and observed +$12 cookie-persona difference. A lower-priced synthetic merchant can be re-audited.
3. **Carbon cap violation:** ~$65.520 kg gross CO2e exceeds both default caps. Enabling the optional $6.56 simulated contribution leaves strict carbon violations BLOCKED. Reviewable policy without acknowledgement gives REVIEW. An explicit buyer exception and recorded reason can resolve carbon-only violations; other strict rules remain enforced.
4. **Settlement:** the buyer must check the approval box. `Simulate settlement` is clearly labeled, makes no PayPal call, and updates the local demo ledger. PayPal follows a separate create → approve on PayPal → manually approve capture in the terminal flow. Synthetic alternative merchants are simulation-only; the original controlled merchant is the only PayPal Sandbox seller.

Scenarios default to a reproducible **synthetic catalog**, including when a Channel3 key is configured. Enable **Live Channel3 discovery** in the mandate and re-audit for real Search results. A synthetic demo SKU has no verified live catalog identity, so live candidates may remain unverified and no identical-product median is fabricated. External URLs use the live adapter automatically and require an explicitly configured public HTTPS host.

## PayPal Sandbox

Credentials belong only in the root `.env`: `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET`. `python-dotenv` loads that exact path without printing it; existing process variables take precedence. `.env` and `.env.*` are ignored except `.env.example`. No secret uses a `VITE_` variable, browser storage, API response, or source literal.

Test OAuth without exposing credentials or tokens:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/paypal/test-auth
# Or: python scripts/check_paypal.py
```

The public response contains **only** `connected` and `http_status`. A missing configuration returns false/503; a transport failure returns false/null. Actual upstream status is preserved when PayPal responds. The access token exists briefly in server memory only.

All PayPal requests use the fixed `https://api-m.sandbox.paypal.com` origin:

- OAuth: `POST /v1/oauth2/token`, Basic authentication and `grant_type=client_credentials`.
- Create: `POST /v2/checkout/orders`, immutable server-side merchant amount in USD, idempotency key bound to audit ID.
- Approval: browser navigates to PayPal's returned Sandbox approval link. Audit PASS alone never triggers payment.
- Capture: separate explicit buyer action. The backend reads the order and requires PayPal `APPROVED` before capture. A return URL or browser boolean is insufficient. Only confirmed `COMPLETED` captures with the expected amount/currency enter the ledger. Retries do not duplicate usage.

Our endpoint `POST /api/paypal/orders` requires `audit_id`, `buyer_approved: true`, and `approved_total` equal to the displayed audited **total fiat exposure**. The same fields plus `order_id` are required by `/api/paypal/capture`. The offset quote is included in the governance budget but excluded from the merchant PayPal order: its separate leg is simulated. Before both operations, the server revalidates PASS, current monthly usage/pending reservations, a 15-minute audit expiry, and fresh storefront evidence. External merchants cannot use our PayPal credentials. Optional carts must reconcile to a single quantity-one audited item; unresolved multi-item carts block.

**Authentication verification in this workspace:** PayPal Sandbox now returns **HTTP 200** after correcting a Secret that duplicated the Client ID and restarting the backend that retained the old values. One real **USD 76.00** Sandbox order was created and its buyer approval page loaded. Buyer approval and capture require explicit buyer actions; consult [PayPal diagnosis](PAYPAL_DIAGNOSIS.md) and the latest verification report for their actual state. Unit/integration tests use mock credentials and mock responses, never the `.env` secrets.

## Actual versus synthetic capabilities

| Capability | Implementation / boundary |
| --- | --- |
| Interactive terminal | Real React state, API audits, AG Grid sorting/filtering, mandate re-audits, history and JSON export. |
| Governance | Real deterministic Pydantic rules. BLOCK > REVIEW > PASS. LLM output cannot authorize payment. |
| DOM extraction | Real headless Playwright. Controlled markers, explicit slashed-price selector, standard Product/Offer JSON-LD, and documented supported selectors in `backend/page_data.py`. HTML snapshots, selectors, timestamps, URL and SHA-256 are preserved, including personalized snapshots. Unsupported or ambiguous values remain missing. |
| Persona comparison | Two isolated contexts on the local storefront; one `returning_customer` cookie differs. No demographic inference, discrimination finding, or statistical significance claim. If browser launch fails, fixture fallback is labeled and no paired observation is asserted. |
| Channel3 | Real documented Search and Lookup adapter; raw responses saved. Live Search returned HTTP 200 with 12 products / 19 usable offers and was verified in AG Grid. Live Lookup returned HTTP 200 and resolved one product. Local URLs skip Lookup. New, variant-unambiguous offers sharing a lookup canonical ID are identical. Functional candidates require category/material agreement and at least two matching functional specs. Others remain unverified; unverified/functional candidates never enter the identical median. |
| LLM | Configurable OpenAI-compatible `/chat/completions` adapter with strict JSON schema and Pydantic/source-ID/claim-coverage checks. No LLM key supplied in this session; the actual model call remains untested. Deterministic fallback is clearly labeled. |
| Carbon | Real arithmetic using versioned published aluminium/freight factors. Fixture mass/composition/route/fabrication electricity are explicitly synthetic. Missing critical inputs block. No unsupported materials or routes are guessed. |
| PayPal | Real OAuth/create/read/capture implementation, Sandbox only. Live OAuth returned 200; one USD 76.00 order was created and its actual Sandbox approval page loaded. Buyer approval/capture are explicit actions, tracked separately in the live verification report. |
| Carbon partner | Modular `CarbonPartner` protocol; separate **SIMULATED** proposed leg, zero credited quantity. No Payouts/Multiparty permissions or eligible contracted partner were confirmed. No transfer, retirement, or atomic split claim. |
| Arbitrage | Merchant links and a new mandate audit. No checkout authority on unrelated merchants. |
| Persistence | Local SQLite audits/orders/ledger plus evidence artifacts under ignored root `data/`. Single local demo buyer, UTC calendar-month accounting, no login or multi-tenant deployment. Sandbox and simulated entries are marked by mode; neither implies a real-world purchase. |

## Channel3 integration

Use **Product discovery** to enter a public HTTPS product URL, or paste it into the terminal URL entry and select **Discover product**. This catalog-only view does not require `AUDIT_ALLOWED_HOSTS`. It calls `POST /api/channel3/discover`, resolves identity with Lookup, then uses the actual title (or an explicitly entered search query) for comparable Search results. Prices retain their source currency; product identity, specifications, merchant links and LIVE provenance are displayed.

Discovery always shows **REVIEW**, with checkout and carbon **NOT VERIFIED** and no purchase authorization or payment controls. It creates no audit/order/ledger entries and never invokes Playwright, the governance validator, carbon estimation or PayPal. An unsupported Lookup does not invent product identity; an optional descriptive query can independently return clearly unverified live search candidates. Provider errors and HTTP statuses remain visible.

**Deep Storefront Audit** is a separate explicit action, enabled only when the exact host is already approved in `AUDIT_ALLOWED_HOSTS`. The server still enforces that allowlist, private-address checks, browser request interception and all existing payment mandates. Public discovery validates HTTPS, rejects embedded credentials/custom ports/private IPs/local hostnames, and checks all resolved addresses before forwarding the URL to Channel3. No merchant browser request is made during discovery. The standalone Lookup and Search-with-reference proxy endpoints use the same public-URL checks.

The interrupted Amazon-specific extraction changes, automatic fallback and temporary Amazon host approvals were reverted. PayPal, governance and carbon modules were restored to the pre-Amazon stage and verified unchanged by file hashes during this work. The three synthetic experiments remain separate and reproducible. Switching to discovery and back preserves an existing Sandbox checkout in the terminal.

Live verification for a supported public URL outside the browser allowlist: Lookup **200**, Search **200**, **14 offers**, identity resolved, decision REVIEW, zero audits created and zero payments initiated. The browser sent no API-key header. See `data/discovery-live-verification.json` and `data/discovery-live.png` for this session's artifacts.

The server sends `x-api-key` only to the configured Channel3 API origin. The browser calls our FastAPI endpoints and never receives the key:

- `POST /api/channel3/lookup` accepts `{ "url": "https://merchant.example/product" }` and calls the documented upstream `POST /v1/lookup`. It returns the resolved `product`, normalized offers, and upstream HTTP status.
- `POST /api/channel3/search` accepts `{ "query": "aluminium laptop stand", "limit": 12 }`, with optional `reference_url` for canonical identity matching, and calls upstream `POST /v1/search`. It returns documented product data, normalized offers, and application status/count metadata.
- Live mandate audits resolve an external product URL with Lookup, then use its actual title (or the buyer's explicit query) for Search. The local demo skips Lookup because synthetic URLs have no real catalog identity.

Documented fields used are `products` / `product`, `id`, `title`, `offers`, `domain`, `url`, `price.price`, `price.currency`, `materials`, `key_features`, `category`, `dimensions`, `condition`, `availability`, and `variants`. `price.amount` is also accepted because the official Offer guide uses that representation in its example. Application fields such as `match_reason`, `synthetic`, `http_status`, and counts are explicitly our normalization metadata, not invented Channel3 response properties.

The matrix calculates original item price, exact-product/same-currency median, spread, `(original / median - 1) × 100`, reference deviation, and up to three lower-priced exact/functional candidates. No currency conversion is assumed. Unknown matches do not contribute to the median or verified cheaper alternatives. Click a grid row for its specifications and matching explanation; open the merchant link or re-audit before checkout.

Enable **Live Channel3 discovery** in the buyer mandate, optionally set **Comparable-product search query**, then select **Apply mandate & re-audit**. LIVE rows, upstream status and product/offer counts appear in the matrix. Reproducible fixtures and failure fallbacks are explicitly **MOCK / SYNTHETIC**. Failures distinguish 401/403 authentication, 404/missing products, 429 rate limits (including a numeric Retry-After), network errors, malformed responses and timeouts. Valid zero-result searches stay LIVE with zero results. External failures never invent external catalog products. Full external DOM audits still require `AUDIT_ALLOWED_HOSTS` and complete checkout/carbon evidence; independent Search and Lookup proxy endpoints do not need a browser audit.

Live verification on 2026-11-11:

- Query **Hydro Flask 32 oz Wide Mouth bottle**: upstream **200**, **12 products**, **19 usable merchant offers**; actual AG Grid rows and LIVE status verified with Chromium.
- Lookup of `https://www.memobottle.com/products/universal-desk-stand-black`: proxy **200**, upstream **200**, product resolved with **1 usable offer**.
- Browser inspection: no direct Channel3 requests and no `x-api-key` header. Final client-bundle credential scan returned false.
- Reproduction scripts: `scripts/check-channel3-frontend.mjs` and `scripts/check_channel3_lookup.py` make real read-only provider requests. They print status/counts only. The UI script saves `data/channel3-live-verification.json` and `data/channel3-live.png`.

## Carbon methodology

Version `qct-carbon-v1`:

- Material: item kg × mass fraction × kg CO2e/kg. Supported table: primary aluminium, **14.8 kg CO2e/kg**, IAI 2023 global cradle-to-cast-house average. Supplier-specific recycled content is not inferred.
- Fabrication: explicit product fabrication kWh × explicit grid factor. The demo provides 0.4 kg CO2e/kWh as a **synthetic fixture assumption**, not a published regional factor. It is additional fabrication after cast-house production, avoiding double counting smelting.
- Freight: shipment kg / 1000 × explicitly supplied route km × mode factor. DESNZ **2025 version**, frozen for reproducibility (not claimed to be the latest): road 0.10163, air 0.89939, sea 0.01612 kg CO2e/tonne-km. `backend/data/transport-factors.json` includes workbook row IDs, exact source rows, download URL and SHA-256. Air includes radiative forcing. These rows exclude well-to-tank fuel emissions; UK road/sea factors are disclosed proxies for synthetic routes.
- Gross: material + fabrication + shipping. Point estimates enforce caps; illustrative ±40% sensitivity is **not** a statistical confidence interval. Packaging production, retail, use and end-of-life are excluded.
- Optional contribution: gross kg / 1000 × configurable USD/tonne, rounded **up** to cents. Default $100/tonne is a demo quote, not a partner market offer. `OFFSET_PARTNER` defaults to an explicitly uncontracted demo partner; `credited_kg` stays zero. Gross cap tests never subtract offsets.
- Monthly ledger increments on explicitly simulated settlement or a completed Sandbox capture. Audit previews do not consume the budget. Pending Sandbox orders reserve carbon within the single-process payment gate. Cancelled orders currently retain their reservation; resolve outstanding orders before continuing the demo.

To regenerate the checked-in factor table, download the exact official workbook URL in `scripts/import_factors.py` to `backend/data/transport-source.xlsx`, then run `python scripts/import_factors.py`. The importer uses Python's standard library only. No workbook download is needed to run the MVP.

## Verification

```powershell
npm.cmd run test
npm.cmd run build
npx.cmd playwright install chromium
npm.cmd run test:e2e
```

Backend tests isolate SQLite and evidence in temporary directories and remove external API keys from each test environment. They cover missing evidence, amount reconciliation, fiat/fees/subscriptions, clean/anchor/carbon scenarios, strict and acknowledged overrides, source validity, API normalization, partial JSON-LD extraction, URL restrictions, OAuth public response boundaries, PASS-only payment gating, buyer approval and exact amount confirmation, stale/changed evidence, monthly usage, capture status/currency/amount and idempotency. Browser tests exercise the terminal against actual local DOM audits, including responsive layout. No automated test initiates a real PayPal order or capture.

This is a single-user local demo, not a deployed production payment service. Public retailer access is an exact HTTPS host allowlist (`AUDIT_ALLOWED_HOSTS`), with private-address checks and request/redirect interception. New merchant checkout schemas need explicit extraction support; unknown final totals, recurring terms, composition, or routes remain missing and block settlement. External DOM and JSON-LD stay untrusted data throughout the claim prompt and governance pipeline.

## Primary references

- [Channel3 Search](https://channel3.ai/docs/guides/make-a-search), [URL Lookup](https://channel3.ai/docs/guides/url-lookup), [offer schema](https://channel3.ai/docs/guides/offer).
- [PayPal OAuth](https://developer.paypal.com/api/rest/authentication/), [Orders v2](https://developer.paypal.com/api/orders/v2).
- [IAI aluminium footprint and boundaries](https://international-aluminium.org/landing/aluminium-carbon-footprint-faqs/), [UK DESNZ 2025 conversion factors](https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2025).
- [Official OpenAI documentation: structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat), [Schema.org Product](https://schema.org/Product), [Schema.org Offer](https://schema.org/Offer).
