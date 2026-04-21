"""Run an experiment. Logging is handled by SimulationLogger from config."""
import sys

sys.path.insert(0, "src")

from swarm.simulation.runner import ExperimentRunner


def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else "configs/experiments/quick_test.yaml"
    runner = ExperimentRunner(config_path)
    result = runner.run()

    # Print emergence events at the end
    detector = runner.detector
    if detector and detector.events:
        print(f"\n  Emergence events ({len(detector.events)}):")
        for event in detector.events:
            print(f"    [{event.tick:2d}] {event.event_type}: {event.description}")

    # Final metric summary
    metrics = detector.metric_history if detector else {}
    print(f"\n  Final metrics:")
    for name in ["consensus", "variance", "polarization_bc", "modularity", "echo_chamber_index"]:
        if name in metrics and metrics[name]:
            print(f"    {name}: {metrics[name][-1]:.4f}")


if __name__ == "__main__":
    main()
