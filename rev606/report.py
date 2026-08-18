"""Human-readable output. Every table ties to the transaction price."""

from .money import fmt, money


def _rule(width):
    return "-" * width


def allocation_table(contract, schedule):
    lines = [f"STEP 4 - ALLOCATION  ({contract.id}, {contract.customer})", ""]
    lines.append(f"{'obligation':<28} {'method':<15} {'SSP':>12} {'allocated':>12}")
    lines.append(_rule(70))
    for ob in contract.obligations:
        lines.append(f"{ob.name[:28]:<28} {ob.method:<15} {fmt(ob.ssp)} {fmt(schedule['allocated'][ob.id])}")
    lines.append(_rule(70))
    lines.append(f"{'TOTAL':<28} {'':<15} {fmt(contract.total_ssp)} {fmt(sum(schedule['allocated'].values()))}")
    if contract.discount:
        lines.append(f"\nDiscount of {fmt(contract.discount).strip()} allocated proportionately across all obligations.")
    if contract.variable:
        lines.append("\nVariable consideration (step 3, constrained):")
        for v in contract.variable:
            lines.append(f"  {v.description}: estimate {fmt(v.estimate).strip()}, "
                         f"included {fmt(v.constrained_to).strip()} - {v.basis}")
    return "\n".join(lines)


def schedule_table(contract, schedule):
    months = schedule["months"]
    w = 12
    head = f"{'obligation':<28}" + "".join(f"{m:>{w}}" for m in months) + f"{'total':>{w}}"
    lines = [f"STEP 5 - RECOGNITION SCHEDULE  ({contract.id})", "", head, _rule(len(head))]
    for ob in contract.obligations:
        sched = schedule["by_obligation"][ob.id]
        row = f"{ob.name[:28]:<28}"
        for m in months:
            row += f"{sched.get(m, ''):>{w},.2f}" if sched.get(m) else f"{'-':>{w}}"
        row += f"{sum(sched.values()):>{w},.2f}"
        lines.append(row)
    lines.append(_rule(len(head)))
    total_row = f"{'TOTAL':<28}"
    for m in months:
        total_row += f"{schedule['totals'][m]:>{w},.2f}"
    total_row += f"{sum(schedule['totals'].values()):>{w},.2f}"
    lines.append(total_row)
    return "\n".join(lines)


def rollforward_table(rows):
    lines = ["CONTRACT POSITION ROLLFORWARD", "",
             f"{'month':<10}{'opening':>14}{'billed':>14}{'recognized':>14}{'closing':>14}"
             f"  {'presented as':<18}",
             _rule(86)]
    for r in rows:
        # Contract assets are shown as positive amounts under their own caption
        # rather than as negative liabilities.
        shown = abs(r["closing"])
        lines.append(f"{r['month']:<10}{r['opening']:>14,.2f}{r['billed']:>14,.2f}"
                     f"{r['recognized']:>14,.2f}{shown:>14,.2f}  {r['position']:<18}")
    return "\n".join(lines)


def journal_table(entries):
    lines = ["JOURNAL ENTRIES", "",
             f"{'month':<10}{'account':<24}{'debit':>14}{'credit':>14}  memo", _rule(90)]
    dr = cr = money(0)
    for e in entries:
        dr += e["dr"]
        cr += e["cr"]
        lines.append(f"{e['month']:<10}{e['account']:<24}{e['dr']:>14,.2f}{e['cr']:>14,.2f}  {e['memo']}")
    lines.append(_rule(90))
    lines.append(f"{'':<34}{dr:>14,.2f}{cr:>14,.2f}   {'balanced' if dr == cr else 'OUT OF BALANCE'}")
    return "\n".join(lines)
