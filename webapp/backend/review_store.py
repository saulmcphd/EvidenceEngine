"""
review_store.py - EvidenceEngine multi-review manager (recoverable park-and-load)
=================================================================================
The app was built around ONE review living in EE/Outputs (+ criteria.txt + its OKF nodes inside the shared
okf-bundle). This module lets a researcher keep MANY reviews and switch between them WITHOUT losing any, and
WITHOUT rewriting the ~150 places the app reaches into Outputs. The design: exactly one review is "active" (its
data sits in the usual Outputs / criteria.txt / bundle-node locations, so every existing screen keeps working
unchanged); the others are "parked" in EE/reviews/<id>/. Switching PARKS the active review, then LOADS the
target into the active slot - data is *moved* (atomic directory renames on one volume), never deleted, so a
switch can't lose work. Delete is RECOVERABLE (moves to EE/reviews/_trash/). The shared knowledge brain
(concepts / playbooks / references / systems + tool/org entities) NEVER moves - only per-review data does.

A review's data =
  * Outputs/*            (config.json, master_records, audits, reliability, PRISMA, RIS, methods.docx ...)
  * criteria.txt         (EE/criteria.txt - the topic config)
  * its OKF nodes        (bundle: entities/entity-screen-*, entities/entity-study-*, raise-disclosure.md,
                          responsible-handover.md)
Identity + name live in EE/reviews/<id>/manifest.json; the active pointer is EE/reviews/active.json.

Crash-safety: park + load are ordered so data is always recoverable, and `_repair()` (run on every list) heals
the one realistic interrupted state - a park that did not finalise into a load - by restoring the active
review's parked copy. Real reviews are never hard-deleted by this module.
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

# The canonical blank criteria template (mirrors the Setup form's empty state) written for a fresh review.
BLANK_CRITERIA = (
    "# EvidenceEngine shared topic config.\n"
    "# Read VERBATIM by the AI screener (screener_abstract.py / screener_fulltext.py) and by the human reviewer.\n"
    "# Assembled from the Setup form (edit the structured boxes there, or toggle raw edit).\n"
    "\n"
    "REVIEW_TOPIC: \n"
    "FRAMEWORK: \n"
    "\n"
    "PICO_P: \n"
    "PICO_I/E: \n"
    "PICO_C: \n"
    "PICO_O: \n"
    "\n"
    "STUDY_DESIGN_FEATURES: \n"
    "\n"
    "INCLUSION_CRITERIA:\n"
    "\n"
    "EXCLUSION_CRITERIA:\n"
    "\n"
    "ROB_TOOL: auto   # auto = RoB2 for RCTs, ROBINS-I for observational\n"
    "DATE_RANGE: no limit\n"
    "LANGUAGE: \n"
    "PUBLICATION_STATUS: \n"
)

# Bundle nodes that belong to a REVIEW (move with it); everything else is the shared knowledge brain (never moves).
_REVIEW_NODE_GLOBS = ("entities/entity-screen-*.md", "entities/entity-study-*.md")
_REVIEW_TOP_NODES = ("raise-disclosure.md", "responsible-handover.md")

_ID_RE = re.compile(r"^review-\d{4,}$")
# A trashed folder is exactly "<review-id>__<YYYYMMDDTHHMMSS>" (see delete_review). The WHOLE name is validated
# before it is ever joined into a path, so a crafted trash_name (containing .. or separators) cannot escape _trash.
_TRASH_RE = re.compile(r"^review-\d{4,}__\d{8}T\d{6}$")


class ReviewStoreError(Exception):
    """A user-facing review-management error (bad id, name clash, illegal delete, ...)."""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


class ReviewStore:
    def __init__(self, ee_dir, bundle_dir, *, skip_okf: bool = False):
        self.ee = Path(ee_dir)
        self.out = self.ee / "Outputs"
        self.crit = self.ee / "criteria.txt"
        self.bundle = Path(bundle_dir)
        self.reviews = self.ee / "reviews"
        self.trash = self.reviews / "_trash"
        self.active_json = self.reviews / "active.json"
        self.skip_okf = skip_okf   # tests set True to skip okf_writer regen/reindex (file moves still happen)

    # -- small helpers ------------------------------------------------------------------------------
    @staticmethod
    def _read_json(p) -> dict:
        try:
            return json.loads(Path(p).read_text(encoding="utf-8"))
        except Exception:
            return {}

    @staticmethod
    def _write_json(p, obj) -> None:
        Path(p).write_text(json.dumps(obj, indent=2), encoding="utf-8")

    def _config_topic(self, out_dir=None) -> str:
        cfg = self._read_json((Path(out_dir) if out_dir else self.out) / "config.json")
        return str(cfg.get("project_title", "") or "").strip()

    def _review_node_files(self):
        found = []
        for g in _REVIEW_NODE_GLOBS:
            found += sorted(self.bundle.glob(g))
        for n in _REVIEW_TOP_NODES:
            p = self.bundle / n
            if p.exists():
                found.append(p)
        return found

    def _all_ids(self):
        ids = set()
        a = self._read_json(self.active_json)
        if a.get("id"):
            ids.add(a["id"])
        for base in (self.reviews, self.trash):
            if base.exists():
                for d in base.iterdir():
                    stem = d.name.split("__")[0]      # trash dirs are "<id>__<ts>"
                    if d.is_dir() and _ID_RE.match(stem):
                        ids.add(stem)
        return ids

    def _new_id(self) -> str:
        n = 0
        for i in self._all_ids():
            try:
                n = max(n, int(i.split("-")[1]))
            except (IndexError, ValueError):
                pass
        return f"review-{n + 1:04d}"

    def _validate_id(self, review_id) -> str:
        if not (isinstance(review_id, str) and _ID_RE.match(review_id)):
            raise ReviewStoreError(f"invalid review id: {review_id!r}")
        return review_id

    def _ensure_active(self) -> dict:
        """If there is no active pointer, adopt whatever is currently in Outputs as the active review."""
        a = self._read_json(self.active_json)
        if a.get("id"):
            return a
        self.reviews.mkdir(parents=True, exist_ok=True)
        topic = self._config_topic()
        a = {"id": self._new_id(), "name": topic or "Untitled review", "created_at": _now(), "topic": topic}
        self._write_json(self.active_json, a)
        return a

    # -- bundle regen (best-effort; a bundle hiccup must NEVER lose the user's review data) ----------
    def _refresh_bundle(self, blank: bool = False) -> None:
        if self.skip_okf:
            return
        try:
            import okf_writer
            if blank:
                okf_writer.write_raise_disclosure(self.bundle, {})
                okf_writer.write_responsible_handover(self.bundle, {})
            okf_writer.write_index(self.bundle)
        except Exception:
            pass

    # -- core moves ---------------------------------------------------------------------------------
    def _park_active(self) -> dict:
        """Move the active review's data out of the live slot into reviews/<id>/. Leaves the active slot empty
        (Outputs re-created empty, criteria gone, review nodes moved out)."""
        a = self._ensure_active()
        topic = self._config_topic() or a.get("topic", "")   # read topic BEFORE Outputs moves
        dest = self.reviews / a["id"]
        if dest.exists() and any(dest.iterdir()):
            raise ReviewStoreError(f"cannot save the current review: {dest} already exists")
        dest.mkdir(parents=True, exist_ok=True)   # tolerate an empty leftover from a crashed park (also healed by _repair)
        if self.out.exists():
            shutil.move(str(self.out), str(dest / "Outputs"))
        self.out.mkdir(exist_ok=True)                         # fresh empty active slot
        if self.crit.exists():
            shutil.move(str(self.crit), str(dest / "criteria.txt"))
        nodes = self._review_node_files()
        if nodes:
            nd = dest / "okf-nodes"
            nd.mkdir()
            for f in nodes:
                shutil.move(str(f), str(nd / f.name))
        manifest = {"id": a["id"], "name": a.get("name") or "Untitled review",
                    "created_at": a.get("created_at") or _now(), "updated_at": _now(), "topic": topic}
        self._write_json(dest / "manifest.json", manifest)
        return manifest

    def _finish_load(self, review_id: str) -> dict:
        """Move a parked review into the active slot and point active.json at it. IDEMPOTENT/RESUMABLE: safe to
        re-run after an interruption — it moves only whatever is still parked (Outputs move is an atomic dir
        rename, so it is never half-done; criteria/nodes are moved only if still present, overwriting a stale
        duplicate). An EMPTY crash-leftover dir (a park that died right after mkdir) is simply removed, leaving
        the live active review untouched. This is the single healer used by switch/new and by _repair."""
        src = self.reviews / review_id
        if not src.is_dir():
            raise ReviewStoreError(f"no such saved review: {review_id}")
        has_data = ((src / "Outputs").exists() or (src / "criteria.txt").exists()
                    or (src / "okf-nodes").is_dir() or (src / "manifest.json").exists())
        if not has_data:                                     # empty leftover from a crashed park — just drop it
            try:
                src.rmdir()
            except OSError:
                pass
            return self._read_json(self.active_json) or self._ensure_active()
        manifest = self._read_json(src / "manifest.json")
        so = src / "Outputs"
        if so.exists():                                      # Outputs not yet moved (atomic: never partial)
            if self.out.exists() and any(self.out.iterdir()):
                raise ReviewStoreError("inconsistent review state: two Outputs present during load")
            if self.out.exists():
                self.out.rmdir()
            shutil.move(str(so), str(self.out))
        elif not self.out.exists():
            self.out.mkdir(exist_ok=True)
        sc = src / "criteria.txt"
        if sc.exists():
            if self.crit.exists():
                self.crit.unlink()
            shutil.move(str(sc), str(self.crit))
        elif not self.crit.exists():
            self.crit.write_text(BLANK_CRITERIA, encoding="utf-8")
        nd = src / "okf-nodes"
        if nd.is_dir():
            for f in list(nd.iterdir()):
                target = (self.bundle / "entities" / f.name) if f.name.startswith("entity-") \
                    else (self.bundle / f.name)
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    target.unlink()                          # overwrite a stale duplicate (idempotent)
                shutil.move(str(f), str(target))
            try:
                nd.rmdir()
            except OSError:
                pass
        (src / "manifest.json").unlink(missing_ok=True)
        try:
            src.rmdir()
        except OSError:
            pass
        cur = self._read_json(self.active_json)              # preserve name/created if the manifest was lost
        active = {"id": review_id,
                  "name": manifest.get("name") or cur.get("name") or "Untitled review",
                  "created_at": manifest.get("created_at") or cur.get("created_at") or _now(),
                  "topic": manifest.get("topic", cur.get("topic", ""))}
        self._write_json(self.active_json, active)
        self._refresh_bundle(blank=False)                    # reindex to include the loaded review's nodes
        return active

    def _repair(self) -> None:
        """Heal ANY interrupted new/switch. The active pointer is committed to the target BEFORE its data moves,
        so if active.json names a review that is still (wholly or partly) parked, an operation was interrupted:
        finish loading it into the live slot (idempotent). This covers a park that died empty (removed), a park
        that finished but the load never started (rolled back / loaded), and a load interrupted midway (resumed).
        In a completed state reviews/<active-id> never exists, so this is a no-op then."""
        a = self._read_json(self.active_json)
        aid = a.get("id")
        if aid and (self.reviews / aid).is_dir():
            try:
                self._finish_load(aid)
            except Exception:
                pass

    # -- public API ---------------------------------------------------------------------------------
    def _n_records(self, out_dir) -> int:
        m = Path(out_dir) / "master_records.csv"
        if not m.exists():
            return 0
        try:
            with m.open(encoding="utf-8", errors="replace") as f:
                return max(0, sum(1 for _ in f) - 1)         # rows minus header
        except OSError:
            return 0

    def list_reviews(self) -> dict:
        self._repair()
        a = self._ensure_active()
        active = {"id": a["id"], "name": a.get("name") or "Untitled review", "active": True,
                  "created_at": a.get("created_at", ""), "topic": self._config_topic(),
                  "n_records": self._n_records(self.out)}
        parked = []
        if self.reviews.exists():
            for d in sorted(self.reviews.iterdir()):
                if d.is_dir() and _ID_RE.match(d.name) and d.name != a["id"]:
                    m = self._read_json(d / "manifest.json")
                    parked.append({"id": d.name, "name": m.get("name") or "Untitled review", "active": False,
                                   "created_at": m.get("created_at", ""), "topic": m.get("topic", ""),
                                   "n_records": self._n_records(d / "Outputs")})
        trashed = []
        if self.trash.exists():
            for d in sorted(self.trash.iterdir()):
                if d.is_dir():
                    m = self._read_json(d / "manifest.json")
                    trashed.append({"trash_name": d.name, "id": d.name.split("__")[0],
                                    "name": m.get("name") or "Untitled review", "topic": m.get("topic", "")})
        return {"active": active, "reviews": parked, "trash": trashed}

    def new_review(self, name: str = "") -> dict:
        """Save (park) the current review, then open a fresh blank review in the active slot."""
        self._park_active()
        # Commit the new identity BEFORE building the slot. If a crash happens before commit, _repair sees the
        # OLD id still parked and rolls back to it (no half-made review); after commit there is no parked folder
        # for the new blank id, so _repair is a no-op and the worst case is a blank review missing its criteria
        # file (harmless — Setup writes it on first save).
        new = {"id": self._new_id(), "name": (name or "").strip() or "Untitled review",
               "created_at": _now(), "topic": ""}
        self._write_json(self.active_json, new)
        self.out.mkdir(exist_ok=True)
        self.crit.write_text(BLANK_CRITERIA, encoding="utf-8")
        self._refresh_bundle(blank=True)                     # blank disclosure/handover + reindex
        return new

    def switch_review(self, review_id: str) -> dict:
        """Save (park) the current review, then load the target review into the active slot."""
        self._validate_id(review_id)
        a = self._ensure_active()
        if review_id == a["id"]:
            return a                                          # already open
        if not (self.reviews / review_id).is_dir():
            raise ReviewStoreError(f"no such saved review: {review_id}")
        self._park_active()
        # Commit intent to the TARGET before its data moves, so a load interrupted midway is FINISHED (not lost)
        # by _repair on the next list. A crash after park but before this commit leaves the OLD id parked -> rolled
        # back to the old review (the switch simply didn't happen). Either way no data is lost.
        m = self._read_json(self.reviews / review_id / "manifest.json")
        self._write_json(self.active_json, {"id": review_id, "name": m.get("name") or "Untitled review",
                                            "created_at": m.get("created_at") or _now(), "topic": m.get("topic", "")})
        return self._finish_load(review_id)

    def rename_review(self, review_id: str, name: str) -> dict:
        self._validate_id(review_id)
        name = (name or "").strip()
        if not name:
            raise ReviewStoreError("a review name is required")
        a = self._ensure_active()
        if review_id == a["id"]:
            a["name"] = name
            self._write_json(self.active_json, a)
            return a
        mf = self.reviews / review_id / "manifest.json"
        if not mf.exists():
            raise ReviewStoreError(f"no such saved review: {review_id}")
        m = self._read_json(mf)
        m["name"] = name
        m["updated_at"] = _now()
        self._write_json(mf, m)
        return m

    def delete_review(self, review_id: str) -> dict:
        """Move a NON-active review to the recoverable trash. The currently-open review cannot be deleted
        (open another first) - so a delete can never wipe the workspace you're in."""
        self._validate_id(review_id)
        a = self._ensure_active()
        if review_id == a["id"]:
            raise ReviewStoreError("You can't delete the review you're working in - open another review first.")
        src = self.reviews / review_id
        if not src.is_dir():
            raise ReviewStoreError(f"no such saved review: {review_id}")
        self.trash.mkdir(parents=True, exist_ok=True)
        dest = self.trash / f"{review_id}__{_now().replace(':', '').replace('-', '')}"
        shutil.move(str(src), str(dest))
        return {"id": review_id, "trashed_as": dest.name}

    def restore_review(self, trash_name: str) -> dict:
        # Validate the WHOLE name (not just the id stem) before it is joined into a path — a crafted trash_name
        # with '..' or separators must never let src escape _trash (the path-traversal the review caught).
        if not (isinstance(trash_name, str) and _TRASH_RE.match(trash_name)):
            raise ReviewStoreError(f"no such deleted review: {trash_name!r}")
        src = self.trash / trash_name
        if src.resolve().parent != self.trash.resolve():        # belt-and-suspenders containment
            raise ReviewStoreError(f"no such deleted review: {trash_name!r}")
        if not src.is_dir():
            raise ReviewStoreError(f"no such deleted review: {trash_name}")
        review_id = self._validate_id(trash_name.split("__")[0])
        dest = self.reviews / review_id
        if dest.exists():
            raise ReviewStoreError(f"a review with id {review_id} already exists")
        shutil.move(str(src), str(dest))
        return self._read_json(dest / "manifest.json")
