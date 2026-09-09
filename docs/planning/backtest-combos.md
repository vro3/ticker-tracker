# Evidence-backed combinations, by universe
Generated 2026-09-08 22:06. 4 years daily, closes >= $1. edge = mean return minus that universe's own baseline, in percentage points.

| rule                                                           | universe    |      n |   win5 |   edge5 |   win10 |   edge10 |   win20 |   edge20 |   med10 |
|:---------------------------------------------------------------|:------------|-------:|-------:|--------:|--------:|---------:|--------:|---------:|--------:|
| above_200 + rsi2<10 (Connors pullback)                         | large caps  |  20714 |   55.4 |     0.2 |    55.9 |      0.3 |    55.6 |      0.2 |     0.7 |
| above_200 + rsi2<10 (Connors pullback)                         | speculative |   2007 |   46.3 |    -0.4 |    46.2 |     -1.4 |    44.9 |     -1.9 |    -1.0 |
| above_200 + rsi2<10 + ibs<0.2                                  | large caps  |   9264 |   56.0 |     0.3 |    56.2 |      0.4 |    56.6 |      0.5 |     0.7 |
| above_200 + rsi2<10 + ibs<0.2                                  | speculative |    922 |   46.5 |    -0.6 |    44.7 |     -1.8 |    43.6 |     -2.5 |    -1.1 |
| above_200 + close below lower BB + RSI14<=30                   | large caps  |    460 |   60.2 |     0.5 |    57.8 |      0.4 |    58.9 |      0.3 |     0.9 |
| below_200 + close below lower BB + RSI14<=30 (no trend filter) | large caps  |   5493 |   59.8 |     0.8 |    61.9 |      1.0 |    61.0 |      1.4 |     1.6 |
| below_200 + close below lower BB + RSI14<=30 (no trend filter) | speculative |    505 |   48.3 |     0.1 |    53.1 |      0.3 |    51.3 |      0.6 |     1.1 |
| above_200 + down 7% day                                        | large caps  |    821 |   59.1 |     1.7 |    55.9 |      1.8 |    53.2 |      1.7 |     1.5 |
| above_200 + down 7% day                                        | speculative |   1296 |   49.1 |     1.5 |    46.3 |      1.6 |    44.2 |      2.5 |    -1.4 |
| below_200 + down 7% day                                        | large caps  |   1407 |   54.9 |     0.8 |    58.6 |      1.5 |    64.6 |      3.4 |     1.5 |
| below_200 + down 7% day                                        | speculative |   1553 |   48.0 |     0.8 |    48.9 |      0.8 |    47.1 |     -1.0 |     0.0 |
| above_200 + strat 2d-2u reversal                               | large caps  |  30236 |   53.4 |    -0.0 |    53.3 |     -0.1 |    54.3 |     -0.2 |     0.4 |
| above_200 + strat 2d-2u reversal                               | speculative |   2749 |   47.6 |     0.2 |    48.6 |      0.5 |    47.1 |      0.8 |    -0.4 |
| above_200 + ftfc green (all frames)                            | large caps  |  74957 |   53.2 |    -0.1 |    54.3 |     -0.1 |    55.0 |     -0.2 |     0.5 |
| above_200 + ftfc green (all frames)                            | speculative |   5966 |   50.7 |     0.8 |    52.4 |      1.6 |    50.4 |      2.8 |     0.9 |
| above_200 + squeeze fired up                                   | large caps  |   4418 |   51.6 |    -0.3 |    52.6 |     -0.4 |    53.9 |     -0.6 |     0.3 |
| above_200 + squeeze fired up                                   | speculative |    323 |   43.0 |    -1.3 |    44.6 |     -0.6 |    46.4 |      2.6 |    -1.6 |
| above_200 + ema8 crosses above vwma26                          | large caps  |   5857 |   52.8 |    -0.1 |    52.6 |     -0.3 |    54.3 |     -0.4 |     0.4 |
| above_200 + ema8 crosses above vwma26                          | speculative |    539 |   44.2 |     0.3 |    47.5 |      1.1 |    46.4 |      3.5 |    -0.9 |
| ema stack bull + pullback to 21 EMA                            | large caps  |  19495 |   53.8 |     0.0 |    54.3 |     -0.1 |    53.7 |     -0.3 |     0.5 |
| ema stack bull + pullback to 21 EMA                            | speculative |   1379 |   45.3 |     0.3 |    45.9 |     -0.1 |    42.9 |     -0.6 |    -1.9 |
| above_200 + 3-bar bear gap (Vince gap rule, long)              | large caps  |   8656 |   55.2 |     0.2 |    56.1 |      0.2 |    55.9 |      0.3 |     0.7 |
| above_200 + 3-bar bear gap (Vince gap rule, long)              | speculative |   1008 |   48.4 |     0.7 |    46.0 |     -0.1 |    43.1 |      0.5 |    -1.3 |
| baseline                                                       | large caps  | 483804 |   53.4 |     0.0 |    54.4 |      0.0 |    55.4 |      0.0 |     0.5 |
| baseline                                                       | speculative |  55380 |   47.1 |     0.0 |    47.2 |      0.0 |    46.5 |      0.0 |    -0.8 |