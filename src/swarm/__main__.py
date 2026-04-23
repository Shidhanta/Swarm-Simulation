"""CLI entrypoint: python -m swarm <command> [args]"""

import sys


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python -m swarm run <config.yaml>      Run an experiment")
        print("  python -m swarm dashboard [port]        Launch dashboard")
        sys.exit(1)

    command = sys.argv[1]

    if command == "run":
        if len(sys.argv) < 3:
            print("Usage: python -m swarm run <config.yaml>")
            sys.exit(1)
        from swarm.simulation.runner import ExperimentRunner
        config_path = sys.argv[2]
        print(f"Running experiment from: {config_path}")
        runner = ExperimentRunner(config_path)
        result = runner.run()
        print(f"\nSimulation complete.")
        print(f"  Ticks: {result.ticks_completed}")
        print(f"  Stop reason: {result.stop_reason}")
        detector = runner.detector
        if detector and detector.events:
            print(f"\nEmergence events detected ({len(detector.events)}):")
            for event in detector.events:
                print(f"  [{event.tick:3d}] {event.event_type}: {event.description}")
        metrics = detector.metric_history if detector else {}
        print(f"\nMetric summary (final tick):")
        for name in ["consensus", "polarization_bc", "variance", "modularity"]:
            if name in metrics and metrics[name]:
                print(f"  {name}: {metrics[name][-1]:.4f}")

    elif command == "dashboard":
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 8050
        from swarm.dashboard import run_dashboard
        print(f"Starting dashboard on http://127.0.0.1:{port}")
        run_dashboard(port=port)

    else:
        print(f"Unknown command: {command}")
        print("Available: run, dashboard")
        sys.exit(1)


if __name__ == "__main__":
    main()
