"""Contract domain model — ASC 606 steps 1 and 2.

A contract carries performance obligations. Identifying them is step 2 and is a
judgment call the engine does not attempt to make: a good is distinct only if
the customer can benefit from it on its own AND it is separately identifiable
within the contract. That determination is an input here, made by a human and
recorded with its rationale, because it is the step most likely to be wrong and
the one an auditor will ask about.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from .money import money

POINT_IN_TIME = "point_in_time"
RATABLE = "ratable"
INPUT_METHOD = "input_method"
METHODS = {POINT_IN_TIME, RATABLE, INPUT_METHOD}


def parse_date(value):
    if isinstance(value, date):
        return value
    return date(*(int(p) for p in value.split("-")))


@dataclass
class PerformanceObligation:
    """A distinct promise in the contract (step 2)."""

    id: str
    name: str
    ssp: Decimal                      # standalone selling price, for step 4
    method: str                       # how control transfers (step 5)
    distinct_rationale: str = ""      # why this was judged distinct
    satisfaction_date: date = None    # point_in_time only
    start: date = None                # ratable only
    end: date = None                  # ratable only
    progress: dict = field(default_factory=dict)  # input_method: {"YYYY-MM": pct_complete}

    def __post_init__(self):
        self.ssp = money(self.ssp)
        if self.method not in METHODS:
            raise ValueError(f"{self.id}: unknown method {self.method!r}")
        for attr in ("satisfaction_date", "start", "end"):
            if getattr(self, attr) and not isinstance(getattr(self, attr), date):
                setattr(self, attr, parse_date(getattr(self, attr)))
        if self.method == POINT_IN_TIME and not self.satisfaction_date:
            raise ValueError(f"{self.id}: point_in_time requires satisfaction_date")
        if self.method == RATABLE and not (self.start and self.end):
            raise ValueError(f"{self.id}: ratable requires start and end")
        if self.method == RATABLE and self.end < self.start:
            raise ValueError(f"{self.id}: end precedes start")
        if self.method == INPUT_METHOD and not self.progress:
            raise ValueError(f"{self.id}: input_method requires progress measurements")


@dataclass
class VariableConsideration:
    """Variable consideration subject to the constraint (step 3).

    ASC 606-10-32-11: include variable consideration only to the extent it is
    probable that a significant reversal will not occur. `estimate` is the
    expected amount; `constrained_to` is the amount that survives the
    constraint. Recording both preserves the judgment instead of burying it in
    a single number.
    """

    id: str
    description: str
    estimate: Decimal
    constrained_to: Decimal
    basis: str = ""

    def __post_init__(self):
        self.estimate = money(self.estimate)
        self.constrained_to = money(self.constrained_to)
        if self.constrained_to > self.estimate:
            raise ValueError(f"{self.id}: constrained amount exceeds the estimate")


@dataclass
class Contract:
    """A customer contract (step 1)."""

    id: str
    customer: str
    inception: date
    fixed_consideration: Decimal
    obligations: list
    variable: list = field(default_factory=list)
    notes: str = ""

    def __post_init__(self):
        self.inception = parse_date(self.inception) if not isinstance(self.inception, date) else self.inception
        self.fixed_consideration = money(self.fixed_consideration)
        if not self.obligations:
            raise ValueError(f"{self.id}: a contract needs at least one performance obligation")
        ids = [o.id for o in self.obligations]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{self.id}: duplicate performance obligation ids")

    @property
    def transaction_price(self):
        """Step 3: fixed consideration plus constrained variable consideration."""
        return money(self.fixed_consideration + sum(v.constrained_to for v in self.variable))

    @property
    def total_ssp(self):
        return money(sum(o.ssp for o in self.obligations))

    @property
    def discount(self):
        """Excess of standalone prices over the transaction price."""
        return money(max(Decimal("0"), self.total_ssp - self.transaction_price))


def contract_from_dict(d):
    obligations = [PerformanceObligation(**o) for o in d["obligations"]]
    variable = [VariableConsideration(**v) for v in d.get("variable", [])]
    return Contract(
        id=d["id"],
        customer=d["customer"],
        inception=d["inception"],
        fixed_consideration=d["fixed_consideration"],
        obligations=obligations,
        variable=variable,
        notes=d.get("notes", ""),
    )
