"""Contract modifications — ASC 606-10-25-10 through 25-13.

Three outcomes, and picking the wrong one misstates revenue in opposite
directions:

  separate_contract  Added goods are distinct AND priced at their standalone
                     selling price. Accounted for independently; the original
                     contract is untouched.

  prospective        Remaining goods are distinct but the pricing does not
                     reflect standalone selling prices. Treated as terminating
                     the old contract and starting a new one: unrecognized
                     consideration plus the modification is allocated over the
                     remaining obligations. No catch-up.

  cumulative_catchup Remaining goods are NOT distinct -- the modification lands
                     inside a single partially satisfied obligation. Revenue is
                     trued up immediately for the change in transaction price
                     applied to progress already made.
"""

from decimal import Decimal

from .money import money

SEPARATE = "separate_contract"
PROSPECTIVE = "prospective"
CATCHUP = "cumulative_catchup"


def classify(adds_distinct_goods, priced_at_ssp, remaining_goods_distinct):
    """Return which of the three treatments applies."""
    if adds_distinct_goods and priced_at_ssp:
        return SEPARATE
    if remaining_goods_distinct:
        return PROSPECTIVE
    return CATCHUP


def prospective_amount(original_price, recognized_to_date, modification_price):
    """Consideration to spread over the remaining obligations, going forward."""
    unrecognized = money(original_price) - money(recognized_to_date)
    if unrecognized < 0:
        raise ValueError("recognized to date exceeds the original transaction price")
    return money(unrecognized + money(modification_price))


def catchup_adjustment(new_transaction_price, percent_complete, recognized_to_date):
    """Immediate true-up when a modification hits a partially satisfied obligation.

    Positive result is additional revenue this period; negative is a reversal.
    A negative catch-up is a legitimate outcome, not an error -- a price
    reduction on work already performed reverses revenue previously recognized.
    """
    pct = Decimal(str(percent_complete))
    if not (Decimal("0") <= pct <= Decimal("1")):
        raise ValueError(f"percent_complete {pct} outside 0..1")
    should_be = money(money(new_transaction_price) * pct)
    return money(should_be - money(recognized_to_date))
