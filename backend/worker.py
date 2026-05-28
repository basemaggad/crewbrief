"""
CrewBrief ingestion worker.

Polls the `ingestion_jobs` table for pending work and runs the full
PDF ingestion pipeline (extract -> chunk -> embed -> insert chunks ->
mark document ready).

Run as a separate process — locally or as a dedicated Railway service:

  python worker.py

Environment variables required (same set as the API):
  SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_ANON_KEY,
  SUPABASE_JWT_SECRET, ANTHROPIC_API_KEY, STORAGE_BUCKET (optional).

Reliability properties:
  * Atomic claim via claim_ingestion_job() RPC (FOR UPDATE SKIP LOCKED),
    safe for multiple parallel workers.
  * Heartbeat: while a job runs, a background thread updates
    last_heartbeat_at every HEARTBEAT_INTERVAL seconds. The claim RPC
    only reclaims a 'processing' job whose heartbeat has gone stale, so a
    long-but-healthy job (e.g. a large PDF) is never re-queued mid-flight.
  * Idempotent retries: process_from_storage() clears existing chunks for
    the document before inserting, so a retried job never duplicates rows.
  * Terminal failure: after max_attempts the job is set to 'error'; a
    Postgres trigger then propagates 'error' to the parent document.
  * Graceful shutdown: SIGTERM/SIGINT finish the current job, and the idle
    poll wait is interruptible so shutdown is near-instant when idle.
"""
import os
import sys
import signal
import logging
import threading
from datetime import datetime, timezone

# Allow imports from the app package.
sys.path.insert(0, os.path.dirname(__file__))

from app.core.config import settings
from app.db.supabase_client import get_supabase_admin
from app.services.document_service import process_from_storage

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)-7s]  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("crewbrief.worker")

# ── Config ─────────────────────────────────────────────────────────────────
POLL_INTERVAL_SECONDS = 5    # idle wait between polls when the queue is empty
HEARTBEAT_INTERVAL    = 30   # how often the active job stamps last_heartbeat_at
LOG_HEARTBEAT_EVERY   = 60   # log an "alive" line this often while idle

# ── Graceful shutdown ──────────────────────────────────────────────────────
# A single Event drives both the idle-poll wait (so we can wake instantly on
# a signal) and the shutdown flag.
_wake = threading.Event()
_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    log.info("Shutdown signal received — will stop after the current job.")
    _shutdown = True
    _wake.set()  # interrupt any idle wait immediately


# ── Heartbeat ──────────────────────────────────────────────────────────────

def _start_heartbeat(job_id: str) -> tuple[threading.Thread, threading.Event]:
    """
    Spawn a daemon thread that stamps last_heartbeat_at every
    HEARTBEAT_INTERVAL seconds until its stop Event is set.
    """
    stop = threading.Event()

    def beat():
        supabase = get_supabase_admin()
        # stop.wait returns True when set (stop), False on timeout (beat again)
        while not stop.wait(HEARTBEAT_INTERVAL):
            try:
                supabase.table("ingestion_jobs").update({
                    "last_heartbeat_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", job_id).execute()
            except Exception as e:
                log.warning(f"  heartbeat update failed for {job_id[:8]}…: {e}")

    t = threading.Thread(target=beat, name=f"hb-{job_id[:8]}", daemon=True)
    t.start()
    return t, stop


# ── Queue helpers ──────────────────────────────────────────────────────────

def claim_job() -> dict | None:
    """Atomically claim one pending job. Returns the row dict or None."""
    supabase = get_supabase_admin()
    res = supabase.rpc("claim_ingestion_job", {}).execute()
    if res.data:
        return res.data[0]
    return None


def complete_job(job_id: str) -> None:
    supabase = get_supabase_admin()
    supabase.table("ingestion_jobs").update({
        "status":       "done",
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", job_id).execute()


def fail_job(job_id: str, error_message: str, attempts: int, max_attempts: int) -> None:
    """
    Mark the job failed. Retries remaining -> back to 'pending'; exhausted ->
    terminal 'error'. The 'error' state propagates to the document via the
    sync_document_error_status trigger, so we do NOT touch documents here.
    """
    supabase = get_supabase_admin()
    if attempts >= max_attempts:
        supabase.table("ingestion_jobs").update({
            "status":        "error",
            "error_message": error_message[:500],
        }).eq("id", job_id).execute()
        log.warning(f"  job {job_id[:8]}… exhausted {max_attempts} attempts -> error")
    else:
        supabase.table("ingestion_jobs").update({
            "status":        "pending",
            "started_at":    None,
            "error_message": error_message[:500],
        }).eq("id", job_id).execute()
        log.info(f"  job {job_id[:8]}… will retry (attempt {attempts}/{max_attempts})")


# ── Job runner ─────────────────────────────────────────────────────────────

def run_job(job: dict) -> None:
    doc_id       = job["document_id"]
    org_id       = job["organization_id"]
    job_id       = job["id"]
    attempts     = job.get("attempts", 1)
    max_attempts = job.get("max_attempts", 3)

    log.info(f"Job {job_id[:8]}…  doc={doc_id[:8]}…  attempt {attempts}/{max_attempts}")

    supabase = get_supabase_admin()

    doc_res = supabase.table("documents").select(
        "storage_path, filename"
    ).eq("id", doc_id).single().execute()
    if not doc_res.data:
        raise RuntimeError(f"Document {doc_id} not found in database")

    storage_path = doc_res.data.get("storage_path")
    if not storage_path:
        raise RuntimeError(
            f"Document {doc_id} has no storage_path — original upload may have failed"
        )

    log.info(f"  ↓ Downloading {storage_path}")
    file_bytes = supabase.storage.from_(settings.STORAGE_BUCKET).download(storage_path)
    if not file_bytes:
        raise RuntimeError(f"Downloaded empty file from storage: {storage_path}")
    log.info(f"  ✓ Downloaded {len(file_bytes):,} bytes — starting pipeline")

    # Heartbeat keeps this job from being reclaimed while it legitimately runs.
    hb_thread, hb_stop = _start_heartbeat(job_id)
    try:
        process_from_storage(doc_id=doc_id, file_bytes=file_bytes, organization_id=org_id)
    finally:
        hb_stop.set()
        hb_thread.join(timeout=5)

    log.info(f"  ✓ Pipeline complete — marking job done")
    complete_job(job_id)


# ── Main loop ──────────────────────────────────────────────────────────────

def main() -> None:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT,  _handle_signal)

    log.info("=" * 60)
    log.info("CrewBrief ingestion worker starting")
    log.info(f"  Storage bucket : {settings.STORAGE_BUCKET}")
    log.info(f"  Poll interval  : {POLL_INTERVAL_SECONDS}s")
    log.info(f"  Heartbeat      : every {HEARTBEAT_INTERVAL}s")
    log.info("=" * 60)

    import time
    last_heartbeat_log = time.time()

    while not _shutdown:
        try:
            job = claim_job()

            if job:
                last_heartbeat_log = time.time()
                job_id       = job["id"]
                attempts     = job.get("attempts", 1)
                max_attempts = job.get("max_attempts", 3)
                try:
                    run_job(job)
                    log.info(f"Job {job_id[:8]}… completed ✓")
                except Exception as exc:
                    err = str(exc)
                    log.error(f"Job {job_id[:8]}… failed: {err}")
                    try:
                        fail_job(job_id, err, attempts, max_attempts)
                    except Exception as inner:
                        log.error(f"Failed to record job failure: {inner}")
                # Loop straight back to claim the next job (no idle wait).
                continue

            # Queue empty — log a periodic heartbeat, then wait (interruptibly).
            now = time.time()
            if now - last_heartbeat_log >= LOG_HEARTBEAT_EVERY:
                log.info("Worker alive — queue empty, polling…")
                last_heartbeat_log = now

            # Interruptible sleep: wakes instantly if a shutdown signal fires.
            _wake.wait(timeout=POLL_INTERVAL_SECONDS)

        except Exception as exc:
            log.error(f"Worker loop error: {exc}")
            _wake.wait(timeout=POLL_INTERVAL_SECONDS)

    log.info("Worker stopped.")


if __name__ == "__main__":
    main()
