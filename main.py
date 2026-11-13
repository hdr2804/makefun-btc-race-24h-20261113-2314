"""Two-sleeve capitulation bot for the cbBTC 24h bars race (agent-fun/bars-replay/v1).

Sleeve 1 (v1, unchanged): stay in cash. Buy only a panic: the close is at
least DD_BPS below the highest close of the last DD_WINDOW bars (a real
drawdown, not a dip), the last LOOKBACK minutes fell at least ENTRY_DEV_BPS
(a climax leg), and the most recent minute rose more than REV_BPS (the first
reversal bar). Then ride the bounce with a wide stop and a fixed take-profit,
or leave after MAX_HOLD bars. One position, full size.

Sleeve 2 (new in v2): a post-capitulation dip buyer. It arms only once this
window has printed a true capitulation (a close at least ARM_DD_BPS below
the trailing high) — before that print there is nothing to distinguish a
dip from the first leg of a decline, and every pre-capitulation dip-buy
tested on the dev window lost money. Once armed, it buys smaller panics:
the close is in the band between S2_DD_BPS and sleeve 1's own DD_BPS below
the trailing high (by construction it can never take sleeve 1's trade: at
or under the DD_BPS line the bar belongs to sleeve 1), the last S2_LOOKBACK
minutes fell more than S2_DEV_BPS, and the last minute rose more than
S2_REV_BPS. It trades at half size with a tighter take-profit and stop:
post-capitulation dips snap back fast or not at all.

At most one position is open at a time; sleeve 1 is checked first. Wire
protocol: the kit's Python SDK shim, vendored byte-for-byte under vendor/
(see its own header). Decisions use bar closes only; an order decided on
bar t fills at bar t+1's open with fee, slippage and pool impact charged
by the harness. Nothing here reads the clock, the environment or a random
source: the same bars always produce the same replies.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"

# Sleeve 1 entry: how deep the drawdown, how hard the climax leg, how strong
# the turn.
DD_WINDOW = 720        # bars of history the drawdown is measured over
DD_BPS = 400           # close must be >= 4.00% under the window's highest close
LOOKBACK = 30          # minutes of the climax leg
ENTRY_DEV_BPS = 60     # the leg must fall more than 0.60%
REV_BPS = 20           # the last minute must rise more than 0.20%
MIN_HIST = 120         # bars to see before any entry is considered
# Sleeve 1 exit: risk controls around the bounce. The stop is deliberately
# wider than the post-climax noise, and the take-profit sits inside the size
# of bounce a 4%+ drawdown typically snaps back. Both were picked at the
# centre of a plateau, not a peak.
STOP_BPS = 80          # sell if the position's value falls 0.80% under its cost
TP_BPS = 150           # sell if it rises 1.50% over its cost
MAX_HOLD = 150         # or after 150 bars, whatever comes first
COOLDOWN = 5           # bars to sit out after an exit
MAX_SLIPPAGE_BPS = 1000

# Sleeve 2: post-capitulation dips. ARM_DD_BPS is sleeve 1's own drawdown
# line: the sleeve arms when a close has printed at or under it. The entry
# band's floor S2_DD_BPS and the climax/reversal strengths sit mid-plateau
# on the dev window (drawdown 1.97-2.53%, leg 0.49-0.81%, reversal
# 0.09-0.15%, take-profit 75-125 bps all keep the sleeve profitable).
ARM_DD_BPS = 400       # a capitulation print at this drawdown arms sleeve 2
S2_DD_BPS = 225        # band floor: close >= 2.25% under the trailing high
S2_LOOKBACK = 60       # minutes of the dip leg
S2_DEV_BPS = 65        # the leg must fall more than 0.65%
S2_REV_BPS = 12        # the last minute must rise more than 0.12%
S2_WEIGHT_BPS = 5000   # half of equity per sleeve-2 trade
S2_STOP_BPS = 50       # tighter than sleeve 1: a failed dip is cut fast
S2_TP_BPS = 100        # the snap-back target for a smaller dip
S2_MAX_HOLD = 150

closes = []            # every close seen, oldest first (ints at price_scale)
held_since = None      # seq the open position's entry was decided on
pos_sleeve = None      # "s1" or "s2": which sleeve opened the position
cooldown_until = -1    # first seq at which a new entry is allowed
panic_armed = False    # a capitulation print has been seen this window


def _trailing_high():
    """Highest close of the last DD_WINDOW bars, the drawdown's reference."""
    return max(closes[-DD_WINDOW:])


def _orders(state):
    global held_since, pos_sleeve, cooldown_until
    pos = state.positions.get(SYMBOL)
    close = state.close(SYMBOL)
    if close is None:
        return []
    seq = state.seq
    if pos is None:
        held_since = None
        pos_sleeve = None
    elif held_since is None:
        held_since = seq
        pos_sleeve = "s1"

    if pos is not None:
        if pos_sleeve == "s2":
            stop_bps, tp_bps, max_hold = S2_STOP_BPS, S2_TP_BPS, S2_MAX_HOLD
        else:
            stop_bps, tp_bps, max_hold = STOP_BPS, TP_BPS, MAX_HOLD
        value = state.value(SYMBOL, pos.qty)
        exit_now = (
            value <= pos.cost * (1.0 - stop_bps / 10000.0)
            or value >= pos.cost * (1.0 + tp_bps / 10000.0)
            or seq - held_since >= max_hold
        )
        if exit_now:
            cooldown_until = seq + COOLDOWN
            return [{"side": "sell", "symbol": SYMBOL, "qty": pos.qty,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        return []

    if seq < cooldown_until or state.warming_up or len(closes) < MIN_HIST:
        return []
    high = _trailing_high()
    if close <= high * (1.0 - DD_BPS / 10000.0):
        # Sleeve 1's bar: a real drawdown. Still needs its climax + turn.
        if closes[-1] / closes[-1 - LOOKBACK] - 1.0 < -ENTRY_DEV_BPS / 10000.0:
            if closes[-1] / closes[-2] - 1.0 > REV_BPS / 10000.0:
                notional = min(state.cash, state.equity)  # full size, capped by cash
                if notional >= 1_000_000:
                    held_since = seq
                    pos_sleeve = "s1"
                    return [{"side": "buy", "symbol": SYMBOL, "notional_quote_units": notional,
                             "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        return []  # at sleeve 1's depth, sleeve 2 never substitutes
    if not panic_armed:
        return []  # no capitulation print yet: every dip is a first leg
    if close > high * (1.0 - S2_DD_BPS / 10000.0):
        return []  # above the band: not even a post-capitulation dip
    if closes[-1] / closes[-1 - S2_LOOKBACK] - 1.0 >= -S2_DEV_BPS / 10000.0:
        return []  # the last hour was not a dip leg
    if closes[-1] / closes[-2] - 1.0 <= S2_REV_BPS / 10000.0:
        return []  # still falling: wait for the first reversal bar
    notional = min(state.cash, state.equity * S2_WEIGHT_BPS // 10000)
    if notional < 1_000_000:
        return []
    held_since = seq
    pos_sleeve = "s2"
    return [{"side": "buy", "symbol": SYMBOL, "notional_quote_units": notional,
             "max_slippage_bps": MAX_SLIPPAGE_BPS}]


def on_batch(state, batch):
    global panic_armed
    for bar in batch["bars"]:
        if bar["symbol"] == SYMBOL:
            closes.append(int(bar["c"]))
            orders = _orders(state)
            # Arming is evaluated after the bar's decisions: a capitulation
            # print on bar t can only arm sleeve 2 from bar t+1 on, exactly
            # as if the print had been observed before the next bar arrives.
            if len(closes) >= MIN_HIST:
                if closes[-1] <= _trailing_high() * (1.0 - ARM_DD_BPS / 10000.0):
                    panic_armed = True
            return orders
    return []


makefun_bars.run(on_batch)
