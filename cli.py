#!/usr/bin/env python3
"""ASC 606 engine CLI.

    python3 cli.py contracts/saas_bundle.json
    python3 cli.py contracts/saas_bundle.json --billings 2026-01=60000
"""

import argparse
import json
import sys

from rev606.engine import build_schedule, journal_entries, rollforward
from rev606.model import contract_from_dict
from rev606.money import money
from rev606.report import allocation_table, journal_table, rollforward_table, schedule_table


def parse_billings(pairs):
    out = {}
    for p in pairs or []:
        month, _, amount = p.partition("=")
        if not amount:
            sys.exit(f"bad --billings value {p!r}; expected YYYY-MM=AMOUNT")
        out[month] = money(amount)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("contract", help="contract JSON file")
    ap.add_argument("--billings", nargs="*", metavar="YYYY-MM=AMT", help="invoiced amounts by month")
    ap.add_argument("--journal", action="store_true", help="also print journal entries")
    a = ap.parse_args()

    with open(a.contract) as fh:
        contract = contract_from_dict(json.load(fh))

    billings = parse_billings(a.billings)
    schedule = build_schedule(contract)

    print(f"CONTRACT {contract.id} - {contract.customer}")
    print(f"Inception {contract.inception}   Transaction price {contract.transaction_price:,.2f}")
    if contract.notes:
        print(f"\n{contract.notes}")
    print()
    print(allocation_table(contract, schedule))
    print()
    print(schedule_table(contract, schedule))
    print()
    print(rollforward_table(rollforward(contract, schedule, billings)))
    if a.journal:
        print()
        print(journal_table(journal_entries(contract, schedule, billings)))

    recognized = sum(schedule["totals"].values())
    print(f"\nTie-out: recognized {recognized:,.2f} vs transaction price "
          f"{contract.transaction_price:,.2f} - "
          f"{'OK' if recognized == contract.transaction_price else 'MISMATCH'}")


if __name__ == "__main__":
    main()
