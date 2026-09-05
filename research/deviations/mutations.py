"""The seeded-deviation set.

A commit corpus contains few deliberate design violations, and none of them are
labelled. This set supplies both: each mutation is a small, reproducible edit to
the reference project, annotated with what *should* happen.

Two independent expectations per mutation, because they are genuinely different
questions:

* `expect_structural_change` -- should the gate notice anything at all? This is
  what separates a real edit from formatting noise, and it is the gate's
  precision that is on trial.
* `expect_conformance_change` -- should the deterministic findings differ from
  the baseline? This is what separates a change that matters for conformance
  from one that does not.

The interesting cells are where the two disagree. A consistent rename changes
conformance (the diagram still names the old class) but leaves the graph
isomorphic, so the isomorphism gate will reuse and be wrong: that is a known,
measurable false negative, not a surprise, and reporting it honestly is more
useful than hiding it.
"""
import os
import re
from dataclasses import dataclass
from typing import Callable, Dict, List

SERVICE = "service/order_service.py"
REPOSITORY = "persistence/repository.py"
CONTROLLER = "api/order_controller.py"
DOMAIN = "domain/order.py"


@dataclass
class Mutation:
    id: str
    description: str
    category: str  # positive | negative | structural-only
    expect_structural_change: bool
    expect_conformance_change: bool
    apply: Callable[[str], None]
    rationale: str = ""


# --- helpers -----------------------------------------------------------------


def _read(tree: str, relative: str) -> str:
    with open(os.path.join(tree, relative), "r", encoding="utf-8") as handle:
        return handle.read()


def _write(tree: str, relative: str, content: str) -> None:
    path = os.path.join(tree, relative)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def _replace(tree: str, relative: str, old: str, new: str) -> None:
    content = _read(tree, relative)
    if old not in content:
        raise AssertionError(f"Mutation target not found in {relative}: {old[:60]!r}")
    _write(tree, relative, content.replace(old, new, 1))


# --- positive: conformance-relevant deviations --------------------------------


def delete_designed_method(tree: str) -> None:
    _replace(
        tree,
        SERVICE,
        "    def refund(self, order_id: str) -> bool:\n        return self.repo.delete(order_id)\n",
        "",
    )


def add_undocumented_class(tree: str) -> None:
    _write(
        tree,
        "service/shipping.py",
        '"""Added without a corresponding element in the diagram."""\n\n\n'
        "class ShippingCalculator:\n"
        "    def quote(self, weight: float) -> float:\n"
        "        return weight * 2.5\n",
    )


def remove_realization(tree: str) -> None:
    _replace(tree, REPOSITORY, "class OrderRepository(Repository):", "class OrderRepository:")


def break_association(tree: str) -> None:
    """The service keeps working but no longer declares what it collaborates with."""
    _replace(
        tree,
        SERVICE,
        "    def __init__(self, repo: OrderRepository, audit: \"AuditLog\" = None):\n"
        "        self.repo = repo\n",
        "    def __init__(self, dependencies):\n"
        "        self.repo = dependencies[0]\n",
    )
    _replace(tree, SERVICE, "        self.audit = audit\n", "        self.audit = None\n")


def controller_bypasses_service(tree: str) -> None:
    _replace(
        tree,
        CONTROLLER,
        "from service.order_service import OrderService",
        "from persistence.repository import OrderRepository\nfrom service.order_service import OrderService",
    )
    _replace(
        tree,
        CONTROLLER,
        "    def get(self, order_id: str) -> dict:\n        return {\"id\": order_id}\n",
        "    def get(self, order_id: str) -> dict:\n"
        "        repository = OrderRepository()\n"
        "        return {\"id\": order_id, \"row\": repository.find_by_id(order_id)}\n",
    )


def invert_dependency(tree: str) -> None:
    """Persistence calls back into the application layer."""
    _replace(
        tree,
        REPOSITORY,
        "from domain.order import Order",
        "from domain.order import Order\nfrom service.order_service import AuditLog",
    )
    _replace(
        tree,
        REPOSITORY,
        "    def __init__(self):\n        self.rows = {}\n",
        "    def __init__(self):\n        self.rows = {}\n        self.audit = AuditLog()\n",
    )
    _replace(
        tree,
        REPOSITORY,
        "        self.rows[entity.order_id] = entity\n        return True\n",
        "        self.rows[entity.order_id] = entity\n"
        "        self.audit.record(entity.order_id)\n"
        "        return True\n",
    )


def rename_class_partially(tree: str) -> None:
    """Rename the class but not its references -- a broken, in-progress refactor."""
    _replace(tree, REPOSITORY, "class OrderRepository(Repository):", "class OrderStore(Repository):")


def rename_class_consistently(tree: str) -> None:
    """A complete rename: the code still works, but the diagram now names a class
    that no longer exists. Shape-preserving, so the isomorphism gate will reuse."""
    for relative in (REPOSITORY, SERVICE, CONTROLLER):
        content = _read(tree, relative)
        _write(tree, relative, content.replace("OrderRepository", "OrderStore"))


def delete_designed_class(tree: str) -> None:
    _replace(
        tree,
        SERVICE,
        "class AuditLog:\n"
        "    def __init__(self):\n"
        "        self.entries = []\n\n"
        "    def record(self, message: str) -> None:\n"
        "        self.entries.append(message)\n",
        "",
    )
    _replace(tree, SERVICE, '    def __init__(self, repo: OrderRepository, audit: "AuditLog" = None):', "    def __init__(self, repo: OrderRepository, audit=None):")


# --- structural-only: real change, no conformance consequence ------------------


def add_private_helper(tree: str) -> None:
    """A new internal method the diagram never claimed to specify."""
    _replace(
        tree,
        SERVICE,
        "    def refund(self, order_id: str) -> bool:",
        "    def _log(self, message: str) -> None:\n"
        "        if self.audit is not None:\n"
        "            self.audit.record(message)\n\n"
        "    def refund(self, order_id: str) -> bool:",
    )


def change_parameter_count(tree: str) -> None:
    """Same operation name, different arity: structural, but the comparison is
    by name, so conformance findings do not move."""
    _replace(
        tree,
        DOMAIN,
        "    def total_with_tax(self, rate: float) -> float:\n        return self.total * (1 + rate)\n",
        "    def total_with_tax(self, rate: float, rounding: int = 2) -> float:\n"
        "        return round(self.total * (1 + rate), rounding)\n",
    )


# --- negative controls: must not trigger a structural re-analysis -------------


def comment_only(tree: str) -> None:
    content = _read(tree, SERVICE)
    content = content.replace(
        "    def place(self, order: Order) -> bool:",
        "    # Persist the order and report whether it stuck.\n"
        "    def place(self, order: Order) -> bool:",
    )
    _write(tree, SERVICE, "# Reviewed for the Q3 audit.\n" + content)


def reformat_whitespace(tree: str) -> None:
    """Blank lines and trailing space only -- no indentation is altered, so this
    stays a pure formatting change rather than a restructuring one."""
    content = _read(tree, SERVICE)
    content = content.replace("\n\n", "\n\n\n")
    content = content.replace("        return saved\n", "        return saved   \n")
    _write(tree, SERVICE, content + "\n\n")


def rename_local_variable(tree: str) -> None:
    _replace(
        tree,
        SERVICE,
        "        saved = self.repo.save(order)\n        return saved\n",
        "        persisted = self.repo.save(order)\n        return persisted\n",
    )


def reorder_methods(tree: str) -> None:
    """Move `cancel` after `refund`; the class is unchanged as a set of members."""
    content = _read(tree, SERVICE)
    cancel = (
        "    def cancel(self, order_id: str) -> bool:\n"
        "        order = self.repo.find_by_id(order_id)\n"
        "        if order is None:\n"
        "            return False\n"
        "        order.cancel()\n"
        "        return self.repo.save(order)\n\n"
    )
    if cancel not in content:
        raise AssertionError("reorder_methods target not found")
    content = content.replace(cancel, "")
    content = content.replace(
        "    def refund(self, order_id: str) -> bool:\n        return self.repo.delete(order_id)\n",
        "    def refund(self, order_id: str) -> bool:\n        return self.repo.delete(order_id)\n\n"
        + cancel.rstrip("\n")
        + "\n",
    )
    _write(tree, SERVICE, content)


def add_docstring(tree: str) -> None:
    _replace(
        tree,
        CONTROLLER,
        "    def get(self, order_id: str) -> dict:\n",
        '    def get(self, order_id: str) -> dict:\n        """Return a stub payload for the order."""\n',
    )


# --- the set ------------------------------------------------------------------

MUTATIONS: List[Mutation] = [
    Mutation(
        id="delete-designed-method",
        description="Remove OrderService.refund(), which the diagram specifies.",
        category="positive",
        expect_structural_change=True,
        expect_conformance_change=True,
        apply=delete_designed_method,
        rationale="A designed operation disappears; the checker must report it missing.",
    ),
    Mutation(
        id="add-undocumented-class",
        description="Add ShippingCalculator, absent from the diagram.",
        category="positive",
        expect_structural_change=True,
        expect_conformance_change=True,
        apply=add_undocumented_class,
        rationale="Undocumented code is a conformance gap in the other direction.",
    ),
    Mutation(
        id="remove-realization",
        description="OrderRepository stops implementing Repository.",
        category="positive",
        expect_structural_change=True,
        expect_conformance_change=True,
        apply=remove_realization,
        rationale="A modelled realization is no longer implemented.",
    ),
    Mutation(
        id="break-association",
        description="Replace the typed repo field with an untyped positional dependency.",
        category="positive",
        expect_structural_change=True,
        expect_conformance_change=True,
        apply=break_association,
        rationale="The association loses its evidence: the collaboration is invisible in the code.",
    ),
    Mutation(
        id="controller-bypasses-service",
        description="The controller instantiates and queries the repository directly.",
        category="positive",
        expect_structural_change=True,
        expect_conformance_change=True,
        apply=controller_bypasses_service,
        rationale="A layering violation the rule engine should catch with evidence.",
    ),
    Mutation(
        id="invert-dependency",
        description="The repository calls back into the application layer.",
        category="positive",
        expect_structural_change=True,
        expect_conformance_change=True,
        apply=invert_dependency,
        rationale="Dependency inversion in the wrong direction.",
    ),
    Mutation(
        id="rename-class-partially",
        description="Rename OrderRepository but leave its references pointing at the old name.",
        category="positive",
        expect_structural_change=True,
        expect_conformance_change=True,
        apply=rename_class_partially,
        rationale="A half-finished refactor: the class the diagram names is gone.",
    ),
    Mutation(
        id="rename-class-consistently",
        description="Rename OrderRepository to OrderStore everywhere.",
        category="positive",
        expect_structural_change=True,
        expect_conformance_change=True,
        apply=rename_class_consistently,
        rationale=(
            "The code still works and the graph is isomorphic, but the diagram names a class "
            "that no longer exists. This is the case where the isomorphism gate is expected to "
            "be wrong; the point of the experiment is to measure how often that costs anything."
        ),
    ),
    Mutation(
        id="delete-designed-class",
        description="Remove AuditLog entirely.",
        category="positive",
        expect_structural_change=True,
        expect_conformance_change=True,
        apply=delete_designed_class,
        rationale="A whole designed element vanishes.",
    ),
    Mutation(
        id="add-private-helper",
        description="Add an internal helper method the diagram never specified.",
        category="structural-only",
        expect_structural_change=True,
        expect_conformance_change=True,
        apply=add_private_helper,
        rationale=(
            "Structure changes and the member appears as undocumented, so findings do move. "
            "Kept separate from the layering cases because nothing is actually wrong."
        ),
    ),
    Mutation(
        id="change-parameter-count",
        description="Add an optional parameter to Order.total_with_tax().",
        category="structural-only",
        expect_structural_change=True,
        expect_conformance_change=False,
        apply=change_parameter_count,
        rationale=(
            "Signatures are compared by name, not arity, so the gate fires but the findings are "
            "identical. This measures how much re-analysis the fingerprint buys that the "
            "conformance check does not use."
        ),
    ),
    Mutation(
        id="comment-only",
        description="Add comments and a file header.",
        category="negative",
        expect_structural_change=False,
        expect_conformance_change=False,
        apply=comment_only,
        rationale="The canonical thing a structural gate must ignore.",
    ),
    Mutation(
        id="reformat-whitespace",
        description="Add blank lines and adjust spacing.",
        category="negative",
        expect_structural_change=False,
        expect_conformance_change=False,
        apply=reformat_whitespace,
        rationale="Formatting must never cost a model call.",
    ),
    Mutation(
        id="rename-local-variable",
        description="Rename a local variable inside OrderService.place().",
        category="negative",
        expect_structural_change=False,
        expect_conformance_change=False,
        apply=rename_local_variable,
        rationale=(
            "Locals are excluded from the fingerprint by design; this test is what keeps that "
            "decision honest."
        ),
    ),
    Mutation(
        id="reorder-methods",
        description="Move cancel() below refund() without changing either.",
        category="negative",
        expect_structural_change=False,
        expect_conformance_change=False,
        apply=reorder_methods,
        rationale="Declaration order is not architecture.",
    ),
    Mutation(
        id="add-docstring",
        description="Add a docstring to a controller method.",
        category="negative",
        expect_structural_change=False,
        expect_conformance_change=False,
        apply=add_docstring,
        rationale="Documentation edits must be free.",
    ),
]

BY_ID: Dict[str, Mutation] = {mutation.id: mutation for mutation in MUTATIONS}


def branch_name(mutation: Mutation) -> str:
    return "deviation/" + re.sub(r"[^a-z0-9-]+", "-", mutation.id.lower())
