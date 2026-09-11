# Day 2 — matcher sweep results

## all-MiniLM-L6-v2 — T sweep at W=3.0d

```
     T    prec  recall      F1  #cases     FP     FN
  0.18   0.966   1.000   0.983      57     32      0
  0.20   0.966   0.987   0.976      58     32     12
  0.22   0.966   0.977   0.971      59     32     21
  0.24   0.965   0.960   0.962      61     32     37
  0.26   1.000   0.960   0.979      63      0     37
  0.28   1.000   0.942   0.970      66      0     53
  0.30   1.000   0.932   0.965      68      0     62
  0.32   1.000   0.916   0.956      70      0     77
  0.34   1.000   0.916   0.956      70      0     77
  0.36   1.000   0.888   0.940      73      0    103
  0.38   1.000   0.877   0.934      74      0    113
  0.40   1.000   0.819   0.900      78      0    166
  0.42   1.000   0.774   0.873      83      0    207
```

## Window sweep at T=0.18

```
  W(d)    prec  recall      F1  #cases
     3   0.966   1.000   0.983      57
     7   0.929   1.000   0.963      55
    14   0.919   1.000   0.958      53
    30   0.274   1.000   0.430      28
```

## Structure checks at chosen config

```
near-miss ['fan_room305', 'hostelB_fan_r210'] merged=False OK
near-miss ['washroom_hostelA_clog', 'washroom_hostelB_clog'] merged=False OK
near-miss ['wifi_hostelB', 'wifi_hostelD'] merged=False OK
singleton broken_window_lib n=1 OK
singleton fan_room305 n=1 OK
singleton gasleak_canteen n=1 OK
singleton pothole_mainroad n=1 OK
largest_group wifi_hostelB#3 size=10 spanned=1 foreign=0 OK
```

## Centroid drift at chosen config

```
non_seed_members=275 marginal=2 below_T_vs_final=0
gap mean=0.126 p90=0.310 max=0.631
```

## Hinglish cross-lingual recall (en-hi), primary vs multilingual

```
     T   A en-hi   A hi-hi   B en-hi   B hi-hi
  0.18     1.000     1.000     1.000     1.000
  0.20     0.971     1.000     1.000     1.000
  0.22     0.949     1.000     1.000     1.000
  0.24     0.910     1.000     0.988     1.000
  0.26     0.910     1.000     0.959     1.000
  0.28     0.876     0.982     0.949     1.000
  0.30     0.854     0.982     0.934     0.982
  0.32     0.818     0.982     0.898     0.964
  0.34     0.818     0.982     0.883     0.964
  0.36     0.774     0.964     0.844     0.964
  0.38     0.749     0.964     0.844     0.964
  0.40     0.630     0.964     0.805     0.911
  0.42     0.555     0.964     0.742     0.911
```

(Hinglish reports detected by heuristic: 111 of 332. en-hi = positive pairs with one English + one Hinglish report — the cross-lingual crux.)