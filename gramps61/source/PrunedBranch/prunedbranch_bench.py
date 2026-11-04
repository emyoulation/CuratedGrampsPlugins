"""
Pruned Branch - benchmark (draft prototype).

Compares whole-tree listing with branch listing, using both the SQL
keep-table join and the Python per-handle strategy, so the report can
confirm or refute the assumptions behind the design.
"""

import platform
import sqlite3
from time import perf_counter

from gramps.version import VERSION

from prunedbranch_db import (
    SORTABLE,
    STRATEGY_PYTHON,
    STRATEGY_SQL,
    TABLES,
    count_callbacks,
)


def _timed(func):
    start = perf_counter()
    result = func()
    return perf_counter() - start, result


def _consume(cursor_factory):
    count = 0
    with cursor_factory() as cursor:
        for _item in cursor:
            count += 1
    return count


def run_benchmark(session, bench_filter, bench_label, out, trial=False):
    """
    Run all measurements and send report lines to out(line).

    :param session: the active BranchSession, or a prepared trial one
    :param bench_filter: GenericFilter to time on full tree and branch,
        or None
    :param bench_label: text naming that filter
    :param out: callable that receives each report line
    :param trial: True when no session is active: the branch was built
        for this report only and Gramps was never switched to it
    """
    real = session.real
    wrapper = session.wrapper
    saved_strategy = wrapper._pb_strategy
    strategies = [STRATEGY_SQL, STRATEGY_PYTHON] if session.sql_ok else [
        STRATEGY_PYTHON
    ]

    out("Pruned Branch benchmark")
    out(
        f"Gramps {VERSION} | Python {platform.python_version()} | "
        f"SQLite {sqlite3.sqlite_version} | backend {type(real).__name__}"
    )
    if trial:
        out(f"Branch: {session.label} (trial branch; no session active)")
    else:
        out(f"Branch: {session.label}")
    out("Note: the first full-tree pass also warms the disk cache; run")
    out("the benchmark twice and compare the second report.")
    out("")
    out("Session build (seconds)")
    for key, value in session.stats["build"].items():
        out(f"  {key:<28} {value:8.3f}")
    out("")
    out("Switching views (seconds; mostly the active view rebuilding)")
    if not session.stats["switch"]:
        out("  not measured: no session was started")
    for key, value in session.stats["switch"].items():
        out(f"  {key:<28} {value:8.3f}")
    out("")
    out("Signal callbacks on the real database (leak check)")
    if not session.stats["callbacks"]:
        out("  no session started since Gramps was opened")
    for key, total, longop in session.stats["callbacks"]:
        out(f"  {key:<28} total {total:5d}   long-op-start {longop:3d}")
    out("")

    head = f"{'type':<11}{'full rows':>10}{'full s':>9}{'branch':>9}"
    for strategy in strategies:
        head += f"{strategy + ' s':>10}"
    head += f"{'sorted full':>13}{'sorted br':>11}"
    out("Cursor iteration (all raw rows) and sorted handle lists")
    out(head)
    try:
        for table, (_cls, one, _many) in TABLES.items():
            full_t, full_n = _timed(
                lambda: _consume(getattr(real, f"get_{one}_cursor"))
            )
            line = f"{table:<11}{full_n:>10,}{full_t:>9.3f}"
            branch_n = 0
            for strategy in strategies:
                wrapper._pb_strategy = strategy
                br_t, branch_n = _timed(
                    lambda: _consume(getattr(wrapper, f"get_{one}_cursor"))
                )
                if strategy == strategies[0]:
                    line += f"{branch_n:>9,}"
                line += f"{br_t:>10.3f}"
            if table in SORTABLE:
                sf_t, _r = _timed(
                    lambda: getattr(real, f"get_{one}_handles")(True)
                )
                sb_t, _r = _timed(
                    lambda: getattr(wrapper, f"get_{one}_handles")(True)
                )
                line += f"{sf_t:>13.3f}{sb_t:>11.3f}"
            out(line)
        wrapper._pb_strategy = saved_strategy
        out("")

        tree_t, tree_n = _timed(lambda: _consume(real.get_place_tree_cursor))
        line = f"place tree: full {tree_n:,} rows {tree_t:.3f}s"
        for strategy in strategies:
            wrapper._pb_strategy = strategy
            br_t, br_n = _timed(lambda: _consume(wrapper.get_place_tree_cursor))
            line += f" | {strategy} {br_n:,} rows {br_t:.3f}s"
        out(line)
        out("")

        if bench_filter is not None:
            out(f"Person filter: {bench_label}")
            ft_t, ft_r = _timed(lambda: bench_filter.apply(real))
            out(f"  full tree      {len(ft_r):>8,} matches {ft_t:8.3f}s")
            for strategy in strategies:
                wrapper._pb_strategy = strategy
                fb_t, fb_r = _timed(lambda: bench_filter.apply(wrapper))
                out(
                    f"  branch {strategy:<7} {len(fb_r):>8,} matches {fb_t:8.3f}s"
                )
            out("")
    finally:
        wrapper._pb_strategy = saved_strategy

    out(
        "Now:  callbacks total "
        f"{count_callbacks(real)}, long-op-start "
        f"{count_callbacks(real, 'long-op-start')}"
    )
    out("Done.")
