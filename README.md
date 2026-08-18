# ASC 606 Revenue Recognition Engine

The five-step model as working software: takes a contract, allocates the transaction
price across performance obligations, and produces a monthly recognition schedule, a
contract-position rollforward, and balanced journal entries — each tying to the one
before it.

```bash
python3 cli.py contracts/saas_bundle.json --billings 2026-01=100000 2026-07=89000
python3 -m unittest discover -s tests    # 28 tests
```

Standard library only. No dependencies.

## The five steps, and where judgment lives

| Step | Where it happens | Automated? |
|---|---|---|
| 1 · Identify the contract | `Contract` | input |
| 2 · Identify performance obligations | `PerformanceObligation.distinct_rationale` | **input — deliberately** |
| 3 · Determine the transaction price | `VariableConsideration`, constraint applied | input + computed |
| 4 · Allocate to obligations | `allocate_price()` — relative standalone selling price | computed |
| 5 · Recognize as control transfers | `build_schedule()` | computed |

**Step 2 is not automated, on purpose.** Whether a promise is distinct — can the
customer benefit from it on its own, and is it separately identifiable within the
contract — is the judgment most likely to be wrong and the first thing an auditor asks
about. The engine requires the rationale as a recorded field rather than inferring it,
so the reasoning survives in the file instead of in someone's memory.

**Step 3 keeps the estimate and the constrained amount separately.** ASC 606-10-32-11
allows variable consideration only to the extent a significant revenue reversal is not
probable. Storing only the constrained number loses the judgment; storing both, with
the basis, means the position can be reviewed:

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

**Contract asset versus contract liability.** When performance runs ahead of billing,
the net position flips sign. The arithmetic is trivial; the presentation is not. Under
ASC 606-10-45-1 that is a contract *asset*, not a negative liability, and the
rollforward captions it accordingly:

```
month            opening        billed    recognized       closing  presented as
2026-04        12,250.00          0.00     11,250.00      1,000.00  contract liability
2026-05         1,000.00          0.00     11,250.00     10,250.00  contract asset
2026-07       -21,500.00     89,000.00     11,250.00     56,250.00  contract liability
```

A "negative contract liability" would be wrong on the face of the balance sheet even
though the number is right.

**Measured progress can go down.** Input-method revenue is the *increment* in cumulative
progress. If an estimate is revised downward, the period produces negative revenue — a
change in estimate under ASC 606-10-25-35, not an error to be floored at zero. There is
a test asserting exactly that, because clamping it is the obvious wrong fix.

**Pennies are allocated, not dropped.** Splitting $1,000 three ways floats to
$999.99. Allocation uses Decimal with the largest-remainder method, so every split sums
exactly to its input, deterministically. Tested across awkward totals including $0.03.

**Everything ties.** Allocation to transaction price, schedule to allocation, journal
debits to credits, rollforward month to month. Those are the assertions in the test
suite, because a revenue schedule that doesn't foot is worse than no schedule.

## Contract modifications

Three treatments, and choosing wrong misstates revenue in opposite directions
(ASC 606-10-25-10 through 25-13):

- **Separate contract** — added goods are distinct *and* priced at standalone selling
  price. The original contract is untouched.
- **Prospective** — remaining goods are distinct but not priced at SSP. Treated as
  terminating the old contract and starting a new one; unrecognized consideration plus
  the modification is spread over what remains. No catch-up.
- **Cumulative catch-up** — the modification lands inside a single partially satisfied
  obligation. Revenue is trued up immediately, and the adjustment is negative when the
  price is cut on work already performed.

## Worked example

`contracts/saas_bundle.json` — a three-obligation bundle with a discount and a
constrained uptime bonus. Transaction price $189,000: $180,000 fixed plus $9,000 of a
$24,000 estimated bonus. $21,000 of discount spread proportionately. Platform ratable
over 12 months, implementation on measured progress, training at a point in time.

## Layout

| | |
|---|---|
| `rev606/money.py` | Decimal arithmetic, exact allocation |
| `rev606/model.py` | Contract, performance obligations, variable consideration |
| `rev606/engine.py` | Allocation, schedule, rollforward, journal entries |
| `rev606/modification.py` | Modification classification and measurement |
| `rev606/report.py` | Tables |
| `cli.py` | Command line |
| `tests/` | 28 tests |

## Limits

- US GAAP only. IFRS 15 is converged in substance but the constraint and licensing
  guidance differ in application.
- Step 2 requires a human. Presented as a feature above, and it is, but it means the
  engine cannot take a raw contract PDF and produce a schedule unaided.
- Single currency per contract. No remeasurement.
- Modification helpers compute the treatment; they do not yet rewrite a live schedule
  in place.
- Not a substitute for professional judgment or an audit.

MIT licensed.
