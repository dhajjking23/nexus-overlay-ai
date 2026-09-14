"""
NEXUS OVERLAY AI - Database Migration Runner
Applies migrations sequentially from the migrations directory.
"""
from __future__ import annotations
import importlib
import logging
import os
import re
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)


class MigrationRunner:
    """
    Applies database migrations sequentially.
    
    Migration files must:
    - Be in the migrations/ directory
    - Be named NNN_description.py (e.g., 001_initial.py)
    - Have an `async def up(db)` function
    - Optionally have an `async def down(db)` function
    """
    
    MIGRATIONS_DIR = Path(__file__).parent
    
    @staticmethod
    async def get_applied_versions(db: aiosqlite.Connection) -> set[int]:
        """Get set of already-applied migration versions."""
        try:
            async with db.execute(
                "SELECT version FROM schema_version ORDER BY version"
            ) as cursor:
                rows = await cursor.fetchall()
                return {row[0] for row in rows}
        except Exception:
            return set()
    
    @staticmethod
    def discover_migrations() -> list[tuple[int, str, str]]:
        """
        Discover migration files in the migrations directory.
        Returns list of (version, name, module_path) tuples, sorted by version.
        """
        migrations_dir = MigrationRunner.MIGRATIONS_DIR
        pattern = re.compile(r'^(\d{3})_(.+)\.py$')
        migrations = []
        
        if not migrations_dir.exists():
            return migrations
        
        for f in sorted(migrations_dir.iterdir()):
            if f.is_file():
                match = pattern.match(f.name)
                if match:
                    version = int(match.group(1))
                    name = match.group(2)
                    module_name = f.stem
                    migrations.append((version, name, module_name))
        
        return sorted(migrations, key=lambda m: m[0])
    
    @staticmethod
    async def apply_pending(db: aiosqlite.Connection) -> list[int]:
        """
        Apply all pending migrations.
        Returns list of applied version numbers.
        """
        applied = await MigrationRunner.get_applied_versions(db)
        available = MigrationRunner.discover_migrations()
        
        applied_versions = []
        
        for version, name, module_name in available:
            if version not in applied:
                logger.info(f"Applying migration {version:03d}_{name}")
                try:
                    # Import the migration module
                    module = importlib.import_module(
                        f"backend.database.migrations.{module_name}"
                    )
                    
                    # Call up()
                    if hasattr(module, 'up'):
                        await module.up(db)
                    
                    # Record the migration
                    await db.execute(
                        """INSERT OR REPLACE INTO schema_version (version, description)
                           VALUES (?, ?)""",
                        (version, f"{name} migration"),
                    )
                    await db.commit()
                    
                    applied_versions.append(version)
                    logger.info(f"Migration {version:03d}_{name} applied successfully")
                    
                except Exception as e:
                    logger.error(f"Migration {version:03d}_{name} failed: {e}")
                    raise
        
        if not applied_versions:
            logger.info("No pending migrations")
        
        return applied_versions
    
    @staticmethod
    async def rollback_last(db: aiosqlite.Connection) -> int | None:
        """
        Rollback the last applied migration.
        Returns the version number that was rolled back, or None.
        """
        applied = await MigrationRunner.get_applied_versions(db)
        available = MigrationRunner.discover_migrations()
        
        if not available:
            return None
        
        # Find highest version
        max_version = max(v for v, _, _ in available)
        if max_version not in applied:
            return None
        
        # Find and execute rollback
        for version, name, module_name in available:
            if version == max_version:
                logger.info(f"Rolling back migration {version:03d}_{name}")
                try:
                    module = importlib.import_module(
                        f"backend.database.migrations.{module_name}"
                    )
                    
                    if hasattr(module, 'down'):
                        await module.down(db)
                    
                    # Remove version record
                    await db.execute(
                        "DELETE FROM schema_version WHERE version = ?", (version,)
                    )
                    await db.commit()
                    
                    logger.info(f"Migration {version:03d}_{name} rolled back")
                    return version
                    
                except Exception as e:
                    logger.error(f"Rollback of {version:03d}_{name} failed: {e}")
                    raise
        
        return None
    
    @staticmethod
    async def get_status(db: aiosqlite.Connection) -> dict:
        """Get migration status."""
        applied = await MigrationRunner.get_applied_versions(db)
        available = MigrationRunner.discover_migrations()
        
        return {
            "total_migrations": len(available),
            "applied_count": len(applied),
            "pending_count": len(available) - len(applied),
            "applied": sorted(applied),
            "pending": [v for v, _, _ in available if v not in applied],
        }