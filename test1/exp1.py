# exp1.py
import os
import sys

path, mode = sys.argv[1], sys.argv[2]
offsets = [int(line) for line in open("offsets.txt")]

if mode == "open":
    with open(path, "rb") as f:
        for offset in offsets:
            f.seek(offset)
            f.read(100)
else:
    fd = os.open(path, os.O_RDONLY)
    for offset in offsets:
        os.pread(fd, 100, offset)
    os.close(fd)
