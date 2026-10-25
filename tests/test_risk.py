import pytest
from hypothesis import given, strategies as st

from human_reliability.bayes import BayesianNetwork, DiscreteNode
from human_reliability.event_tree import (
    Branch,
    event_tree,
    fn_curve,
    individual_risk_rate,
    protection_partition,
)
from human_reliability.fault_tree import (
    Event,
    Gate,
    birnbaum_importance,
    fault_probability,
    fault_probability_joint,
    minimal_cut_sets,
)


@given(st.floats(0, 1), st.floats(0, 1), st.floats(0, 1))
def test_repeated_events_are_boolean_identities(a, b, c):
    tree = Gate("OR", (Gate("AND", (Event("a"), Event("b"))), Gate("AND", (Event("b"), Event("c")))))
    expected = b * (a + c - a * c)
    assert fault_probability(tree, {"a": a, "b": b, "c": c}) == pytest.approx(expected, abs=1e-12)


@pytest.mark.parametrize(
    "tree",
    [
        Gate("NOT", (Event("a"),)),
        Gate("VOTE", (Event("a"), Event("a"), Event("b")), 2),
        Gate("OR", (Gate("AND", (Event("a"), Event("b"))), Event("c"))),
    ],
)
def test_bdd_matches_independent_truth_table(tree):
    from human_reliability.fault_tree import event_ids

    probabilities = {key: 0.17 + 0.13 * i for i, key in enumerate(sorted(event_ids(tree)))}
    assert fault_probability(tree, probabilities, backend="bdd") == pytest.approx(
        fault_probability(tree, probabilities)
    )


def test_minimal_cuts_and_importance():
    tree = Gate("OR", (Event("a"), Gate("AND", (Event("a"), Event("b")))))
    assert minimal_cut_sets(tree) == (frozenset({"a"}),)
    importance = birnbaum_importance(tree, {"a": 0.1, "b": 0.2})
    assert importance == pytest.approx({"a": 1, "b": 0})


def test_correlated_fault_tree_from_bayesian_network():
    network = BayesianNetwork(
        (
            DiscreteNode("common", ("off", "on"), (), {(): (0.9, 0.1)}),
            DiscreteNode("a", ("ok", "fail"), ("common",), {("off",): (0.99, 0.01), ("on",): (0.2, 0.8)}),
            DiscreteNode("b", ("ok", "fail"), ("common",), {("off",): (0.99, 0.01), ("on",): (0.2, 0.8)}),
        )
    )
    assert network.query("a")["fail"] == pytest.approx(0.089)
    states = {}
    for state, p in network.joint_states():
        key = (state["a"] == "fail", state["b"] == "fail")
        states[key] = states.get(key, 0) + p
    joint = [({"a": a, "b": b}, p) for (a, b), p in states.items()]
    tree = Gate("AND", (Event("a"), Event("b")))
    assert fault_probability_joint(tree, joint) == pytest.approx(0.06409)
    assert fault_probability(tree, {"a": 0.089, "b": 0.089}) < fault_probability_joint(tree, joint)


@given(st.floats(0, 1), st.floats(0, 1), st.floats(0, 100))
def test_protection_frequency_is_conserved(pa, qh, frequency):
    ledger = event_tree(frequency, protection_partition(pa, qh, auto_evidence="a", human_evidence="h"))
    assert sum(row["annual_frequency_per_year"] for row in ledger) == pytest.approx(frequency, abs=1e-10)
    assert ledger[-1]["annual_frequency_per_year"] == pytest.approx(frequency * (1 - pa) * qh)


def test_risk_and_fn_conditioning():
    branches = (
        Branch("safe", 0.8, consequence_id="safe", evidence="s"),
        Branch("harm", 0.2, consequence_id="harm", evidence="h"),
    )
    ledger = event_tree(0.01, branches)
    assert individual_risk_rate(ledger, {"safe": 0.0, "harm": 0.5}) == pytest.approx(0.001)
    assert fn_curve(ledger, {"safe": {0: 1.0}, "harm": {0: 0.3, 1: 0.5, 2: 0.2}}, [1, 2]) == pytest.approx(
        {1: 0.0014, 2: 0.0004}
    )
    with pytest.raises(ValueError):
        event_tree(1.0, (Branch("one", 0.3, consequence_id="safe", evidence="x"),))
