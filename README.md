# One read(), Three Sizes: test kit

Scripts for the three tests of the article "One read(), Three Sizes: Monitor System Calls in
Python, C#/.NET and PostgreSQL".

| Size   | Data                                                  | Recorded with                |
|--------|-------------------------------------------------------|------------------------------|
| Size 1 | The data that your code reads                         | known from the program       |
| Size 2 | The data that the runtime reads from the kernel       | strace                       |
| Size 3 | The data that the kernel reads from the disk          | kernel tracepoints (tracefs) |

The scripts record size 3 through tracefs (`/sys/kernel/tracing`). bpftrace and perf use the same
tracepoints. `test1/loaded.bt` is the bpftrace version of the Test 1 recording, as shown in the article.

## Requirements

Linux 6.18 or a kernel with the `readahead` tracepoints (`ls /sys/kernel/tracing/events/readahead`),
root, strace, Python 3 with matplotlib, the .NET 8 SDK (Test 1, C#), PostgreSQL 16 or newer with
pgbench (Test 2) and PostgreSQL 18 (Test 3). Use a quiet test machine: the scripts empty the page
cache, change the readahead value of the disk for a short time and restart PostgreSQL.

## Test 1: what does the kernel read for 100 bytes?

    cd test1
    sh make_data.sh                         # data.bin (256 MiB) and offsets.txt
    sudo python3 run_test1.py python        # results/test1_python.json
    (cd ../csharp && dotnet build -c Release)
    sudo python3 run_test1.py dotnet ../csharp/bin/Release/net8.0/exp1cs.dll   # results/test1_csharp.json

Each mode runs two times: with the current readahead value and with readahead 0. The script sets the
old value back at the end.

## Test 2: where does PostgreSQL find an 8 KiB page?

    sudo -u postgres createdb bench
    sudo -u postgres pgbench -i -s 100 bench
    cd test2
    sudo PGBIN=/usr/lib/postgresql/18/bin PGDATA=/var/lib/postgresql/18/main python3 run_test2.py

The script stops and starts the server with `pg_ctl` (shared_buffers 128MB, then 2GB) and writes
`results/test2.json` and `results/test2_fdatasync.json`. If your server runs as a systemd service,
stop the service first, and give the data directory of the server as `PGDATA`.

## Test 3: when does strace not see the I/O of PostgreSQL? (PostgreSQL 18)

    cd test3
    sudo PGBIN=/usr/lib/postgresql/18/bin PGDATA=/var/lib/postgresql/18/main python3 run_test3.py

The script does one cold sequential scan of `pgbench_accounts` for `io_method` = sync, worker and
io_uring, and writes `results/test3.json`. It skips a value that the server does not accept.
At the end it resets `io_method`. This script ran on PostgreSQL 16 in a dry run (one scan, like
`sync`), but not yet on PostgreSQL 18. Check the first result before you use it.

## Figures

    python3 plot_figures.py results figures "Data: <your machine, kernel, versions>"

This draws `fig1_three_sizes.png`, `fig2_offsets.png`, `fig3_page_sources.png` and, if
`results/test3.json` exists, `fig4_io_method.png`.

## Draft results in this kit

`results/` and `figures/` contain draft data from one test machine: a KVM virtual machine with
2 vCPUs (Intel Xeon, 2.10 GHz), 8 GiB RAM, a 256 GiB virtio disk with ext4, Linux 6.18.44,
readahead 128 KiB, Python 3.13.18 and PostgreSQL 16.15. C# and Test 3 were not measured there.
For the article, run all tests on one machine and replace these files.
