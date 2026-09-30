"""Additive tables alongside existing memory; no external service required."""

import sqlite3
from contextlib import contextmanager

from shared.memory.insights import memory_db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_episodes(
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, domain TEXT NOT NULL,
 role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS agent_episodes_owner ON agent_episodes(user_id,created_at);
CREATE VIRTUAL TABLE IF NOT EXISTS agent_episodes_fts USING fts5(content,content='agent_episodes',content_rowid='id');
CREATE TRIGGER IF NOT EXISTS agent_episodes_ai AFTER INSERT ON agent_episodes BEGIN
 INSERT INTO agent_episodes_fts(rowid,content) VALUES(new.id,new.content); END;
CREATE TRIGGER IF NOT EXISTS agent_episodes_ad AFTER DELETE ON agent_episodes BEGIN
 INSERT INTO agent_episodes_fts(agent_episodes_fts,rowid,content) VALUES('delete',old.id,old.content); END;
CREATE TABLE IF NOT EXISTS agent_projects(
 id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,name TEXT NOT NULL,summary TEXT NOT NULL,
 links TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(user_id,name));
CREATE TABLE IF NOT EXISTS agent_project_focus(user_id INTEGER PRIMARY KEY,project_id TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agent_records(
 id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,kind TEXT NOT NULL,project_id TEXT NOT NULL,
 body TEXT NOT NULL,source TEXT NOT NULL,certainty TEXT NOT NULL,status TEXT NOT NULL,
 valid_from TEXT NOT NULL,valid_until TEXT NOT NULL,supersedes TEXT NOT NULL,
 created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS agent_records_owner ON agent_records(user_id,project_id,status);
CREATE TABLE IF NOT EXISTS agent_operations(
 id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,request_key TEXT NOT NULL,tool TEXT NOT NULL,
 args_hash TEXT NOT NULL,status TEXT NOT NULL,result TEXT NOT NULL,created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,UNIQUE(user_id,request_key,tool,args_hash));
CREATE TABLE IF NOT EXISTS agent_followups(
 id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,domain TEXT NOT NULL,project_id TEXT NOT NULL,
 objective TEXT NOT NULL,tool TEXT NOT NULL,args TEXT NOT NULL,condition TEXT NOT NULL,
 expected TEXT NOT NULL,baseline TEXT NOT NULL,status TEXT NOT NULL,next_check TEXT NOT NULL,
 expires_at TEXT NOT NULL,lease_until TEXT NOT NULL,failures INTEGER NOT NULL DEFAULT 0,
 result TEXT NOT NULL,notify_state TEXT NOT NULL,updated_at TEXT NOT NULL,
 UNIQUE(user_id,objective,tool,args));
"""


@contextmanager
def connection():
    p = memory_db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(p), timeout=30)
    db.row_factory = sqlite3.Row
    try:
        db.executescript(SCHEMA)
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()
