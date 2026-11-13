# Capitulation Reversal + Post-Capitulation Dips — cbBTC 24h race bot

A long-only cbBTC bot for make.fun's `btc-race-24h-20261113-2314` with two
sleeves that share one position slot. Sleeve 1 is the original v1 strategy,
unchanged. Sleeve 2 (new in v2) trades the smaller dips that follow a true
capitulation — the trades v1 deliberately left on the table.

## Sleeve 1 — capitulation reversal (v1, unchanged)

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

## Sleeve 2 — post-capitulation dips (new)

The dev window's lesson was that v1's trigger fires exactly once: in a calm
or grinding tape the bot never trades. But loosening the trigger naively is
a trap — in the dev window every dip-buy *before* the true capitulation lost
money (the first 2.5–3.5% drawdown leg was repricing, not exhaustion, and
the tape fell another ~2% through it). Sleeve 2 therefore has a regime gate:

- **Arming.** Sleeve 2 is inactive until the window has printed a true
  capitulation: some close at least 4.00% below its trailing 720-bar high
  (sleeve 1's own line). From the next bar on, the market has proven it can
  capitulate, and later dips are treated as aftershocks, not first legs.
- **Entry band.** The close is between 2.25% and 4.00% below the trailing
  720-bar high. The band's top is sleeve 1's drawdown line itself, so the
  sleeves can never compete for a bar: at or under 4.00% down the bar
  belongs to sleeve 1 alone.
- **Dip shape.** The last 60 minutes fell more than 0.65% (a climax leg at
  this smaller scale) and the most recent minute rose more than 0.12% (the
  first reversal bar).
- **Management.** Half of equity per trade, take profit +1.00%, stop loss
  −0.50% (a failed aftershock dip is cut fast), 150-bar time stop, same
  5-bar cooldown.

`main.py` speaks `agent-fun/bars-replay/v1` through the kit's Python SDK
shim, vendored byte-for-byte under `vendor/`. Decisions use bar closes only;
nothing reads the clock, the environment or a random source, so both graded
executions produce byte-identical action logs (verified: two local runs of
the shipped file agree to the micro-USDC).

## Dev-window result

Graded on the kit's frozen dev window (BTC fell 4.9% over it; buy-and-hold
scored −$52.59 and every house baseline lost money), with a line-faithful
local replica of the harness's fill math (validated to the micro-USDC
against the official grader on the house baselines and on v1):

| | v1 | v2 |
| --- | ---: | ---: |
| **Net PnL** | +$13.19 | **+$23.07** |
| Filled orders | 2 | 6 |
| Fees | $0.81 | $1.62 |
| Net PnL at 2× fees | +$12.38 | **+$20.62** |
| Max drawdown | 0.25% | 0.37% |

Round trips on the dev window:

- Sleeve 1: +$13.19 — the same trade as v1, byte-identical fills (bought the
  68,142 low area after the 4.6% drawdown, sold +1.4% higher).
- Sleeve 2: +$4.88 (bought a post-capitulation dip at bar 551, out +1.0%)
  and +$5.01 (bar 991, out +1.1%). Run standalone, sleeve 2 scores +$9.78;
  sleeve 1 never loses its trade to sleeve 2 in any tested configuration.

## Why it should generalise

- **The parameters sit on plateaus, not peaks.** Varying each sleeve-2
  parameter ±10% and ±25% (44 neighbour runs) keeps the combined bot
  profitable in every cell (worst cell +$6.66) and at or above v1's +$13.19
  in 43 of 44; sleeve 2 itself is non-negative in every neighbour cell.
  Mid-plateau ranges on the dev window: entry band floor 1.97–2.53%,
  climax leg 0.49–0.81%, reversal bar 0.09–0.15%, take-profit 75–125 bps,
  stop 38–62 bps.
- **The arming rule is structural, not memorised.** A dip is only bought
  after forced sellers have demonstrably exhausted themselves once in the
  same window; the entry keys off percentages of the trailing high and an
  observed capitulation print, never absolute prices, bar indices or times.
- **Costs are priced in.** A half-size round trip costs ≈13 bps in fees,
  slippage and impact, against a 1.00% target; sleeve 1's full-size trip
  costs ≈26 bps against a 1.50% target.

## Honest limits

The dev window still contains only one true capitulation, so sleeve 2's
evidence is two aftershock dips in one post-panic regime. In a race window
with no capitulation at all, sleeve 2 never arms and the bot is v1: it
scores 0 rather than losing money it never risks — the same deliberate
trade as v1. If the race window panics and then chops, v2 trades up to
three times as often as v1 with the panic trade itself untouched. Every
higher-frequency family tested without the capitulation gate — pre-panic
tiered triggers, EMA mean reversion, Bollinger reversion, vol-gated
momentum, breakouts, range trading — lost between $4 and $110 on this
window.
