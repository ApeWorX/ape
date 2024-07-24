def test_compile_performance(benchmark, project_with_contracts):
    """
    See https://pytest-benchmark.readthedocs.io/en/latest/
    """
    benchmark.pedantic(
        lambda *args, **kwargs: project_with_contracts.get_contract(*args, **kwargs),
        args=(("Other",),),
        rounds=5,
        warmup_rounds=1,  # It's always slower the first time, a little bit.
    )

    # Get the median of the measured times
    stats = benchmark.stats
    median = stats.get("median")
    assert median < 0.0002
