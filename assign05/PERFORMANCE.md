# Performance

Machine: Python 3.12.3 on Linux x86_64

Raw SHA-256d header hashing: **1,191,943 hashes/second** (best of 3 x 200,000 hashes).

Expected vs observed attempts (10 trials per row; each row is a fresh set of fixed pseudo-headers, so attempt counts are reproducible and only the time column varies):

| bits | trials | expected | observed mean | median | min | max | obs/exp | z | time (s) |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 8 | 10 | 256 | 404.8 | 137 | 7 | 2,361 | 1.58 | +1.84 | 0.00 |
| 12 | 10 | 4,096 | 4,922.5 | 3,774 | 456 | 15,615 | 1.20 | +0.64 | 0.05 |
| 16 | 10 | 65,536 | 102,718.9 | 96,377 | 1,896 | 208,863 | 1.57 | +1.79 | 0.87 |
| 20 | 10 | 1,048,576 | 1,246,486.3 | 1,219,443 | 165,195 | 2,450,995 | 1.19 | +0.60 | 10.56 |

Mining time at difficulty `b` bits is about `2^b / hash_rate`: the toy targets used in the tests (4 to 10 bits) take microseconds to milliseconds, and 20 bits takes about a second per block on this machine.
