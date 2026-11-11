"""Test 3: which process reads the data for each value of io_method (PostgreSQL 18).

Usage: sudo PGBIN=/usr/lib/postgresql/18/bin PGDATA=/path/to/data python3 run_test3.py
The database "bench" must exist (see Test 2). NOTE: written for PostgreSQL 18 and not yet
run on PostgreSQL 18 by the author of this kit. Check the first result before you use it.
"""
import collections, json, os, re, signal, subprocess, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from tracefs_rec import Recorder

PGBIN = os.environ.get("PGBIN", "/usr/lib/postgresql/18/bin")
PGDATA = os.environ["PGDATA"]
PGUSER = os.environ.get("PGOSUSER", "postgres")
LOG = os.environ.get("PGLOG", "/tmp/pg_test3.log")
RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")

def pg(cmd, check=True):
    return subprocess.run(["su", PGUSER, "-c", cmd], capture_output=True, text=True, check=check)

def psql(sql):
    return pg(f"psql -d bench -qAtc \"{sql}\"", check=False).stdout.strip()

def start():
    return pg(f"{PGBIN}/pg_ctl -D {PGDATA} -l {LOG} -w start", check=False).returncode == 0

def stop():
    pg(f"{PGBIN}/pg_ctl -D {PGDATA} -m fast -w stop", check=False)

def run(io_method):
    stop(); start()
    psql(f"ALTER SYSTEM SET io_method = '{io_method}'")
    stop()
    subprocess.run("sync; echo 3 > /proc/sys/vm/drop_caches", shell=True, check=True)
    if not start() or psql("SHOW io_method") != io_method:
        print(io_method, "not available on this server"); return None
    types = dict(line.split("|") for line in psql("SELECT pid, backend_type FROM pg_stat_activity").splitlines())
    session = subprocess.Popen(["su", PGUSER, "-c", "psql -d bench -qAt"], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, text=True)
    session.stdin.write("SET max_parallel_workers_per_gather = 0;\nSELECT pg_backend_pid();\n"); session.stdin.flush()
    backend = session.stdout.readline().strip()
    types[backend] = "client backend (test)"
    strace = subprocess.Popen(["strace", "-c", "-p", backend, "-o", f"strace_{io_method}.txt"])
    time.sleep(1)
    flt = 'comm == "postgres"'
    ev = [("syscalls/sys_enter_pread64", flt), ("syscalls/sys_enter_preadv", flt),
          ("syscalls/sys_enter_io_uring_enter", flt), ("block/block_rq_issue", None)]
    with Recorder("t3", ev, f"trace_{io_method}.txt", buffer_kb=131072) as rec:
        session.stdin.write("SELECT count(*) FROM pgbench_accounts;\n"); session.stdin.flush()
        rows = session.stdout.readline().strip()
    strace.send_signal(signal.SIGINT); strace.wait()
    session.stdin.write("\\q\n"); session.stdin.flush(); session.wait()
    calls, disk_reads = collections.Counter(), 0
    pat = re.compile(r'^\s*(.*)-(\d+)\s+\[\d+\]\s+\S+\s+[\d.]+: (\w+)(\(|:)(.*)$')
    for line in open(f"trace_{io_method}.txt"):
        m = pat.match(line)
        if not m:
            continue
        ev_name, rest = m.group(3), m.group(5)
        if ev_name == "block_rq_issue":
            if re.match(r"\s*\d+,\d+ R", rest):
                disk_reads += 1
        else:
            # trace output shows the thread ID; PostgreSQL processes have one thread each
            calls[(types.get(m.group(2), "other postgres process"), ev_name)] += 1
    strace_calls = {}
    for line in open(f"strace_{io_method}.txt"):
        f = line.split()
        if f and f[-1] in ("pread64", "preadv", "io_uring_enter"):
            strace_calls[f[-1]] = int(f[3])
    r = {"io_method": io_method, "rows": rows, "strace_backend": strace_calls,
         "calls_by_type": {f"{k[0]}|{k[1]}": v for k, v in calls.items()},
         "block_read_operations": disk_reads, "lost_events": rec.lost}
    print(json.dumps(r), flush=True)
    return r

if __name__ == "__main__":
    res = [r for m in ("sync", "worker", "io_uring") if (r := run(m))]
    stop(); start(); psql("ALTER SYSTEM RESET io_method"); stop(); start()
    json.dump(res, open(os.path.join(RESULTS, "test3.json"), "w"), indent=1)
