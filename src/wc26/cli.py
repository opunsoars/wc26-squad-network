"""CLI entry-point for the WC26 squad freshness & familiarity pipeline."""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pandas as pd
import structlog
import typer

from wc26.config import RAW_CACHE_DIR, TOURNAMENT_DATE
from wc26.pipeline.matchlogs import fetch_player_matchlogs
from wc26.pipeline.metrics import build_squad_graph, compute_freshness, compute_squad_metrics
from wc26.pipeline.squads import build_players_dataset
from wc26.scraper import Scraper
from wc26.store import Store

app = typer.Typer(help="WC26 squad freshness & familiarity pipeline")
logger = structlog.get_logger()

_DEFAULT_DB = "data/wc26.duckdb"


@app.command()
def squads(
    cache_dir: str = typer.Option(RAW_CACHE_DIR, help="Raw HTML cache dir"),
    db: str = typer.Option(_DEFAULT_DB, help="DuckDB file path"),
) -> None:
    """Scrape squad lists, resolve Transfermarkt IDs, and save to DuckDB."""
    scraper = Scraper(cache_dir=cache_dir)
    players = build_players_dataset(scraper)
    store = Store(db)
    store.upsert_players(players)
    store.close()
    typer.echo(f"Saved {len(players)} players to {db}")


@app.command()
def matchlogs(
    cache_dir: str = typer.Option(RAW_CACHE_DIR, help="Raw HTML cache dir"),
    db: str = typer.Option(_DEFAULT_DB, help="DuckDB file path"),
    headless: bool = typer.Option(True, help="Run Chromium headless"),
    resume: bool = typer.Option(False, "--resume", help="Skip players already in DB"),
) -> None:
    """Render TM performance pages and append match logs to DuckDB.

    Use --resume to continue an interrupted run without re-scraping
    players whose logs are already stored.
    """
    store = Store(db)
    all_players = store.all_players()

    if resume:
        done = store.processed_tm_ids()
        players = [p for p in all_players if p.tm_id not in done]
        typer.echo(f"Resuming: {len(done)} already done, {len(players)} remaining")
    else:
        players = all_players

    total_new = 0
    for i, player in enumerate(players, 1):
        logs = fetch_player_matchlogs(player, cache_dir=cache_dir, headless=headless)
        if logs:
            store.append_match_logs(logs)
            total_new += len(logs)
        typer.echo(f"[{i}/{len(players)}] {player.name} ({player.squad}): {len(logs)} rows")

    store.close()
    typer.echo(f"Done. {total_new} new match-log rows written to {db}")


@app.command()
def metrics(
    db: str = typer.Option(_DEFAULT_DB, help="DuckDB file path"),
    out_dir: str = typer.Option("site/data", help="JSON output directory"),
) -> None:
    """Compute freshness + network metrics and write site JSON."""
    store = Store(db)
    all_players = store.all_players()
    all_logs = store.all_match_logs()
    store.close()

    players_by_squad: dict[str, list[Any]] = {}
    for p in all_players:
        players_by_squad.setdefault(p.squad, []).append(p)

    logs_by_player: dict[str, list[Any]] = {}
    for log in all_logs:
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


@app.command()
def export(
    db: str = typer.Option(_DEFAULT_DB, help="DuckDB file path"),
    out_dir: str = typer.Option("data", help="Output directory for parquet/CSV files"),
) -> None:
    """Export DuckDB contents to parquet + CSV for committing to the repo."""
    store = Store(db)
    players = store.all_players()
    logs = store.all_match_logs()
    store.close()

    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    df_players = pd.DataFrame([p.model_dump() for p in players])
    df_players.to_parquet(out / "players.parquet", index=False)
    df_players.to_csv(out / "players.csv", index=False)

    df_logs = pd.DataFrame([m.model_dump() for m in logs])
    df_logs.to_parquet(out / "player_matches.parquet", index=False)
    df_logs.to_csv(out / "player_matches.csv", index=False)

    typer.echo(f"Exported {len(players)} players and {len(logs)} match logs to {out_dir}/")


@app.command(name="all")
def run_all(
    cache_dir: str = typer.Option(RAW_CACHE_DIR),
    db: str = typer.Option(_DEFAULT_DB),
    resume: bool = typer.Option(False, "--resume"),
) -> None:
    """Run all pipeline stages in order (squads → matchlogs → metrics → export)."""
    typer.echo("Running: squads")
    squads(cache_dir=cache_dir, db=db)
    typer.echo("Running: matchlogs")
    matchlogs(cache_dir=cache_dir, db=db, headless=True, resume=resume)
    typer.echo("Running: metrics")
    metrics(db=db, out_dir="site/data")
    typer.echo("Running: export")
    export(db=db, out_dir="data")
