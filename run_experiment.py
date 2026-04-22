"""Run an experiment or counterfactual analysis. Logging handled by SimulationLogger."""
import sys

import yaml

sys.path.insert(0, "src")

from swarm.simulation.runner import ExperimentRunner
from swarm.simulation.intervention import CounterfactualRunner


def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else "configs/experiments/quick_test.yaml"

    with open(config_path) as f:
        config = yaml.safe_load(f)

    if "counterfactual" in config:
        print(f"Running counterfactual analysis from: {config_path}")
        runner = CounterfactualRunner(config)
        runner.run()
    else:
        runner = ExperimentRunner(config_path)
        result = runner.run()

        detector = runner.detector
        if detector and detector.events:
            print(f"\n  Emergence events ({len(detector.events)}):")
            for event in detector.events:
                print(f"    [{event.tick:2d}] {event.event_type}: {event.description}")

        metrics = detector.metric_history if detector else {}
        print(f"\n  Final metrics:")
        for name in ["consensus", "variance", "polarization_bc", "modularity", "echo_chamber_index"]:
            if name in metrics and metrics[name]:
                print(f"    {name}: {metrics[name][-1]:.4f}")


if __name__ == "__main__":
    main()
