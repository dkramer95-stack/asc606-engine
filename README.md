# ASC 606 Revenue Recognition Engine

The five-step model as working software. Give it a contract, get back the transaction
price allocated across performance obligations, a monthly recognition schedule, a
contract position rollforward, and journal entries that balance.

```bash
python3 cli.py contracts/saas_bundle.json --billings 2026-01=100000 2026-07=89000
python3 -m unittest discover -s tests
```

Standard library only.

## The five steps

| Step | Where | Automated |
|---|---|---|
| 1 · Identify the contract | `Contract` | input |
| 2 · Identify performance obligations | `PerformanceObligation.distinct_rationale` | no, on purpose |
| 3 · Determine the transaction price | `VariableConsideration` | input + computed |
| 4 · Allocate to obligations | `allocate_price()` | computed |
| 5 · Recognize as control transfers | `build_schedule()` | computed |

**Step 2 isn't automated deliberately.** Whether a promise is distinct (can the
customer benefit from it on its own, is it separately identifiable in the contract) is
the judgment most likely to be wrong and the first thing an auditor asks about. The
engine makes you record the rationale instead of inferring it, so the reasoning is in
the file rather than in somebody's head.

**Step 3 keeps the estimate and the constrained amount apart.** ASC 606-10-32-11 only
lets you include variable consideration to the extent a significant reversal isn't
probable. Storing just the constrained number throws away the judgment. Storing both,
with the basis, means someone can review it:

```json
{
  "description": "Uptime bonus, 99.95% SLA",
  "estimate": "24000.00",
  "constrained_to": "9000.00",
  "basis": "Most likely amount. Bonus earned in 3 of 8 comparable contracts;
            including the full estimate would risk a significant reversal."
}
```

## Details that decide whether the output is usable

**Contract asset vs contract liability.** When performance runs ahead of billing the net
position flips sign. The arithmetic is easy, the presentation isn't. Under
ASC 606-10-45-1 that's a contract asset, not a negative liability:

```
month            opening        billed    recognized       closing  presented as
2026-04        12,250.00          0.00     11,250.00      1,000.00  contract liability
2026-05         1,000.00          0.00     11,250.00     10,250.00  contract asset
2026-07       -21,500.00     89,000.00     11,250.00     56,250.00  contract liability
```

A negative contract liability would be wrong on the face of the balance sheet even
though the number is right. I had it printing that way before I caught it.

**Measured progress can go down.** Input-method revenue is the increment in cumulative
progress. Revise an estimate downward and the period produces negative revenue. That's
a change in estimate under ASC 606-10-25-35, not an error to clamp at zero. There's a
test on it, because flooring it is the obvious wrong fix.

**Pennies get allocated, not dropped.** Split $1,000 three ways in floating point and
you get $999.99. Allocation is Decimal with largest-remainder, so every split sums
exactly to its input and does it the same way every time. Tested on awkward totals
including $0.03.

**Everything ties.** Allocation to transaction price, schedule to allocation, debits to
credits, rollforward month to month. Those are the assertions in the tests. A revenue
schedule that doesn't foot is worse than no schedule.

## Contract modifications

Three treatments, and picking wrong misstates revenue in opposite directions
(ASC 606-10-25-10 through 25-13):

- **Separate contract.** Added goods are distinct and priced at standalone selling
  price. Original contract untouched.
- **Prospective.** Remaining goods are distinct but not priced at SSP. Treat it as
  terminating the old contract and starting a new one. Unrecognized consideration plus
  the modification spreads over what's left. No catch-up.
- **Cumulative catch-up.** The modification lands inside one partially satisfied
  obligation. True up immediately. The adjustment goes negative when the price is cut on
  work already done.

## Worked example

`contracts/saas_bundle.json`. Three obligations, a discount, and a constrained uptime
bonus. Transaction price $189,000: $180,000 fixed plus $9,000 of a $24,000 estimated
bonus. $21,000 of discount spread proportionately. Platform ratable over 12 months,
implementation on measured progress, training at a point in time.

## Layout

| | |
|---|---|
| `rev606/money.py` | Decimal arithmetic and exact allocation |
| `rev606/model.py` | Contracts, obligations, variable consideration |
| `rev606/engine.py` | Allocation, schedule, rollforward, journal entries |
| `rev606/modification.py` | Modification classification and measurement |
| `rev606/report.py` | Tables |
| `cli.py` | Command line |
| `tests/` | 28 tests |

## Limits

- US GAAP. IFRS 15 is converged in substance but the constraint and licensing guidance
  apply differently.
- Step 2 needs a person. I've argued above that's correct, but it does mean you can't
  hand it a contract PDF and get a schedule.
- One currency per contract, no remeasurement.
- The modification helpers compute the treatment. They don't rewrite a live schedule yet.
- Not a substitute for professional judgment or an audit.

MIT.
