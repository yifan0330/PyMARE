
from pymare.stats import q_gen, q_profile


def test_q_gen(vars_with_intercept):
    result = q_gen(*vars_with_intercept, 8)
    assert round(result, 4) == 8.0161


def test_q_profile(vars_with_intercept):
    bounds = q_profile(*vars_with_intercept, 0.05)
    assert set(bounds.keys()) == {'ci_l', 'ci_u'}
    assert round(bounds['ci_l'], 4) == 3.8076
    assert round(bounds['ci_u'], 4) == 59.6144
