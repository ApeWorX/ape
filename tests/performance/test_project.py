def test_get_contract(benchmark, project_with_contracts):
    benchmark.pedantic(
        lambda *args, **kwargs: project_with_contracts.get_contract(*args, **kwargs),
        args=(("Other",),),
        rounds=5,
        warmup_rounds=1,  # It's always slower the first time, a little bit.
    )
    stats = benchmark.stats
    median = stats.get("median")
    assert median < 0.0002
