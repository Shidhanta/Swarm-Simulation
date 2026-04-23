"""FastAPI dashboard application."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from swarm.dashboard.data_loader import ExperimentIndex, ExperimentData

app = FastAPI(title="Swarm Dashboard", version="0.1.0")

PROJECT_ROOT = Path(__file__).resolve().parents[3]
STATIC_DIR = Path(__file__).parent / "static"

index = ExperimentIndex(
    logs_dir=str(PROJECT_ROOT / "logs"),
    configs_dir=str(PROJECT_ROOT / "configs" / "experiments"),
    reports_dir=str(PROJECT_ROOT / "reports"),
)

_cache: dict[str, ExperimentData] = {}


def _get_experiment(name: str) -> ExperimentData:
    if name not in _cache:
        log_path = index.get_log_path(name)
        if not log_path.exists():
            raise HTTPException(404, f"No log file for experiment: {name}")
        data = ExperimentData(log_path)
        data.load()
        _cache[name] = data
    return _cache[name]


@app.get("/")
async def root():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/experiments")
async def list_experiments():
    return index.list_experiments()


@app.get("/api/experiment/{name}/config")
async def get_config(name: str):
    config = index.get_config(name)
    if not config:
        data = _get_experiment(name)
        config = data.config
    return config


@app.get("/api/experiment/{name}/ticks")
async def get_ticks(name: str):
    data = _get_experiment(name)
    return data.get_all_ticks_summary()


@app.get("/api/experiment/{name}/tick/{n}")
async def get_tick(name: str, n: int):
    data = _get_experiment(name)
    tick = data.get_tick(n)
    if not tick:
        raise HTTPException(404, f"Tick {n} not found")
    return tick


@app.get("/api/experiment/{name}/metrics")
async def get_metrics(name: str):
    data = _get_experiment(name)
    return data.get_metrics()


@app.get("/api/experiment/{name}/events")
async def get_events(name: str):
    data = _get_experiment(name)
    return data.get_events()


@app.get("/api/experiment/{name}/network/{tick}")
async def get_network(name: str, tick: int):
    data = _get_experiment(name)
    return data.get_network(tick)


@app.get("/api/experiment/{name}/conversations/{tick}")
async def get_conversations(name: str, tick: int):
    data = _get_experiment(name)
    return data.get_conversations(tick)


@app.get("/api/experiment/{name}/beliefs")
async def get_beliefs(name: str):
    data = _get_experiment(name)
    return data.get_beliefs_timeseries()


@app.get("/api/experiment/{name}/reports")
async def list_reports(name: str):
    report_dir = index.get_report_dir(name)
    if not report_dir.exists():
        return []
    return [f.name for f in report_dir.iterdir() if f.is_file()]


@app.get("/api/experiment/{name}/reports/{filename}")
async def get_report_file(name: str, filename: str):
    report_dir = index.get_report_dir(name)
    file_path = report_dir / filename
    if not file_path.exists():
        raise HTTPException(404, f"Report file not found: {filename}")
    return FileResponse(file_path)


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
