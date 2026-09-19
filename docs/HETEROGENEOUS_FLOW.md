# Lane-less discharge: measuring pressure in seconds, not vehicles

This is the part of SmartTraffic that is not standard practice. Everything else
here — max-pressure control, green waves, preemption, transit priority, shielded
RL — is established work, well implemented. This is not.

## The gap

Signal-control theory assumes lane discipline. Vehicles queue single file and
cross the stop line one per lane per saturation headway, and a static PCU factor
converts other classes into car equivalents. Both assumptions come from road
environments that Indian urban traffic does not resemble.

In lane-less flow, two-wheelers filter forward into lateral gaps and discharge
two or three abreast inside one nominal lane. So what limits the number of
vehicles crossing the stop line per second is the **lateral road space** each
class occupies — not a space-equivalence factor calibrated for moving flow.

Every controller in this project, and most in the literature, measured pressure
as a *count* of vehicles. A queue of 30 two-wheelers and a queue of 30 cars
looked identical to it. The first clears in about a third of the time.

## The model

Discharge time per vehicle of class `i` on an approach `W` lane-widths wide:

```
t_i = w_i * h_i / W

  w_i   lateral width occupied, in lane-equivalents
  h_i   saturation headway in its own track, seconds
```

It is deliberately calibrated to reproduce the conventional result where the
conventional assumptions hold. A car at `w=1.0, h=2.0` on a two-lane approach
gives `t = 1.0 s`, i.e. 1800 veh/h/lane — the textbook saturation flow. The
model departs from convention only as lane discipline breaks down.

| class | static PCU | PCU implied by discharge | over-statement |
|---|---|---|---|
| two-wheeler | 0.50 | 0.32 | **+56%** |
| auto | 0.80 | 0.66 | +21% |
| car | 1.00 | 1.00 | 0% |
| bus | 3.00 | 1.80 | +67% |

Green-time error for a 30-vehicle queue, by two-wheeler share:

| two-wheeler share | PCU believes | actually needs | error |
|---|---|---|---|
| 0% | 31.2 s | 29.4 s | +6.0% |
| 30% | 26.7 s | 23.3 s | +14.5% |
| 45% | 24.2 s | 19.9 s | **+21.5%** |
| 75% | 20.2 s | 14.5 s | +39.5% |

Swept across the plausible parameter range (two-wheeler width 0.30–0.55
lane-equivalents, headway 1.2–2.0 s) at a 45% share, the error runs **+4.6% to
+34.7%**, median +21.5%. It collapses only at the most conservative corner.

## What it took to make it matter

The measurement error is large. Getting it to change a control decision was
not straightforward, and the failures are the useful part.

**Attempt 1 — composition-aware phase selection. No effect.** Every approach
drew from the same composition, so PCU's bias applied equally to both sides of
the NS-vs-EW comparison and cancelled. A systematic error identical on both
sides of a comparison cannot change which side wins. *Correcting a measure only
matters where the things being compared differ in that measure.*

**Attempt 2 — contrasting mixes across approaches.** A two-wheeler feeder meets
a bus arterial. Only blocked arrivals moved, and barely (−17 ± 16).

**Attempt 3 — diagnosis.** The two controllers issued identical decisions 84.7%
of the time, and the green-duration estimate was pinned at its minimum on every
single tick. Making two-wheelers cheap to discharge had *raised* network
capacity, leaving it undersaturated. Nothing was scarce, so allocating it badly
cost nothing.

**Attempt 4 — allocate duration, under genuine scarcity.** Phase *selection* is
binary and rarely flips under rescaling. Green *duration* is where a mis-measured
queue actually costs something.

## The result

With competing approaches carrying different mixes, and demand high enough that
green time is scarce, measured over 10 seeds with paired confidence intervals:

| condition | people served | vehicles served |
|---|---|---|
| uniform mix, demand ×4 | −180 ± 597 (noise) | +48 ± 39 |
| **contrasting mixes, demand ×4** | **+3356 ± 1575** | −1971 ± 959 |
| **contrasting mixes, demand ×7** | **+6602 ± 927** | −5102 ± 557 |

The mechanism, confirmed directly: static PCU gives the two-wheeler road
**55.3%** of green; the corrected measure gives it **45.1%**. Wasted green is
unchanged (3.68% vs 3.86%), so this is not about eliminating waste — it is about
*who gets the green*. PCU over-states two-wheeler demand, so it hands a
two-wheeler feeder more green than the traffic needs. Correcting that returns
roughly ten percentage points of green to the arterial, which is where the buses
are.

## Fixing what it cost: `person-seconds-v1`

The result above was bought at a price, and the price was the wrong shape. The
efficiency measure optimises *green-seconds per vehicle cleared*, and because
two-wheelers are cheap to clear, an approach full of them scores low on exactly
the quantity being maximised. Green drifted to the arterial and the feeder
starved — a worst-approach wait of 187.6 ticks at demand ×7, which is minutes of
standing still.

That was optimising a proxy. Road efficiency is a constraint, not the objective.
What a signal should maximise is people moved, so the quantity that follows is
**people per second of green**:

```
rate_i = (people waiting on approach i) / (green seconds approach i needs)
```

A two-wheeler queue now scores well despite carrying few people per vehicle,
precisely because it clears so fast — the efficiency controller could only see
the denominator. An explicit fairness term proportional to accumulated red time
sits on top, so a waiting approach gains priority when the choice is close.

Ten seeds, contrasting mixes, paired intervals:

| demand ×7 | people | vehicles | worst-approach wait |
|---|---|---|---|
| `pcu-timed-v1` (conventional) | 34,671 | 13,077 | 32.1 |
| `heterogeneous-timed-v1` (efficiency) | 41,273 | 7,975 | **187.6** |
| **`person-seconds-v1`** | 36,663 | 11,210 | **37.1** |

Against the conventional baseline it still moves significantly more people
(+1,992 ± 687 at ×7, +2,614 ± 373 at ×4). Against the efficiency controller it
gives up some person-throughput and wins back 3,235 vehicles and a **five-fold
reduction in worst-case wait**. At demand ×4 its 95th-percentile delay is 38.5
ticks lower, significant.

That is the trade worth making. A controller that moves marginally more people
by leaving one approach red for minutes is not deployable, and no transport
authority would sign it off.

## The honest caveats

**It still trades vehicles for people.** `person-seconds-v1` serves about 1,900
fewer vehicles than the conventional baseline while moving 2,000 more people.
Whether a city wants that is a policy question, not a technical one, and it
should be asked rather than assumed.

**Delay is still above the conventional baseline.** p95 is 6.1 ticks higher than
`pcu-timed-v1` at demand ×7. The starvation is fixed; moving more people is
still not free.

**The efficiency-only controller is kept, and should not be deployed.**
`heterogeneous-timed-v1` remains in the registry because it is what isolates the
measurement effect, and because the starvation it causes is the evidence for why
`person-seconds-v1` is shaped the way it is.

**The conditions are narrow and must be stated.** No uniform-mix effect. No
undersaturated effect. The claim is conditional, and the conditions are exactly
the ones an Indian arterial meets at peak — which is the point — but the claim
does not generalise beyond them.

**The parameters are estimates, not measurements.** Lateral widths and headways
are centre estimates. They must be calibrated against a real junction before any
performance claim is made. `POST /api/calibrate` takes observed counts;
calibrating the *discharge* parameters needs stop-line video, which we have not
done.

**The engine is not a traffic simulator.** Final claims must be regenerated in
SUMO with a heterogeneous vehicle set.

## Reproducing it

```bash
curl http://localhost:8000/api/saturation/report        # the measurement study
python -m pytest tests/test_heterogeneous.py -q         # both halves of the result
```

`tests/test_heterogeneous.py` pins the negative half too — that a uniform mix
shows no significant effect. If a future change makes that test pass for the
wrong reason, the claim in this document has quietly stopped being true.
