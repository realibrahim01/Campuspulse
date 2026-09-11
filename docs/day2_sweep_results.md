# Day 2 — matcher sweep results

## all-MiniLM-L6-v2 — T sweep at W=7.0d

```
     T    prec  recall      F1  #cases     FP     FN
  0.30   0.971   0.929   0.950      66     25     65
  0.35   0.971   0.913   0.941      68     25     80
  0.40   1.000   0.819   0.900      78      0    166
  0.45   1.000   0.738   0.849      88      0    240
  0.50   1.000   0.649   0.787      99      0    322
  0.55   1.000   0.550   0.709     112      0    413
  0.60   1.000   0.456   0.626     130      0    499
  0.65   1.000   0.400   0.572     143      0    550
  0.70   1.000   0.323   0.488     162      0    621
  0.75   1.000   0.262   0.415     175      0    677
  0.80   1.000   0.236   0.381     183      0    701
  0.85   1.000   0.216   0.355     189      0    719
```

## Window sweep at T=0.30

```
  W(d)    prec  recall      F1  #cases
     3   1.000   0.932   0.965      68
     7   0.971   0.929   0.950      66
    14   0.959   0.929   0.944      64
    30   0.279   0.923   0.429      35
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
non_seed_members=266 marginal=2 below_T_vs_final=0
gap mean=0.121 p90=0.289 max=0.537
```

## Hinglish cross-lingual recall (en-hi), primary vs multilingual

```
     T   A en-hi   A hi-hi   B en-hi   B hi-hi
  0.30     0.852     0.982     0.932     0.982
  0.35     0.815     0.982     0.854     0.964
  0.40     0.630     0.964     0.805     0.911
  0.45     0.487     0.964     0.628     0.911
  0.50     0.333     0.884     0.545     0.884
  0.55     0.156     0.884     0.428     0.839
  0.60     0.010     0.875     0.304     0.830
  0.65     0.007     0.812     0.165     0.795
  0.70     0.000     0.777     0.088     0.768
  0.75     0.000     0.714     0.000     0.554
  0.80     0.000     0.643     0.000     0.446
  0.85     0.000     0.562     0.000     0.375
```

(Hinglish reports detected by heuristic: 111 of 332. en-hi = positive pairs with one English + one Hinglish report — the cross-lingual crux.)