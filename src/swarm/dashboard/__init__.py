"""Dashboard — FastAPI web interface for experiment visualization."""


def run_dashboard(host: str = "127.0.0.1", port: int = 8050):
    import uvicorn
    from swarm.dashboard.app import app
    uvicorn.run(app, host=host, port=port)
