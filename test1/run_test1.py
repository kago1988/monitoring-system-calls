"""Test 1: size 1, size 2 (strace) and size 3 (kernel tracepoints) for exp1.py."""
import json, os, re, subprocess, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from tracefs_rec import Recorder

DATA = os.path.abspath("data.bin")
INO = os.stat(DATA).st_ino
def _ra_file(path):
    st = os.stat(path)
    dev = os.path.realpath(f"/sys/dev/block/{os.major(st.st_dev)}:{os.minor(st.st_dev)}")
    if os.path.exists(f"{dev}/partition"):
        dev = os.path.dirname(dev)
    return f"{dev}/queue/read_ahead_kb"

RA_FILE = _ra_file(DATA)
RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
MIB = 1 << 20
NBINS = os.path.getsize(DATA) // MIB

def parse_strace(path):
    pos, size2, calls, bins = {}, 0, 0, [0] * NBINS
    pat = re.compile(r'^(\d+)\s+(lseek|read|pread64)\((\d+)<[^>]*data\.bin>, (.*)\)\s+= (-?\d+)')
    for line in open(path):
        m = pat.match(line)
        if not m:
            continue
        pid, name, fd, args, ret = m.group(1), m.group(2), m.group(3), m.group(4), int(m.group(5))
        key = (pid, fd)
        if name == "lseek":
            pos[key] = ret
            continue
        if name == "read":
            off = pos.get(key, 0)
            pos[key] = off + max(ret, 0)
        else:
            off = int(args.rsplit(",", 1)[1])
        if ret > 0:
            calls += 1
            size2 += ret
            b, end = off, off + ret
            while b < end:  # spread bytes over 1 MiB bins
                nb = min(end, (b // MIB + 1) * MIB)
                bins[b // MIB] += nb - b
                b = nb
    return size2, calls, bins

def parse_trace(path):
    cause = {}
    size3 = {0: 0, 1: 0, 2: 0}
    bins = {c: [0] * NBINS for c in (0, 1, 2)}
    pat = re.compile(r'^\s*(.*)-(\d+)\s+\[\d+\]\s+\S+\s+[\d.]+: (\w+): (.*)$')
    for line in open(path):
        m = pat.match(line)
        if not m:
            continue
        tid, ev, rest = m.group(2), m.group(3), m.group(4)
        if ev == "page_cache_sync_ra":
            cause[tid] = 1
        elif ev == "page_cache_async_ra":
            cause[tid] = 2
        elif ev in ("sys_read", "sys_pread64") or ev.startswith("sys_exit"):
            cause.pop(tid, None)
        elif ev == "mm_filemap_add_to_page_cache":
            ofs = int(re.search(r"ofs=(\d+)", rest).group(1))
            order = int(re.search(r"order=(\d+)", rest).group(1))
            nbytes = 4096 << order
            c = cause.get(tid, 0)
            size3[c] += nbytes
            bins[c][ofs // MIB] += nbytes
    return size3, bins

def command(runtime, mode):
    if runtime == "python":
        return ["python3", "exp1.py", DATA, mode]
    return ["dotnet", DLL, DATA, mode]

def run(runtime, mode, ra_kb):
    open(RA_FILE, "w").write(str(ra_kb))
    subprocess.run("sync; echo 3 > /proc/sys/vm/drop_caches", shell=True, check=True)
    ev = [("readahead/page_cache_sync_ra", f"i_ino == {INO}"),
          ("readahead/page_cache_async_ra", f"i_ino == {INO}"),
          ("filemap/mm_filemap_add_to_page_cache", f"i_ino == {INO}"),
          ("syscalls/sys_exit_read", None), ("syscalls/sys_exit_pread64", None)]
    tag = f"{runtime}_{mode}_ra{ra_kb}"
    with Recorder("t1", ev, f"trace_{tag}.txt") as rec:
        subprocess.run(["strace", "-f", "-y", "-s", "0", "-e", "trace=lseek,read,pread64",
                        "-o", f"strace_{tag}.txt"] + command(runtime, mode), check=True)
    size2, calls, bins2 = parse_strace(f"strace_{tag}.txt")
    size3, bins3 = parse_trace(f"trace_{tag}.txt")
    return {"mode": mode, "readahead_kb": ra_kb, "size1": 10000 * 100, "size2": size2,
            "read_calls": calls, "size3": sum(size3.values()), "size3_by_cause": size3,
            "bins_size2": bins2, "bins_size3": bins3, "lost_events": rec.lost}

if __name__ == "__main__":
    # Usage: sudo python3 run_test1.py python
    #        sudo python3 run_test1.py dotnet /path/to/exp1cs.dll
    runtime = sys.argv[1]
    DLL = os.path.abspath(sys.argv[2]) if runtime == "dotnet" else None
    modes = ("open", "pread") if runtime == "python" else ("stream", "random")
    original = open(RA_FILE).read().strip()
    results = []
    try:
        for mode in modes:
            for ra in (int(original), 0):
                r = run(runtime, mode, ra)
                print(mode, ra, "size2", r["size2"], "calls", r["read_calls"], "size3", r["size3"],
                      r["size3_by_cause"], "lost", r["lost_events"], flush=True)
                results.append(r)
    finally:
        open(RA_FILE, "w").write(original)
    name = "test1_python.json" if runtime == "python" else "test1_csharp.json"
    json.dump(results, open(os.path.join(RESULTS, name), "w"))
