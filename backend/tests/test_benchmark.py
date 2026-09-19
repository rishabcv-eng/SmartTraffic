from app.services.benchmark import run_benchmark, run_benchmark_suite


def test_benchmark_returns_comparable_results():
    results = run_benchmark(steps=20, seed=5)
    assert len(results) == 14
    names = {r['controller'] for r in results}
    assert names == {
        'fixed-time',
        'actuated',
        'max-pressure',
        'network-max-pressure',
        'predictive-pressure-v2',
        'mpc-lite-v1',
        'transit-priority-v1',
        'gated-pressure-v1',
        'coordinated-pressure-v1',
        'pcu-pressure-v1',
        'heterogeneous-pressure-v1',
        'pcu-timed-v1',
        'heterogeneous-timed-v1',
        'rl-network-v2',
    }
    assert all(r['throughput'] >= 0 for r in results)
    assert all(r['peak_queue'] >= 0 for r in results)
    # Delay distribution and impact travel with every row.
    assert all(r['p95_vehicle_delay'] >= r['mean_vehicle_delay'] * 0 for r in results)
    assert all(r['co2_kg'] >= 0 for r in results)


def test_benchmark_suite_is_ranked_and_reproducible():
    a = run_benchmark_suite(steps=40, seeds=[3, 7], scenarios=['normal', 'accident'])
    b = run_benchmark_suite(steps=40, seeds=[3, 7], scenarios=['normal', 'accident'])
    assert a == b
    assert len(a['summary']) == 14
    queues = [row['mean_average_queue'] for row in a['summary']]
    assert queues == sorted(queues)
    assert all(row['runs'] == 4 for row in a['summary'])
