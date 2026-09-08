"""The operator kill switch's transport: a sentinel file, its payload, and its accessors.

The node is a long-running process holding positions; the operator is at a terminal in a
different process. Three transports cross that boundary and two are rejected in D8: an OS
signal carries no payload and NautilusTrader already claims SIGTERM/SIGINT/SIGABRT
(system/kernel.py:566-572), and a Redis-backed external bus is a new hard dependency whose
availability correlates with the incident it exists to end. A local file needs nothing to be
running and nothing to be reachable.

The property that makes a file the right answer is durability, not simplicity. A signal is an
event: if nobody was listening at that instant it never happened. A trip file is state, so a
node that is down when the operator trips it halts the moment it starts, before it can touch
the market.

This module lives in `models/` and NOT in `actors/` on purpose: the CLI imports it to write the
file, and an `actors/` module would drag in `Actor` and therefore nautilus_trader. Keeping it
engine-free is also what lets it be developed and tested on a machine where nautilus_trader
cannot be installed at all (see docs/testing.md). `test_halt_file.py` enforces that by parsing
this file, so the constraint is checked rather than remembered.

HARD REQUIREMENT, stated here and enforced by `zerodte preflight` (ops epic), not by this
module: the trip file must live on a LOCAL filesystem. The poll that reads it is a `stat` inside
an engine callback, and a `stat` against a hung network mount does not fail - it blocks
uninterruptibly, taking the whole event loop with it. The kill switch would become the thing
that wedges the node.

This module holds NO behaviour. Nothing reads the file until H6 and nothing latches until H5.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

HALT_FILE_SCHEMA = 1

TRIP_FILE_SUFFIX = ".trip"
TRIP_DIR_NAME = "halt"

REASON_UNREADABLE = "trip_file_unreadable"
REASON_UNPARSEABLE = "unparseable_trip_file"


class TripRecord(BaseModel):
    """The payload of a trip file.

    `requested_at_utc` is optional and this module never fills it in. A record synthesised from
    a file we could not read does not know when the halt was requested, and inventing a
    timestamp would put a fabricated fact into the evidence chain. It is also how this module
    stays clear of T3: nothing here reads a wall clock, so there is no clock to be the wrong
    one. The CLI supplies the timestamp when it writes a real record (H7).

    A record whose `schema_version` is from the future is deliberately NOT special-cased. It
    parses, and it trips. Refusing to act on a trip file because its version is unfamiliar would
    be the one failure this design cannot tolerate.
    """

    model_config = ConfigDict(frozen=True)

    schema_version: int = HALT_FILE_SCHEMA
    token: str
    reason: str
    trader_id: str
    requested_by: str | None = None
    requested_at_utc: datetime | None = None


def trip_path(runs_dir: Path, trader_id: str) -> Path:
    """`<runs_dir>/halt/<trader_id>.trip`.

    The trader id goes in the FILENAME and not in the body, which buys two things. The hot poll
    becomes one `exists()` on a fixed path with nothing to open, parse or compare. And two nodes
    on one box structurally cannot cross-kill each other, because each only ever looks at its
    own path - a property no amount of care inside the file body would give.
    """
    return runs_dir / TRIP_DIR_NAME / f"{trader_id}{TRIP_FILE_SUFFIX}"


def write_trip(path: Path, record: TripRecord) -> None:
    """Write the trip file so that a poller can never observe a partial one.

    Write to a temporary file IN THE SAME DIRECTORY, then `os.replace`, which is an atomic
    rename. Same directory is not tidiness: `os.replace` is only atomic within one filesystem,
    and a temp file under the system temp directory can land on a different one, at which point
    the rename either raises `OSError(EXDEV)` or degrades to a copy that a poller can catch
    half-written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f"{path.name}.tmp"
    tmp.write_text(record.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def read_trip(path: Path) -> TripRecord | None:
    """Return the trip record, or None if and ONLY if the file is absent.

    T5, fail closed. A file that is present but unreadable or present but unparseable returns a
    synthesised record naming which, so the caller trips. A control file we cannot read is not a
    reason to keep trading, and returning None on a parse failure would turn the one file that
    exists to stop the system into a file that silently does not.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError:
        return _synthesised(REASON_UNREADABLE, path)
    try:
        return TripRecord.model_validate_json(raw)
    except ValueError:
        return _synthesised(REASON_UNPARSEABLE, path)


def clear_trip(path: Path) -> bool:
    """Remove the trip file. True if a file was removed, False if there was none.

    Clearing the file does NOT un-halt a running node: the strategy latch has no setter (H5), so
    resuming needs this plus a restart. That asymmetry is the design, not an oversight.
    """
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True


def _synthesised(reason: str, path: Path) -> TripRecord:
    """A record for a file we could not use, carrying only what the path itself tells us.

    The token is fresh because there is no readable one to recover. That is harmless: the actor
    reads the file exactly once and latches (killswitch_plan.md, H1/H2 of the trip sequence), so
    no second token is ever generated for the same trip.
    """
    return TripRecord(
        token=uuid4().hex,
        reason=reason,
        trader_id=path.stem,
    )
