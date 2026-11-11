"""Draw Figures 1-3 of the article from the JSON results.

Usage: python3 plot_figures.py RESULTS_DIR OUT_DIR "NOTE FOR THE FOOTER"
Optional input: RESULTS_DIR/test1_csharp.json with the same fields as test1_python.json
(modes "stream" and "random").
"""
import json, os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, LogLocator

RES, OUT, NOTE = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(OUT, exist_ok=True)

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
S1, S2, S3 = "#2a78d6", "#eb6834", "#1baf7a"   # categorical slots 1-3 (validated)
MIB, GIB = 1 << 20, 1 << 30

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 11, "text.color": INK,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.facecolor": SURFACE, "figure.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
    "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
})

def footer(fig):
    fig.text(0.01, 0.01, NOTE, color=INK2, fontsize=8.5, ha="left", va="bottom")

def mib_label(v):
    return f"{v / MIB:,.2f} MiB"

# ---------- Figure 1: three sizes ----------
py = {(r["mode"], r["readahead_kb"]): r for r in json.load(open(f"{RES}/test1_python.json"))}
ra_on = max(k[1] for k in py)
cs_path = f"{RES}/test1_csharp.json"
cs = {(r["mode"], r["readahead_kb"]): r for r in json.load(open(cs_path))} if os.path.exists(cs_path) else {}

groups = [("Python open()", py.get(("open", ra_on))), ("Python os.pread()", py.get(("pread", ra_on))),
          ("C# FileStream", cs.get(("stream", ra_on))), ("C# RandomAccess.Read()", cs.get(("random", ra_on)))]
fig, ax = plt.subplots(figsize=(10, 5.6), dpi=150)
w, gap = 0.26, 0.015
for gi, (name, r) in enumerate(groups):
    if r is None:
        ax.text(gi, 2.2 * MIB, "Not measured\non this machine", ha="center", va="center",
                color=INK2, fontsize=10, style="italic")
        continue
    for si, (key, color) in enumerate((("size1", S1), ("size2", S2), ("size3", S3))):
        x = gi + (si - 1) * (w + gap)
        ax.bar(x, r[key], width=w, color=color, linewidth=0)
        ax.text(x, r[key] * 1.12, mib_label(r[key]), ha="center", va="bottom", fontsize=8.5, color=INK)
ax.set_yscale("log")
ax.set_ylim(0.3 * MIB, 400 * MIB)
ax.set_yticks([1 * MIB, 10 * MIB, 100 * MIB])
ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v / MIB:g} MiB"))
ax.yaxis.set_minor_formatter(FuncFormatter(lambda v, _: ""))
ax.set_xticks(range(len(groups)), [g[0] for g in groups])
ax.tick_params(axis="x", length=0)
ax.grid(axis="x", visible=False)
ax.set_ylabel("Data (logarithmic scale)")
handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in (S1, S2, S3)]
ax.legend(handles, ["Size 1: data that the code reads", "Size 2: data that the runtime reads from the kernel",
                    "Size 3: data that the kernel reads from the disk"],
          loc="upper left", frameon=False, fontsize=9.5, ncol=1)
fig.tight_layout(rect=(0, 0.04, 1, 1))
footer(fig)
fig.savefig(f"{OUT}/fig1_three_sizes.png")
plt.close(fig)

# ---------- Figure 2: size 2 and size 3 per 1 MiB part (Python open(), readahead on) ----------
r = py[("open", ra_on)]
b2 = r["bins_size2"]
b3 = {int(k): v for k, v in r["bins_size3"].items()}
n = len(b2)
x = list(range(n))
KIB = 1024
fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 6.2), dpi=150, sharex=True, sharey=True)
a1.bar(x, [v / KIB for v in b2], width=1.0, color=S1, linewidth=0, edgecolor=SURFACE)
a1.set_title("Size 2: data that CPython reads from the kernel (strace)", loc="left", fontsize=10.5, color=INK)
sync = [v / KIB for v in b3[1]]
asyn = [v / KIB for v in b3[2]]
a2.bar(x, sync, width=1.0, color=S2, linewidth=0)
a2.bar(x, asyn, width=1.0, bottom=sync, color=S3, linewidth=0)
a2.set_title("Size 3: data that the kernel reads from the disk (kernel tracepoints)", loc="left",
             fontsize=10.5, color=INK)
a2.legend([plt.Rectangle((0, 0), 1, 1, color=c) for c in (S2, S3)],
          [f"Synchronous readahead ({sum(b3[1]) / MIB:.2f} MiB)", f"Asynchronous readahead ({sum(b3[2]) / MIB:.2f} MiB)"],
          loc="upper right", frameon=False, fontsize=9, ncol=2)
for a in (a1, a2):
    a.set_ylabel("KiB in each 1 MiB part")
    a.grid(axis="x", visible=False)
a2.set_xlim(-0.5, n - 0.5)
a2.set_xlabel("File offset (MiB)")
a1.set_ylim(0, max(max(b2), max(s + t for s, t in zip(b3[1], b3[2]))) / KIB * 1.25)
fig.tight_layout(rect=(0, 0.04, 1, 1))
footer(fig)
fig.savefig(f"{OUT}/fig2_offsets.png")
plt.close(fig)

# ---------- Figure 3: where PostgreSQL found each 8 KiB page ----------
t2 = json.load(open(f"{RES}/test2.json"))
labels = {"128MB": "shared_buffers = 128 MiB", "2GB": "shared_buffers = 2 GiB"}
fig, ax = plt.subplots(figsize=(10, 3.6), dpi=150)
for yi, r in enumerate(t2):
    vals = [max(r["pct_shared_buffers"], 0), max(r["pct_page_cache"], 0), max(r["pct_disk"], 0)]
    left = 0
    for v, color in zip(vals, (S1, S2, S3)):
        if v > 0:
            ax.barh(yi, v - 0.25 if v > 0.5 else v, left=left, height=0.5, color=color, linewidth=0)
        left += v
    # direct labels: one line under each bar
    ax.text(0, yi + 0.38, f"shared_buffers {vals[0]:.1f} %   ·   Page cache {vals[1]:.1f} %   ·   Disk {vals[2]:.1f} %",
            va="center", ha="left", fontsize=9.5, color=INK)
ax.set_yticks(range(len(t2)), [labels[r["shared_buffers"]] for r in t2])
ax.set_xlim(0, 100)
ax.set_ylim(len(t2) - 0.4, -0.6)
ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f} %"))
ax.set_xlabel("Share of all 8 KiB pages that the queries read (size 1)")
ax.grid(axis="y", visible=False)
ax.tick_params(axis="y", length=0)
ax.legend([plt.Rectangle((0, 0), 1, 1, color=c) for c in (S1, S2, S3)],
          ["shared_buffers", "Page cache", "Disk"], loc="lower center", bbox_to_anchor=(0.5, 1.0),
          frameon=False, ncol=3, fontsize=9.5)
fig.tight_layout(rect=(0, 0.06, 1, 1))
footer(fig)
fig.savefig(f"{OUT}/fig3_page_sources.png")
plt.close(fig)
# ---------- Figure 4: io_method (only if results/test3.json exists) ----------
t3_path = f"{RES}/test3.json"
if os.path.exists(t3_path):
    t3 = json.load(open(t3_path))
    S4 = "#eda100"  # categorical slot 4
    series = [("Read system calls of the backend", S1,
               lambda r: sum(v for k, v in r["calls_by_type"].items()
                             if k.startswith("client backend") and not k.endswith("io_uring_enter"))),
              ("Read system calls of the I/O workers", S2,
               lambda r: sum(v for k, v in r["calls_by_type"].items()
                             if k.startswith("io worker") and not k.endswith("io_uring_enter"))),
              ("io_uring_enter() system calls", S3,
               lambda r: sum(v for k, v in r["calls_by_type"].items() if k.endswith("io_uring_enter"))),
              ("Read operations at the block layer", S4, lambda r: r["block_read_operations"])]
    fig, ax = plt.subplots(figsize=(10, 5.2), dpi=150)
    w = 0.2
    for si, (name, color, f) in enumerate(series):
        for gi, r in enumerate(t3):
            v = f(r); x = gi + (si - 1.5) * (w + 0.01)
            ax.bar(x, v, width=w, color=color, linewidth=0)
            ax.text(x, v, f"{v:,}", ha="center", va="bottom", fontsize=8, color=INK)
    ax.set_xticks(range(len(t3)), [f"io_method = {r['io_method']}" for r in t3])
    ax.tick_params(axis="x", length=0); ax.grid(axis="x", visible=False)
    ax.set_ylabel("Count for one sequential scan")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.legend([plt.Rectangle((0, 0), 1, 1, color=c) for _, c, _ in series], [n for n, _, _ in series],
              loc="upper right", frameon=False, fontsize=9)
    fig.tight_layout(rect=(0, 0.04, 1, 1)); footer(fig)
    fig.savefig(f"{OUT}/fig4_io_method.png"); plt.close(fig)
print("ok")
