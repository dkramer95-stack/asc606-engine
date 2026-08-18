"""Tests for the ASC 606 engine.

Focused on the invariants that make a revenue schedule auditable: allocation
ties to the transaction price, the schedule ties to the allocation, debits
equal credits, and the constraint is actually applied.
"""

import json
import os
import sys
import unittest
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rev606.engine import build_schedule, journal_entries, months_between, rollforward
from rev606.model import (INPUT_METHOD, POINT_IN_TIME, RATABLE, Contract,
                          PerformanceObligation, VariableConsideration,
                          contract_from_dict)
from rev606.modification import (CATCHUP, PROSPECTIVE, SEPARATE,
                                 catchup_adjustment, classify, prospective_amount)
from rev606.money import allocate, money


def simple(fixed="10000.00", variable=None):
    return Contract(
        id="T", customer="Test", inception="2026-01-01",
        fixed_consideration=fixed,
        variable=variable or [],
        obligations=[
            PerformanceObligation("a", "License", "4000", POINT_IN_TIME, satisfaction_date="2026-01-15"),
            PerformanceObligation("b", "Support", "6000", RATABLE, start="2026-01-01", end="2026-06-30"),
        ],
    )


class TestAllocationArithmetic(unittest.TestCase):
    def test_allocation_sums_exactly(self):
        for total, weights in [("1000.00", [1, 1, 1]), ("10000.00", [4000, 3500, 1200]),
                               ("0.03", [1, 1, 1]), ("99999.99", [7, 11, 13, 17])]:
            parts = allocate(total, weights)
            self.assertEqual(sum(parts), money(total), f"{total} across {weights}")

    def test_allocation_is_deterministic(self):
        self.assertEqual(allocate("1000.00", [1, 1, 1]), allocate("1000.00", [1, 1, 1]))

    def test_zero_weight_rejected(self):
        with self.assertRaises(ValueError):
            allocate("100.00", [0, 0])


class TestStepThreeConstraint(unittest.TestCase):
    def test_only_constrained_amount_enters_transaction_price(self):
        vc = VariableConsideration("v", "bonus", estimate="24000", constrained_to="9000",
                                   basis="most likely amount")
        c = simple(variable=[vc])
        self.assertEqual(c.transaction_price, money("19000.00"))

    def test_constraint_cannot_exceed_estimate(self):
        with self.assertRaises(ValueError):
            VariableConsideration("v", "bonus", estimate="1000", constrained_to="2000")


class TestStepFourAllocation(unittest.TestCase):
    def test_allocation_ties_to_transaction_price(self):
        c = simple()
        s = build_schedule(c)
        self.assertEqual(sum(s["allocated"].values()), c.transaction_price)

    def test_discount_spread_proportionately(self):
        c = simple(fixed="5000.00")   # SSP totals 10,000 -> 50% discount
        s = build_schedule(c)
        self.assertEqual(s["allocated"]["a"], money("2000.00"))
        self.assertEqual(s["allocated"]["b"], money("3000.00"))
        self.assertEqual(c.discount, money("5000.00"))


class TestStepFiveSchedule(unittest.TestCase):
    def test_schedule_ties_to_allocation(self):
        c = simple()
        s = build_schedule(c)
        for ob_id, sched in s["by_obligation"].items():
            self.assertEqual(sum(sched.values()), s["allocated"][ob_id], ob_id)

    def test_total_recognized_equals_transaction_price(self):
        c = simple()
        s = build_schedule(c)
        self.assertEqual(sum(s["totals"].values()), c.transaction_price)

    def test_point_in_time_lands_in_one_month(self):
        c = simple()
        s = build_schedule(c)
        self.assertEqual(list(s["by_obligation"]["a"]), ["2026-01"])

    def test_ratable_is_even_across_months(self):
        c = simple()
        s = build_schedule(c)
        amounts = list(s["by_obligation"]["b"].values())
        self.assertEqual(len(amounts), 6)
        self.assertEqual(sum(amounts), money("6000.00"))
        self.assertLessEqual(max(amounts) - min(amounts), money("0.01"))

    def test_input_method_recognizes_increments_not_cumulative(self):
        ob = PerformanceObligation("i", "Impl", "1000", INPUT_METHOD,
                                   progress={"2026-01": 0.25, "2026-02": 0.60, "2026-03": 1.00})
        c = Contract("T2", "Test", "2026-01-01", "1000", [ob])
        s = build_schedule(c)
        got = list(s["by_obligation"]["i"].values())
        self.assertEqual(got, [money("250.00"), money("350.00"), money("400.00")])
        self.assertEqual(sum(got), money("1000.00"))

    def test_downward_revision_produces_negative_catchup(self):
        # A reduction in measured progress is a change in estimate, and must
        # reverse revenue rather than be floored at zero.
        ob = PerformanceObligation("i", "Impl", "1000", INPUT_METHOD,
                                   progress={"2026-01": 0.80, "2026-02": 0.50, "2026-03": 1.00})
        c = Contract("T3", "Test", "2026-01-01", "1000", [ob])
        s = build_schedule(c)
        amounts = list(s["by_obligation"]["i"].values())
        self.assertLess(amounts[1], 0)
        self.assertEqual(sum(amounts), money("1000.00"))

    def test_progress_outside_range_rejected(self):
        with self.assertRaises(ValueError):
            build_schedule(Contract("T4", "T", "2026-01-01", "100", [
                PerformanceObligation("i", "Impl", "100", INPUT_METHOD, progress={"2026-01": 1.5})]))


class TestRollforwardAndJournal(unittest.TestCase):
    def test_rollforward_closes_at_zero_when_fully_billed(self):
        c = simple()
        s = build_schedule(c)
        rows = rollforward(c, s, {"2026-01": c.transaction_price})
        self.assertEqual(rows[-1]["closing"], money("0.00"))

    def test_rollforward_is_continuous(self):
        c = simple()
        s = build_schedule(c)
        rows = rollforward(c, s, {"2026-01": "5000"})
        for prev, nxt in zip(rows, rows[1:]):
            self.assertEqual(prev["closing"], nxt["opening"])

    def test_position_flips_to_contract_asset_when_performance_leads(self):
        c = simple()
        s = build_schedule(c)
        rows = rollforward(c, s, {})          # nothing billed at all
        self.assertTrue(any(r["position"] == "contract asset" for r in rows))

    def test_journal_balances(self):
        c = simple()
        s = build_schedule(c)
        entries = journal_entries(c, s, {"2026-01": "10000"})
        self.assertEqual(sum(e["dr"] for e in entries), sum(e["cr"] for e in entries))


class TestModifications(unittest.TestCase):
    def test_classification(self):
        self.assertEqual(classify(True, True, True), SEPARATE)
        self.assertEqual(classify(True, False, True), PROSPECTIVE)
        self.assertEqual(classify(False, False, False), CATCHUP)

    def test_prospective_carries_unrecognized_forward(self):
        self.assertEqual(prospective_amount("100000", "40000", "25000"), money("85000.00"))

    def test_prospective_rejects_impossible_state(self):
        with self.assertRaises(ValueError):
            prospective_amount("100", "500", "0")

    def test_catchup_can_be_negative(self):
        # Price cut on work already half done reverses revenue.
        self.assertEqual(catchup_adjustment("80000", 0.5, "50000"), money("-10000.00"))

    def test_catchup_positive(self):
        self.assertEqual(catchup_adjustment("120000", 0.5, "50000"), money("10000.00"))


class TestValidation(unittest.TestCase):
    def test_duplicate_obligation_ids_rejected(self):
        with self.assertRaises(ValueError):
            Contract("D", "T", "2026-01-01", "100", [
                PerformanceObligation("x", "A", "50", POINT_IN_TIME, satisfaction_date="2026-01-01"),
                PerformanceObligation("x", "B", "50", POINT_IN_TIME, satisfaction_date="2026-01-01")])

    def test_contract_needs_an_obligation(self):
        with self.assertRaises(ValueError):
            Contract("E", "T", "2026-01-01", "100", [])

    def test_ratable_end_before_start_rejected(self):
        with self.assertRaises(ValueError):
            PerformanceObligation("r", "S", "10", RATABLE, start="2026-06-01", end="2026-01-01")

    def test_months_between_inclusive_and_year_crossing(self):
        from datetime import date
        self.assertEqual(months_between(date(2025, 11, 1), date(2026, 2, 28)),
                         ["2025-11", "2025-12", "2026-01", "2026-02"])


class TestSampleContract(unittest.TestCase):
    def test_shipped_contract_ties_out(self):
        path = os.path.join(os.path.dirname(__file__), "..", "contracts", "saas_bundle.json")
        with open(path) as fh:
            c = contract_from_dict(json.load(fh))
        s = build_schedule(c)
        self.assertEqual(sum(s["totals"].values()), c.transaction_price)
        self.assertEqual(c.transaction_price, money("189000.00"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
