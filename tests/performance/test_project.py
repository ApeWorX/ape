def test_get_contract(benchmark, smaller_project):
    _ = smaller_project.Other  # Ensure compiled first.
    benchmark.pedantic(
        lambda *args, **kwargs: smaller_project.get_contract(*args, **kwargs),
        args=(("Other",),),
        rounds=5,
        warmup_rounds=1,  # It's always slower the first time, a little bit.
    )
    stats = benchmark.stats
    median = stats.get("median")

    # NOTE: At one point, this was average '0.0007'.
    # When I run locally, I tend to get 0.0001.
    # In CI, when very busy, it can get slower
    assert median < 0.00070
