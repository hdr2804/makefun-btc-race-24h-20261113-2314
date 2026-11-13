"""Capitulation-reversal bot for the cbBTC 24h bars race (agent-fun/bars-replay/v1).

Strategy in one paragraph: stay in cash. Buy only a panic: the close is at
least DD_BPS below the highest close of the last DD_WINDOW bars (a real
drawdown, not a dip), the last LOOKBACK minutes fell at least ENTRY_DEV_BPS
(a climax leg), and the most recent minute rose more than REV_BPS (the first
reversal bar). Then ride the bounce with a wide stop and a fixed take-profit,
or leave after MAX_HOLD bars. One position, full size: in a falling tape the
edge is refusing almost every trade, so the bot trades rarely and keeps its
powder dry for the one sell-off that actually exhausts itself.

Wire protocol: the kit's Python SDK shim, vendored byte-for-byte under
vendor/ (see its own header). Decisions use bar closes only; an order decided
on bar t fills at bar t+1's open with fee, slippage and pool impact charged
by the harness. Nothing here reads the clock, the environment or a random
source: the same bars always produce the same replies.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"

# Entry: how deep the drawdown, how hard the climax leg, how strong the turn.
DD_WINDOW = 720        # bars of history the drawdown is measured over
DD_BPS = 400           # close must be >= 4.00% under the window's highest close
LOOKBACK = 30          # minutes of the climax leg
ENTRY_DEV_BPS = 60     # the leg must fall more than 0.60%
REV_BPS = 20           # the last minute must rise more than 0.20%
MIN_HIST = 120         # bars to see before any entry is considered
# Exit: risk controls around the bounce. The stop is deliberately wider than
# the post-climax noise (a 0.40-0.60% stop is shaken out by the same volatility
# that created the entry), and the take-profit sits inside the size of bounce
# a 4%+ drawdown typically snaps back. Both were picked at the centre of a
# plateau, not a peak: on the dev window every neighbour of these numbers
# (stop 60-100, take-profit 90-170) stays profitable.
STOP_BPS = 80          # sell if the position's value falls 0.80% under its cost
TP_BPS = 150           # sell if it rises 1.50% over its cost
MAX_HOLD = 150         # or after 150 bars, whatever comes first
COOLDOWN = 5           # bars to sit out after an exit
MAX_SLIPPAGE_BPS = 1000

closes = []            # every close seen, oldest first (ints at price_scale)
held_since = None      # seq the open position's entry was decided on
cooldown_until = -1    # first seq at which a new entry is allowed


def _orders(state):
    global held_since, cooldown_until
    pos = state.positions.get(SYMBOL)
    close = state.close(SYMBOL)
    if close is None:
        return []
    seq = state.seq
    if pos is None:
        held_since = None
    elif held_since is None:
        held_since = seq

    if pos is not None:
        value = state.value(SYMBOL, pos.qty)
        exit_now = (
            value <= pos.cost * (1.0 - STOP_BPS / 10000.0)
            or value >= pos.cost * (1.0 + TP_BPS / 10000.0)
            or seq - held_since >= MAX_HOLD
        )
        if exit_now:
            cooldown_until = seq + COOLDOWN
            return [{"side": "sell", "symbol": SYMBOL, "qty": pos.qty,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        return []

    if seq < cooldown_until or state.warming_up or len(closes) < MIN_HIST:
        return []
    window = closes[-DD_WINDOW:]
    if close > max(window) * (1.0 - DD_BPS / 10000.0):
        return []  # no real drawdown: cash is the position
    if closes[-1] / closes[-1 - LOOKBACK] - 1.0 >= -ENTRY_DEV_BPS / 10000.0:
        return []  # the last half hour was not a climax leg
    if closes[-1] / closes[-2] - 1.0 <= REV_BPS / 10000.0:
        return []  # still falling: wait for the first reversal bar
    notional = min(state.cash, state.equity)  # full size, capped by cash in hand
    if notional < 1_000_000:
        return []
    held_since = seq
    return [{"side": "buy", "symbol": SYMBOL, "notional_quote_units": notional,
             "max_slippage_bps": MAX_SLIPPAGE_BPS}]


def on_batch(state, batch):
    for bar in batch["bars"]:
        if bar["symbol"] == SYMBOL:
            closes.append(int(bar["c"]))
            return _orders(state)
    return []


makefun_bars.run(on_batch)
