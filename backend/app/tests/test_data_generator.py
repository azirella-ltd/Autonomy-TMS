import numpy as np

from app.rl.config import SimulationParams
from app.rl.data_generator import generate_sim_training_windows
from app.services.agents import AgentStrategy


def test_generate_sim_training_windows_pid_strategy():
    params = SimulationParams(order_leadtime=1, supply_leadtime=1, init_inventory=10)

    X, A, P, Y = generate_sim_training_windows(
        num_runs=1,
        T=6,
        window=2,
        horizon=1,
        params=params,
        randomize=False,
        use_simpy=False,
        agent_strategy=AgentStrategy.PID,
    )

    assert X.shape[0] > 0
    assert A.shape == (2, 4, 4)
    assert X.shape[2] == 4  # four nodes in the default topology
    assert Y.shape[1] == 4
    # ensure outputs are finite numbers
    assert np.isfinite(X).all()
    assert np.isfinite(Y).all()
