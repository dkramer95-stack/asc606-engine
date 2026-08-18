"""Steps 4 and 5: allocate the transaction price, then build the schedule.

Step 4 allocates on relative standalone selling price. Step 5 recognizes each
obligation's allocated amount as control transfers, by month.
"""

from collections import OrderedDict
from datetime import date
from decimal import Decimal

from .model import INPUT_METHOD, POINT_IN_TIME, RATABLE
from .money import CENT, allocate, money


def month_key(d):
    return f"{d.year:04d}-{d.month:02d}"


def months_between(start, end):
    """Inclusive list of YYYY-MM keys from start through end."""
    if end < start:
        return []
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def allocate_price(contract):
    """Step 4 — relative standalone selling price allocation.

    Any discount is allocated proportionately across all obligations, which is
    the default. ASC 606-10-32-37 permits allocating a discount entirely to
    specific obligations only when there is observable evidence the discount
    belongs to them; that is a judgment the engine does not make silently.
    """
    weights = [o.ssp for o in contract.obligations]
    amounts = allocate(contract.transaction_price, weights)
    return OrderedDict((o.id, amt) for o, amt in zip(contract.obligations, amounts))


def _schedule_for(ob, allocated):
    """Month -> amount recognized, for a single obligation."""
    if ob.method == POINT_IN_TIME:
        return OrderedDict([(month_key(ob.satisfaction_date), allocated)])

    if ob.method == RATABLE:
        keys = months_between(ob.start, ob.end)
        amounts = allocate(allocated, [1] * len(keys))
        return OrderedDict(zip(keys, amounts))

    if ob.method == INPUT_METHOD:
        # Progress is cumulative percent complete. Revenue for a month is the
        # increment, so a downward revision produces a negative catch-up rather
        # than being silently floored at zero -- ASC 606-10-25-35 treats a change
        # in measured progress as a change in estimate.
        keys = sorted(ob.progress)
        out, prior_cum = OrderedDict(), Decimal("0")
        for i, k in enumerate(keys):
            pct = Decimal(str(ob.progress[k]))
            if not (Decimal("0") <= pct <= Decimal("1")):
                raise ValueError(f"{ob.id}: progress {pct} outside 0..1 at {k}")
            cum = (allocated * pct).quantize(CENT)
            if i == len(keys) - 1 and pct == Decimal("1"):
                cum = allocated  # final period absorbs rounding
            out[k] = cum - prior_cum
            prior_cum = cum
        return out

    raise ValueError(f"{ob.id}: unhandled method {ob.method}")


def build_schedule(contract):
    """Step 5 — {obligation_id: {month: amount}}, plus a combined total row."""
    allocated = allocate_price(contract)
    per_ob = OrderedDict(
        (ob.id, _schedule_for(ob, allocated[ob.id])) for ob in contract.obligations
    )
    months = sorted({m for sched in per_ob.values() for m in sched})
    totals = OrderedDict(
        (m, money(sum(sched.get(m, 0) for sched in per_ob.values()))) for m in months
    )
    return {"allocated": allocated, "by_obligation": per_ob, "months": months, "totals": totals}


def rollforward(contract, schedule, billings=None):
    """Contract liability rollforward — the tie-out an auditor actually asks for.

    Deferred revenue closing = opening + billed - recognized. When nothing is
    billed the schedule still reconciles, showing the full transaction price
    moving from unrecognized to recognized.
    """
    billings = billings or {}
    rows, opening = [], Decimal("0")
    for m in schedule["months"]:
        billed = money(billings.get(m, 0))
        recognized = schedule["totals"][m]
        closing = money(opening + billed - recognized)
        # ASC 606-10-45-1: the net contract position is presented as a contract
        # liability when the entity has been paid ahead of performance, and as a
        # contract asset when it has performed ahead of billing. It is one net
        # position per contract whose sign decides the caption -- reporting a
        # "negative contract liability" would be wrong on the face of the
        # balance sheet even though the arithmetic is right.
        rows.append(
            {"month": m, "opening": opening, "billed": billed,
             "recognized": recognized, "closing": closing,
             "position": "contract liability" if closing > 0
                         else ("contract asset" if closing < 0 else "nil")}
        )
        opening = closing
    return rows


def journal_entries(contract, schedule, billings=None):
    """Double-entry postings per month. Debits must equal credits, always."""
    billings = billings or {}
    entries = []
    for m in schedule["months"]:
        billed = money(billings.get(m, 0))
        if billed:
            entries.append({"month": m, "account": "Accounts receivable", "dr": billed, "cr": Decimal("0"),
                            "memo": f"{contract.id} billing"})
            entries.append({"month": m, "account": "Contract liability", "dr": Decimal("0"), "cr": billed,
                            "memo": f"{contract.id} billing"})
        for ob in contract.obligations:
            amt = schedule["by_obligation"][ob.id].get(m)
            if not amt:
                continue
            entries.append({"month": m, "account": "Contract liability", "dr": amt, "cr": Decimal("0"),
                            "memo": f"{contract.id} {ob.id} recognition"})
            entries.append({"month": m, "account": "Revenue", "dr": Decimal("0"), "cr": amt,
                            "memo": f"{contract.id} {ob.id} recognition"})
    return entries
