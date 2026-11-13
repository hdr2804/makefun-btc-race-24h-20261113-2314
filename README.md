# Capitulation Reversal — cbBTC 24h race bot

A long-only cbBTC bot for make.fun's `btc-race-24h-20261113-2314` that spends
almost the whole race in cash and buys exactly one kind of moment: a panic
that has already started to turn.

## Strategy

Stay flat until **all three** entry conditions hold on the same bar:

1. **A real drawdown** — the close is at least 4.00% below the highest close
   of the last 720 bars. Not a dip: a sell-off.
2. **A climax leg** — the last 30 minutes fell more than 0.60%.
3. **The first reversal bar** — the most recent minute rose more than 0.20%,
   so the bot never catches a still-falling knife.

Then buy with 100% of equity and manage the bounce:

- take profit at +1.50% over the position's cost (fees included),
- stop loss at −0.80% under cost (wide on purpose: post-climax noise shakes
  out a tight stop),
- time stop after 150 bars,
- 5-bar cooldown after any exit.

`main.py` speaks `agent-fun/bars-replay/v1` through the kit's Python SDK
shim, vendored byte-for-byte under `vendor/`. Decisions use bar closes only;
nothing reads the clock, the environment or a random source, so both graded
executions produce byte-identical action logs.

## Dev-window result

Graded on the kit's frozen dev window (BTC fell 4.9% over it; buy-and-hold
scored −$52.59 and every house baseline lost money):

- **Net PnL +$13.19** on $1,000 (fees $0.81; still **+$12.38 with every fee
  doubled**)
- 2 filled orders — one round trip: bought the 68,142 low area after the
  4.6% drawdown, sold +1.4% higher into the snap-back
- Max drawdown 0.25%, exposure 4.2% of the window

The number was produced by a line-faithful local replica of the harness's
fill math (validated to the micro-USDC against the official grader on the
house baselines) and confirmed by the official `grade-local` on an identical
TypeScript twin of this strategy: same PnL, same trades, same fees.

## Why it should generalise

- **The parameters sit on a plateau, not a peak.** On the dev window every
  neighbouring setting stays profitable: drawdown 3.90–4.10%, climax leg
  0.50–0.70%, lookback 25–35, stop 60–100 bps, take-profit 90–170 bps,
  max-hold 120–180. Nothing was shaved to fit one bar.
- **The rule is structural, not memorised.** Forced sellers exhaust
  themselves at the end of a fast multi-percent drawdown in a thin on-chain
  pool; the first strong up-minute is observable evidence the exhaustion is
  real. That pattern exists in any window with a panic in it, at whatever
  price level — the bot keys off percentages of the trailing high, never
  absolute prices or times of day.
- **Costs are priced in.** A full-size round trip costs ≈26 bps in fees,
  slippage and impact, so the bot demands a ≥4% drawdown and a 1.5% bounce
  target before risking anything; ordinary chop is ignored, which is also
  why fees were only $0.81.

## Honest limits

The dev window contained exactly one panic of this size, so the position
count is small and the race window may contain none (then the bot scores 0
and fails the dev-gate-style bar of "at least one trade" if it never fires —
a deliberate trade: it cannot lose money it never risks, and in the dev
window every higher-frequency family tested — EMA mean reversion,
Bollinger reversion, vol-gated momentum, breakouts, range trading — lost
between $8 and $110). If the race window panics more than once, the bot can
take each qualifying bounce the same way.
