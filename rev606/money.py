"""Exact money arithmetic and allocation with penny reconciliation.

Revenue allocation is where floating point quietly breaks an audit. Splitting
$1,000 three ways gives 333.33 x 3 = 999.99, and the missing cent has to land
somewhere deterministic rather than vanish. Everything here is Decimal, and
every allocation is forced to sum to its input.
"""

from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")


def money(value):
    """Coerce to a 2dp Decimal. Accepts str, int, float, Decimal."""
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def allocate(total, weights):
    """Split `total` across `weights` in proportion, summing exactly to total.

    The largest-remainder method: floor each share, then hand the leftover
    pennies to the shares with the largest truncated remainder. This keeps the
    allocation deterministic and the total exact, which a naive round-each-share
    does not.

    Returns a list of Decimals, same length as weights.
    """
    total = money(total)
    weights = [Decimal(str(w)) for w in weights]
    if not weights:
        return []
    denom = sum(weights)
    if denom == 0:
        raise ValueError("cannot allocate across zero total weight")

    exact = [total * w / denom for w in weights]
    floored = [e.quantize(CENT, rounding="ROUND_DOWN") for e in exact]
    shortfall = int(((total - sum(floored)) / CENT).to_integral_value())

    # Largest remainder first; ties broken by position for determinism.
    order = sorted(
        range(len(weights)),
        key=lambda i: (-(exact[i] - floored[i]), i),
    )
    for k in range(shortfall):
        floored[order[k % len(order)]] += CENT
    return floored


def fmt(amount):
    return f"{amount:>12,.2f}"
