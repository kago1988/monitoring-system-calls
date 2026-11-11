"""Record kernel tracepoints through tracefs (the interface under bpftrace and perf).

Usage as a module:
    with Recorder("t1", events, out_path): run_workload()
events: list of (group/event, filter or None)
"""
import os, subprocess, time

TRACEFS = "/sys/kernel/tracing"

class Recorder:
    def __init__(self, name, events, out_path, buffer_kb=131072):
        self.inst = f"{TRACEFS}/instances/{name}"
        self.events, self.out_path, self.buffer_kb = events, out_path, buffer_kb

    def _w(self, rel, val):
        with open(f"{self.inst}/{rel}", "w") as f:
            f.write(val)

    def __enter__(self):
        if not os.path.isdir(f"{TRACEFS}/events"):
            subprocess.run(["mount", "-t", "tracefs", "nodev", TRACEFS], check=True)
        if os.path.isdir(self.inst):
            os.rmdir(self.inst)
        os.mkdir(self.inst)
        self._w("buffer_size_kb", str(self.buffer_kb))
        self._w("trace_clock", "mono")
        for ev, flt in self.events:
            if flt:
                self._w(f"events/{ev}/filter", flt)
            self._w(f"events/{ev}/enable", "1")
        self._w("trace", "")
        self._w("tracing_on", "1")
        time.sleep(0.2)
        return self

    def __exit__(self, *exc):
        time.sleep(0.5)
        self._w("tracing_on", "0")
        time.sleep(0.5)
        with open(f"{self.inst}/trace") as src, open(self.out_path, "w") as dst:
            for line in src:
                if not line.startswith("#"):
                    dst.write(line)
        lost = sum(int(l.split()[-1]) for cpu in os.listdir(f"{self.inst}/per_cpu")
                   for l in open(f"{self.inst}/per_cpu/{cpu}/stats") if l.startswith("overrun"))
        for ev, _ in self.events:
            self._w(f"events/{ev}/enable", "0")
        os.rmdir(self.inst)
        self.lost = lost
        return False
