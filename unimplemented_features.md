# Gateway Checker — Unimplemented Features & Pending Improvements

> Cross-referenced every doc (`IMPROVEMENTS.md`, `IMPLEMENTATION_GUIDE.md`, `urlcheckupgrade.md`, `gate_implement.md`) against actual source code.
> Status legend: ✅ Done · ⚠️ Partial · ❌ Not started
>
> **Last audited:** 2026-05-01 (re-verified against live source)

---

## 🔴 Critical Bug Fixes

| ID | Issue | File | Status | Notes |
|----|-------|------|--------|-------|
| CRITICAL-001 | Race condition in HTTP client singleton (`_lock is None` check) | `http_client.py` | ✅ **Fixed** | Module-level `_get_singleton_lock()` implemented |
| CRITICAL-002 | Unsafe file ops in `_atomic_write_json` (no dir check, no temp cleanup) | `user_manager.py` | ✅ **Fixed** | Full validation + finally-cleanup present |

---

## 🟡 Warnings (Documented but NOT Fixed)

| ID | Issue | File | Status |
|----|-------|------|--------|
| WARNING-001 | Wrong type hint `Dict[str, any]` (lowercase `any`) in `analyze_url_response` | `detection.py` | ✅ **Fixed** — all signatures now use `Dict[str, Any]` (capital A) |
| WARNING-002 | `RateLimiter.user_requests` unbounded memory growth (no periodic cleanup, no `max_tracked_users`) | `rate_limiter.py` | ✅ **Fixed** — `cleanup_interval`, `max_tracked_users=50_000`, hourly cleanup + LRU eviction all present |
| WARNING-003 | `UserCache._lock_flag` bool not thread-safe (should use `threading.Lock`) | `user_manager.py` | ✅ **Fixed** — now uses `self._lock = threading.Lock()` (L63) |
| WARNING-004 | `Dict[str, any]` in `detection.py` — missing `URLAnalysisResult` TypedDict | `detection.py` | ✅ **Fixed** — type hints corrected to `Dict[str, Any]`; TypedDict still absent but no incorrect `any` |
| WARNING-005 | Missing `w` duration suffix support in `add_subscription` (1w = 7 days) | `user_manager.py` | ✅ **Fixed** — `endswith('w')` branch handles weeks (L541-543) |

---

## 🟢 Suggestions / Optimizations (All Not Implemented)

### Performance — URL Checking (`urlcheckupgrade.md`)

| # | Fix | File | Effort | Status |
|---|-----|------|--------|--------|
| OPT-01 | Fix O(n²) `urls.index(url)` → O(1) dict `url_to_idx` in `process_urls_async` | `bot_aiogram.py` | 5 min | ✅ **Done** — `url_to_idx = {url: i for i, url in enumerate(urls)}` (L2209) |
| OPT-02 | Enable cache lookup on retry (currently only checked on `retry_count==0`) | `gateway_checker.py` | 2 min | ✅ **Done** — cache checked on ALL retry attempts (L126) |
| OPT-03 | Parallel HTML analysis with `ThreadPoolExecutor` + `asyncio.gather()` | `detection.py` | 30 min | ❌ |
| OPT-04 | Circuit breaker for failing domains (avoids 3×timeout per dead site) | `gateway_checker.py` | 45 min | ❌ |
| OPT-05 | Increase `limit_per_host` from 10 → 30 for bulk same-domain scans | `http_client.py` | 5 min | ❌ — still 10 |
| OPT-06 | Response streaming with size limit (currently `await response.text()` loads all) | `gateway_checker.py` | 60 min | ❌ |
| OPT-07 | Frequency-ordered patterns (most common gateways checked first) | `detection.py` | 30 min | ❌ |
| OPT-08 | Failed-result caching (TTL-based per status code: 403→30m, 5xx→5m, timeout→10m) | `cache_manager.py` | 45 min | ❌ |
| OPT-09 | Adaptive timeout based on domain history | `gateway_checker.py` | 60 min | ❌ |

### Infrastructure Gaps

| # | Feature | File | Status |
|---|---------|------|--------|
| INFRA-01 | **Scan result caching** — `cache_manager.py` exists but is **never called** from `gateway_checker.py` | `gateway_checker.py` | ✅ **Done** — fully wired: imported, cache-hit on all attempts, saved on 200 (L17, L127-139, L237-249) |
| INFRA-02 | **`/clearcache` command** for owner | `bot_aiogram.py` | ✅ **Done** — `@router.message(Command("clearcache"))` at L532 |
| INFRA-03 | **Rescan button** is implemented but saves URLs to FSMContext `last_urls` — verify state persistence across restarts | `bot_aiogram.py:1120` | ✅ **Done** — `SQLiteStorage` (`fsm_storage.py`) replaces `MemoryStorage`; `fsm_state` table added to DB; `last_urls` persists across restarts |
| INFRA-04 | Rate limiter **memory leak** — `user_requests` dict grows forever; missing hourly cleanup job | `rate_limiter.py` | ✅ **Done** — see WARNING-002; hourly LRU eviction implemented |
| INFRA-05 | `cache_manager.py`'s `clear_expired_cache()` is never scheduled periodically | `bot_aiogram.py` | ✅ **Done** — called inside `/clearcache` handler (L547-559); note: not on a background timer, only on-demand |
| INFRA-06 | `Contact info` → `CONTACT_USERNAME` is in `config.py`, but some bot messages still **hardcode** `@volde_is_back` — needs audit | `bot_aiogram.py` | ✅ **Done** — no hardcoded `volde_is_back` found; `Config.CONTACT_USERNAME` used in all 6+ places |

---

## 📦 New Feature Implementations (Phase 3–4, Not Started)

### From `IMPLEMENTATION_GUIDE.md`

| Feature | Description | Status |
|---------|-------------|--------|
| `/history` command | Show user's last N scans from `scan_history` DB table | ✅ **Done** — `@router.message(Command("history"))` at `bot_aiogram.py:762` |
| `/stats` gateway stats | Show top detected gateways from `gateway_stats` table | ✅ **Done** — `@router.message(Command("stats"))` at `bot_aiogram.py:324`; also `/cachestats` at L459 |
| Bulk file upload (`/bulk`) | Parse `.txt` uploaded files with URLs for batch scanning | ✅ **Done** — `/bulk` command + `F.document` handler fully implemented (`bot_aiogram.py:2293+`) |
| JS rendering support | Use Playwright/Selenium for JS-heavy checkout pages | ❌ Not implemented |
| Health check endpoint | HTTP endpoint for uptime monitoring | ❌ Not implemented |
| Webhook mode support | Switch from polling to webhook for lower latency | ❌ Not implemented |
| Export scan results | Export to CSV/JSON on demand | ✅ **Done** — `/export` command sends CSV, JSON, or TXT file via Telegram document (`bot_aiogram.py:845`); TXT also supported |

### From `gate_implement.md` — Gateway Signature Gaps

All Tier 1–3 gateway additions are **not yet added** to `config.py`/`detection.py`:

| Tier | Gateways | Status |
|------|----------|--------|
| Tier 1 (High-impact) | Sift Science, Airwallex, Bolt Checkout, OKX Pay, THORSwap, LN Markets, Stripe Treasury, Wise Business (8 gateways) | ✅ **Done** |
| Tier 2 Regional | India (PhonePe Switch, Bharat QR, YONO SBI, ICICI iMobile), SEA (LinkAja, SeaMoney, TrueMoney, AirAsia Pay, Boost), Africa (Remitly, WorldRemit, Paga, Moov), MENA (Ziina, MyFatoorah, Hala), LATAM (Stone, Uala), Europe (Fondy, Datatrans) | ✅ **Done** |
| Tier 3 Niche | Gaming (Xsolla, Tencent Pay, Unity Monetization), SaaS billing (Sage Intacct, Oracle, SAP Concur), Wellness (Mindbody, ClassPass), Privacy/Crypto (Monero, Zcash, Haveno), AI services (OpenAI billing, Anthropic billing) | ✅ **Done** |

---

## 🏗️ Implementation Priority Ranking

> Items marked ~~strikethrough~~ are completed.

```
🔴 Fix First (small effort, high impact):
  1. ✅ OPT-01 — O(n²) list fix in process_urls_async
  2. OPT-05 — Increase limit_per_host 10 → 30 (5 min)  ← STILL OPEN
  3. ✅ INFRA-01 — Wire cache_manager into gateway_checker.py
  4. ✅ WARNING-003 — Replace _lock_flag bool with threading.Lock
  5. ✅ WARNING-001 — Fix Dict[str, any] → Dict[str, Any]

🟡 Do Next (medium effort, useful):
  6. OPT-04 — Circuit breaker for dead domains (45 min)  ← STILL OPEN
  7. OPT-03 — Parallel HTML analysis (30 min)  ← STILL OPEN
  8. ✅ OPT-02 — Cache-on-retry in gateway_checker
  9. ✅ INFRA-04 — Rate limiter cleanup job
  10. ✅ WARNING-002 — RateLimiter max_tracked_users + hourly eviction

🟢 Nice to Have (new features):
  11. Tier 1 gateway signatures (30 min batch)  ← STILL OPEN
  12. ✅ /history command
  13. ✅ /stats command
  14. OPT-06 — Response streaming (60 min)  ← STILL OPEN
  15. ✅ Bulk file upload
```

---

## Quick Reference: What IS Implemented

| Feature | Status |
|---------|--------|
| HTTP client singleton race condition fix | ✅ Done |
| Atomic JSON writes with full validation | ✅ Done |
| SQLite database backend (`database.py`) | ✅ Done |
| Async user management wrappers | ✅ Done |
| Rate limiter DB persistence + batch writes | ✅ Done |
| Rate limiter hourly LRU eviction (`max_tracked_users`) | ✅ Done |
| Rescan button with FSM state | ✅ Done |
| Progress tracker for bulk scans | ✅ Done |
| Aho-Corasick pattern matching | ✅ Done (in `pattern_matcher.py`) |
| Audit logging (`audit_log.py`) | ✅ Done |
| Security input sanitization (`security.py`) | ✅ Done |
| Configurable contact info (`CONTACT_USERNAME`) | ✅ Done — fully replaced in all bot messages |
| `cache_manager.py` wired into `gateway_checker.py` | ✅ Done — imported + used on all attempts |
| O(1) URL index lookup (`url_to_idx` dict) | ✅ Done |
| `/clearcache` owner command | ✅ Done |
| `/history` command | ✅ Done |
| `/stats` + `/cachestats` commands | ✅ Done |
| Bulk `.txt` file upload (`/bulk`) | ✅ Done |
| `threading.Lock` in `UserCache` | ✅ Done |
| `Dict[str, Any]` type hints in `detection.py` | ✅ Done |
| Week (`w`) duration in subscriptions | ✅ Done |

### ❌ Remaining Open Items

| ID | Item | Effort |
|----|------|--------|
| OPT-03 | Parallel HTML analysis (`ThreadPoolExecutor`) | 30 min |
| OPT-04 | Circuit breaker for dead domains | 45 min |
| OPT-05 | `limit_per_host` 10 → 30 | 5 min |
| OPT-06 | Response streaming with size cap | 60 min |
| OPT-07 | Frequency-ordered gateway patterns | 30 min |
| OPT-08 | Failed-result caching (per-status TTL) | 45 min |
| OPT-09 | Adaptive per-domain timeout | 60 min |

| INFRA-05 | Background timer for `clear_expired_cache()` (currently on-demand only) | 10 min |
| WARNING-004 | `URLAnalysisResult` TypedDict for `analyze_url_response` | 15 min |
| New features | JS rendering, health endpoint, webhook mode, CSV export | high effort |
| Gateway sigs | ~~Tier 1–3 new gateway signatures~~ | ✅ Done — 989 unique signatures, new GATEWAYS_GAMING category added |
