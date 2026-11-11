#!/bin/sh
# Make the 256 MiB test file and the 10,000 random offsets (same seed as in the article).
head -c 256M /dev/urandom > data.bin
python3 -c 'import random; r = random.Random(42); print(*(r.randrange(268435356) for _ in range(10000)), sep="\n")' > offsets.txt
