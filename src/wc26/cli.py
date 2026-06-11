"""CLI entry-point for the WC26 squad freshness & familiarity pipeline."""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pandas as pd
import structlog
import typer

from wc26.config import RAW_CACHE_DIR, TOURNAMENT_DATE
from wc26.models import MatchLog, Player
from wc26.pipeline.matchlogs import fetch_player_matchlogs
from wc26.pipeline.metrics import build_squad_graph, compute_freshness, compute_squad_metrics
from wc26.pipeline.squads import build_players_dataset
from wc26.scraper import Scraper

app = typer.Typer(help="WC26 squad freshness & familiarity pipeline")
logger = structlog.get_logger()


@app.command()
def squads(
    cache_dir: str = typer.Option(RAW_CACHE_DIR, help="Raw HTML cache dir"),
    out: str = typer.Option("data/players.parquet", help="Output parquet path"),
) -> None:
    """Scrape squad lists and resolve Transfermarkt IDs."""
    scraper = Scraper(cache_dir=cache_dir)
    players = build_players_dataset(scraper)
    df = pd.DataFrame([p.model_dump() for p in players])
    pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    df.to_csv(out.replace(".parquet", ".csv"), index=False)
    typer.echo(f"Saved {len(players)} players to {out}")


@app.command()
def matchlogs(
    players_file: str = typer.Option("data/players.parquet", help="Players parquet"),
    cache_dir: str = typer.Option(RAW_CACHE_DIR, help="Raw HTML cache dir"),
    out: str = typer.Option("data/player_matches.parquet", help="Output parquet path"),
    headless: bool = typer.Option(True, help="Run browser headless"),
) -> None:
    """Render TM performance pages with Playwright and parse match logs."""
    df_players = pd.read_parquet(players_file)
    all_players = [Player(**row) for row in df_players.to_dict(orient="records")]  # type: ignore[arg-type]

    all_logs: list[MatchLog] = []
    for player in all_players:
        logs = fetch_player_matchlogs(player, cache_dir=cache_dir, headless=headless)
        all_logs.extend(logs)

    df = pd.DataFrame([m.model_dump() for m in all_logs])
    pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    df.to_csv(out.replace(".parquet", ".csv"), index=False)
    typer.echo(f"Saved {len(all_logs)} match logs to {out}")


@app.command()
def metrics(
    players_file: str = typer.Option("data/players.parquet"),
    matchlogs_file: str = typer.Option("data/player_matches.parquet"),
    out_dir: str = typer.Option("site/data", help="JSON output directory"),
) -> None:
    """Compute freshness + network metrics and write site JSON."""
    df_players = pd.read_parquet(players_file)
    df_logs = pd.read_parquet(matchlogs_file)
    df_logs["date"] = pd.to_datetime(df_logs["date"]).dt.date

    players_by_squad: dict[str, list[Player]] = {}
    for _, row in df_players.iterrows():
        p = Player(**row.to_dict())  # type: ignore[arg-type]
        players_by_squad.setdefault(p.squad, []).append(p)

    logs_all = [MatchLog(**row) for row in df_logs.to_dict(orient="records")]  # type: ignore[arg-type]
    logs_by_player: dict[str, list[MatchLog]] = {}
    for log in logs_all:
        logs_by_player.setdefault(log.player_tm_id, []).append(log)

    out_path = pathlib.Path(out_dir)
    (out_path / "teams").mkdir(parents=True, exist_ok=True)

    summary_squads: list[dict[str, Any]] = []

    for squad, players in players_by_squad.items():
        squad_logs = [log for p in players for log in logs_by_player.get(p.tm_id, [])]
        sq_metrics = compute_squad_metrics(squad, players, squad_logs)
        G = build_squad_graph(players, squad_logs)

        player_freshness: list[dict[str, Any]] = [
            {
                "tm_id": p.tm_id,
                "name": p.name,
                "position": p.position,
                "club": p.club,
                "freshness_minutes": compute_freshness(
                    logs_by_player.get(p.tm_id, []),
                    player_tm_id=p.tm_id,
                    as_of=TOURNAMENT_DATE,
                ),
            }
            for p in players
        ]

        edges: list[dict[str, Any]] = [
            {
                "source": u,
                "target": v,
                "raw_shared_minutes": d["raw_shared_minutes"],
                "weighted_shared_minutes": d["weighted_shared_minutes"],
            }
            for u, v, d in G.edges(data=True)
        ]

        team_code = squad.lower().replace(" ", "_")
        team_json: dict[str, Any] = {
            "squad": squad,
            "metrics": sq_metrics.model_dump(),
            "players": player_freshness,
            "edges": edges,
        }
        (out_path / "teams" / f"{team_code}.json").write_text(
            json.dumps(team_json, default=str), encoding="utf-8"
        )

        summary_squads.append(
            {
                "squad": squad,
                "team_code": team_code,
                "density": sq_metrics.density,
                "clustering": sq_metrics.clustering,
                "avg_freshness_minutes": (
                    sum(p["freshness_minutes"] for p in player_freshness) / len(players)
                    if players
                    else 0
                ),
                "market_value_eur": sq_metrics.market_value_eur,
            }
        )

    summary_json: dict[str, Any] = {
        "as_of": TOURNAMENT_DATE.isoformat(),
        "squads": summary_squads,
    }
    (out_path / "summary.json").write_text(json.dumps(summary_json, default=str), encoding="utf-8")
    typer.echo(f"JSON written to {out_dir}: {len(summary_squads)} squads")


@app.command(name="all")
def run_all(
    cache_dir: str = typer.Option(RAW_CACHE_DIR),
) -> None:
    """Run all pipeline stages in order."""
    typer.echo("Running: squads")
    squads(cache_dir=cache_dir, out="data/players.parquet")
    typer.echo("Running: matchlogs")
    matchlogs(
        players_file="data/players.parquet",
        cache_dir=cache_dir,
        out="data/player_matches.parquet",
        headless=True,
    )
    typer.echo("Running: metrics")
    metrics(
        players_file="data/players.parquet",
        matchlogs_file="data/player_matches.parquet",
        out_dir="site/data",
    )
