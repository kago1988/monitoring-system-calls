"""Test 2: where PostgreSQL finds each 8 KiB page (pgbench -S), and the time of fdatasync().

Usage: sudo PGBIN=/usr/lib/postgresql/18/bin PGDATA=/path/to/data python3 run_test2.py
The database "bench" must exist:  createdb bench && pgbench -i -s 100 bench
"""
import json, os, re, signal, statistics, subprocess, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from tracefs_rec import Recorder

PGBIN = os.environ.get("PGBIN", "/usr/lib/postgresql/18/bin")
PGDATA = os.environ["PGDATA"]
PGUSER = os.environ.get("PGOSUSER", "postgres")          # operating system user of the server
LOG = os.environ.get("PGLOG", "/tmp/pg_test2.log")
RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")

def pg(cmd, check=True):
    return subprocess.run(["su", PGUSER, "-c", cmd], capture_output=True, text=True, check=check).stdout

def restart(shared_buffers):
    pg(f"{PGBIN}/pg_ctl -D {PGDATA} -m fast -w stop", check=False)
    subprocess.run("sync; echo 3 > /proc/sys/vm/drop_caches", shell=True, check=True)
    pg(f"{PGBIN}/pg_ctl -D {PGDATA} -l {LOG} -w -o '-c shared_buffers={shared_buffers}' start")

def parse(path):
    in_read, pages, calls = set(), 0, 0
    pat = re.compile(r'^\s*(.*)-(\d+)\s+\[\d+\]\s+\S+\s+[\d.]+: (\w+)(\(|:| ->)(.*)$')
    for line in open(path):
        m = pat.match(line)
        if not m:
            continue
        tid, ev, rest = m.group(2), m.group(3), m.group(5)
        if ev in ("sys_pread64", "sys_preadv"):
            if m.group(4) == "(":
                in_read.add(tid); calls += 1
            else:
                in_read.discard(tid)
        elif ev == "mm_filemap_add_to_page_cache" and tid in in_read:
            pages += 1 << int(re.search(r"order=(\d+)", rest).group(1))
    return pages * 4096, calls

def run(shared_buffers):
    restart(shared_buffers)
    pg("psql -d bench -Atc \"SELECT pg_stat_reset_shared('io');\"")
    flt = 'comm == "postgres"'
    ev = [("syscalls/sys_enter_pread64", flt), ("syscalls/sys_exit_pread64", flt),
          ("syscalls/sys_enter_preadv", flt), ("syscalls/sys_exit_preadv", flt),
          ("filemap/mm_filemap_add_to_page_cache", flt)]
    with Recorder("t2", ev, f"trace_sb{shared_buffers}.txt", buffer_kb=262144) as rec:
        out = pg("pgbench -S -c 8 -T 60 bench")
    hits, reads = (int(x) for x in pg(
        "psql -d bench -Atc \"SELECT sum(hits), sum(reads) FROM pg_stat_io WHERE object = 'relation';\"").strip().split("|"))
    size3, calls = parse(f"trace_sb{shared_buffers}.txt")
    size1 = (hits + reads) * 8192
    r = {"shared_buffers": shared_buffers, "hits": hits, "reads": reads, "read_calls_traced": calls,
         "size1": size1, "size2": reads * 8192, "size3": size3,
         "tps": float(re.search(r"tps = ([\d.]+)", out).group(1)), "lost_events": rec.lost,
         "pct_shared_buffers": 100 * hits * 8192 / size1, "pct_disk": 100 * size3 / size1}
    r["pct_page_cache"] = 100 - r["pct_shared_buffers"] - r["pct_disk"]
    print(json.dumps(r), flush=True)
    return r

def fdatasync_time():
    """Median time of fdatasync() in one backend during the default pgbench workload."""
    restart("128MB")
    bench = subprocess.Popen(["su", PGUSER, "-c", "pgbench -c 8 -T 60 bench"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(5)
    pid = subprocess.run(["pgrep", "-n", "-f", "postgres: .*bench"], capture_output=True, text=True).stdout.strip()
    subprocess.run(["timeout", "50", "strace", "-T", "-e", "trace=fdatasync", "-p", pid, "-o", "fdatasync.txt"])
    bench.wait()
    t = [float(x) for x in re.findall(r"fdatasync\(.*\)\s+= 0 <([\d.]+)>", open("fdatasync.txt").read())]
    r = {"fdatasync_calls": len(t), "median_ms": statistics.median(t) * 1000,
         "p99_ms": sorted(t)[int(len(t) * 0.99)] * 1000}
    print(r)
    return r

if __name__ == "__main__":
    res = [run("128MB"), run("2GB")]
    json.dump(res, open(os.path.join(RESULTS, "test2.json"), "w"), indent=1)
    json.dump(fdatasync_time(), open(os.path.join(RESULTS, "test2_fdatasync.json"), "w"))
