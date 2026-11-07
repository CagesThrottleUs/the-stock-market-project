## Targets for Matching Engine

These are the following goals of the matching engine for following performance:

### Latency

Use GoogleBenchmark or nanobench

```math
p_{50} < 100 \text{ns} 
```

```math
p_{99} < 250 \text{ns} 
```

```math
p_{99.9} < 500 \text{ns}
```


### Heap allocation

Use Valgrind to confirm: 0 `malloc`/`free` or `new`/`delete`

### Cache Misses

Using `perf` tool to determine cache miss to be less than 1.0%.

### Instructions per cycle

`perf` also provides this metric and the target is greater than `2.5`.

### Branch Misprediction

Using `perf` we can also determine that branch prediction should be less than 0.5%.
