"""Schéma SQLite (SQLAlchemy Core).

Isolation des carrières : toutes les tables de données de jeu portent `career_id`.
Historique : `players_current` est remplacée à chaque synchronisation, mais les changements
(club, salaire, valeur, contrat) sont archivés dans `player_history` ; matchs, stats de saison
et finances sont fusionnés (upsert) pour conserver ce que FM26 finit par oublier.
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Table as T

metadata = MetaData()

schema_version = T("schema_version", metadata, Column("version", Integer, primary_key=True))

careers = T(
    "careers",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("fingerprint", String(64), nullable=False, unique=True),
    Column("label", String(200), nullable=False),
    Column("save_stem", String(200)),
    Column("manager_name", String(200)),
    Column("manager_staff_uid", Integer),
    Column("club_uid", Integer),
    Column("club_name", String(200)),
    Column("db_version", String(50)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("last_sync_at", DateTime(timezone=True)),
    Column("last_game_date", Date),
    Column("current_season_start_year", Integer),
    Column("season_source", String(40)),
)

snapshots = T(
    "snapshots",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("career_id", ForeignKey("careers.id", ondelete="CASCADE"), nullable=False),
    Column("source_path", Text, nullable=False),
    Column("copy_path", Text),
    Column("sha256", String(64), nullable=False),
    Column("size", Integer),
    Column("copied_at", DateTime(timezone=True), nullable=False),
    Column("game_date", Date),
    Column("build", String(50)),
    Column("reader", String(50)),
    Column("status", String(20), nullable=False),
    Column("warnings", JSON),
    Column("field_status", JSON),
    Column("counts", JSON),
    Column("duration_ms", Integer),
    UniqueConstraint("career_id", "sha256", name="uq_snapshot_hash"),
)

clubs_current = T(
    "clubs_current",
    metadata,
    Column("career_id", ForeignKey("careers.id", ondelete="CASCADE"), primary_key=True),
    Column("uid", Integer, primary_key=True),
    Column("snapshot_id", Integer, nullable=False),
    Column("name", String(200)),
    Column("short_name", String(100)),
    Column("nation_id", Integer),
    Column("reputation", Integer),
    Column("last_league_position", Integer),
)

players_current = T(
    "players_current",
    metadata,
    Column("career_id", ForeignKey("careers.id", ondelete="CASCADE"), primary_key=True),
    Column("uid", Integer, primary_key=True),
    Column("snapshot_id", Integer, nullable=False),
    Column("unique_id", Integer),
    Column("name", String(200), nullable=False),
    Column("name_search", String(200), nullable=False),
    Column("birth_date", Date),
    Column("age", Integer),
    Column("nation_id", Integer),
    Column("height_cm", Integer),
    Column("club_uid", Integer),
    Column("club_name", String(200)),
    Column("team_slot", Integer),  # 0 = équipe première ; NULL = inconnu
    Column("positions", String(100)),  # ",DC,DL," pour LIKE
    Column("accomplished_positions", String(100)),
    Column("position_ratings", JSON),
    Column("left_foot", Integer),
    Column("right_foot", Integer),
    Column("current_ability", Integer),
    Column("potential_ability", Integer),
    Column("transfer_value", Integer),
    Column("transfer_value_state", String(30)),
    Column("wage", Integer),
    Column("contract_start", Date),
    Column("contract_end", Date),
    Column("squad_status", String(50)),
    Column("on_loan", Boolean),
    Column("loan_parent_club_uid", Integer),
    Column("condition", Integer),
    Column("attributes", JSON),
    Column("personality", JSON),
    Column("traits", JSON),
    Column("banned", Boolean),
)
Index("ix_players_club", players_current.c.career_id, players_current.c.club_uid)
Index("ix_players_age", players_current.c.career_id, players_current.c.age)
Index("ix_players_value", players_current.c.career_id, players_current.c.transfer_value)
Index("ix_players_name", players_current.c.career_id, players_current.c.name_search)

player_history = T(
    "player_history",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("career_id", ForeignKey("careers.id", ondelete="CASCADE"), nullable=False),
    Column("uid", Integer, nullable=False),
    Column("snapshot_id", Integer, nullable=False),
    Column("game_date", Date),
    Column("name", String(200)),
    Column("club_uid", Integer),
    Column("club_name", String(200)),
    Column("wage", Integer),
    Column("transfer_value", Integer),
    Column("contract_end", Date),
    Column("change", String(200)),
)
Index("ix_history_player", player_history.c.career_id, player_history.c.uid)

fixtures = T(
    "fixtures",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("career_id", ForeignKey("careers.id", ondelete="CASCADE"), nullable=False),
    Column("match_key", String(120), nullable=False),
    Column("stage_id", Integer),
    Column("competition_id", Integer),
    Column("competition_name", String(200)),
    Column("round_label", String(60)),
    Column("date", Date, nullable=False),
    Column("season_start_year", Integer),
    Column("home_club_uid", Integer),
    Column("home_club_name", String(200)),
    Column("home_team_slot", Integer),
    Column("away_club_uid", Integer),
    Column("away_club_name", String(200)),
    Column("away_team_slot", Integer),
    Column("home_goals", Integer),
    Column("away_goals", Integer),
    Column("played", Boolean),
    Column("first_seen_snapshot", Integer),
    Column("last_seen_snapshot", Integer),
    Column("score_snapshot", Integer),
    UniqueConstraint("career_id", "match_key", name="uq_fixture"),
)
Index("ix_fixture_date", fixtures.c.career_id, fixtures.c.date)

season_stats = T(
    "season_stats",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("career_id", ForeignKey("careers.id", ondelete="CASCADE"), nullable=False),
    Column("season_start_year", Integer),
    Column("season_source", String(40)),
    Column("player_uid", Integer, nullable=False),
    Column("player_name", String(200)),
    Column("kind", String(40), nullable=False),
    Column("club_uid", Integer),
    Column("club_name", String(200)),
    Column("team_slot", Integer),
    Column("starts", Integer),
    Column("substitute_appearances", Integer),
    Column("minutes", Integer),
    Column("goals", Integer),
    Column("assists", Integer),
    Column("average_rating", Float),
    Column("expected_goals", Float),
    Column("player_of_the_match", Integer),
    Column("yellow_cards", Integer),
    Column("red_cards", Integer),
    Column("extra", JSON),
    Column("snapshot_id", Integer),
    Column("game_date", Date),
    UniqueConstraint(
        "career_id", "season_start_year", "player_uid", "kind", "club_uid", "team_slot",
        name="uq_season_stat",
    ),
)
Index("ix_stats_player", season_stats.c.career_id, season_stats.c.player_uid)

finances = T(
    "finances",
    metadata,
    Column("career_id", ForeignKey("careers.id", ondelete="CASCADE"), primary_key=True),
    Column("club_uid", Integer, primary_key=True),
    Column("month", Date, primary_key=True),
    Column("balance", Integer),
    Column("transfer_budget_allocated", Integer),
    Column("transfer_budget_remaining", Integer),
    Column("wage_budget_weekly", Integer),
    Column("wage_payroll_weekly", Integer),
    Column("total_income", Integer),
    Column("total_expenditure", Integer),
    Column("net", Integer),
    Column("snapshot_id", Integer),
)

league_tables = T(
    "league_tables",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("career_id", ForeignKey("careers.id", ondelete="CASCADE"), nullable=False),
    Column("snapshot_id", Integer, nullable=False),
    Column("game_date", Date),
    Column("competition_id", Integer),
    Column("competition_name", String(200)),
    Column("position", Integer),
    Column("club_uid", Integer),
    Column("club_name", String(200)),
    Column("team_slot", Integer),
    Column("played", Integer),
    Column("won", Integer),
    Column("drawn", Integer),
    Column("lost", Integer),
    Column("goals_for", Integer),
    Column("goals_against", Integer),
    Column("points", Integer),
)
Index("ix_tables_snap", league_tables.c.career_id, league_tables.c.snapshot_id)

tactics = T(
    "tactics",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("career_id", ForeignKey("careers.id", ondelete="CASCADE"), nullable=False),
    Column("snapshot_id", Integer, nullable=False),
    Column("club_uid", Integer),
    Column("team_slot", Integer),
    Column("idx", Integer),
    Column("name", String(200)),
    Column("style_name", String(200)),
    Column("mentality", String(60)),
    Column("slots", JSON),
)

injuries = T(
    "injuries",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("career_id", ForeignKey("careers.id", ondelete="CASCADE"), nullable=False),
    Column("injury_key", String(120), nullable=False),
    Column("kind", String(40)),
    Column("player_uid", Integer),
    Column("player_name", String(200)),
    Column("date", Date),
    Column("club_uid", Integer),
    Column("type_name", String(200)),
    Column("snapshot_id", Integer),
    UniqueConstraint("career_id", "injury_key", name="uq_injury"),
)

# --- Mémoire, conversations, préférences --------------------------------------------------

conversations = T(
    "conversations",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("career_id", ForeignKey("careers.id", ondelete="CASCADE"), nullable=False),
    Column("title", String(200)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("summary", Text),
)

messages = T(
    "messages",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("conversation_id", ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
    Column("role", String(20), nullable=False),
    Column("content", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("game_date", Date),
    Column("route", String(40)),
    Column("tool_trace", JSON),
)

memories = T(
    "memories",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("career_id", ForeignKey("careers.id", ondelete="CASCADE"), nullable=False),
    # preference | objectif | joueur_refuse | cible | promesse | decision | a_vendre | strategie
    Column("kind", String(30), nullable=False),
    Column("key", String(100)),
    Column("value", JSON, nullable=False),
    Column("text", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("game_date", Date),
    Column("active", Boolean, nullable=False, default=True),
)

# --- Journal d'audit (outils, IA, actions) -----------------------------------------------

tool_audit = T(
    "tool_audit",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("career_id", Integer),
    Column("tool", String(80), nullable=False),
    Column("category", String(20), nullable=False),
    Column("args", JSON),
    Column("ok", Boolean, nullable=False),
    Column("error", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("duration_ms", Integer),
)

ai_usage = T(
    "ai_usage",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("provider", String(100), nullable=False),
    Column("model", String(100)),
    Column("tier", Integer),
    Column("input_tokens", Integer),
    Column("output_tokens", Integer),
    Column("cost_usd", Float),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

operations = T(
    "operations",
    metadata,
    Column("id", String(40), primary_key=True),  # identifiant unique anti double-envoi
    Column("career_id", Integer, nullable=False),
    Column("action", String(60), nullable=False),
    Column("payload", JSON, nullable=False),
    # prepared | awaiting_approval | approved | executing | executed | confirmed | failed | cancelled | refused
    Column("status", String(30), nullable=False),
    Column("detail", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

alerts = T(
    "alerts",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("career_id", ForeignKey("careers.id", ondelete="CASCADE"), nullable=False),
    Column("rule", String(60), nullable=False),
    Column("subject_key", String(120), nullable=False),
    Column("severity", String(20), nullable=False),
    Column("message", Text, nullable=False),
    Column("data", JSON),
    Column("game_date", Date),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("dismissed", Boolean, nullable=False, default=False),
    UniqueConstraint("career_id", "rule", "subject_key", name="uq_alert"),
)
