# Privacy and data protection

SmartTraffic is a signal-control system, not a surveillance system. This
document states what it collects, what it deliberately does not, and how that
maps to India's Digital Personal Data Protection Act, 2023 (DPDP).

## What the system processes

| Data | Purpose | Retained |
| --- | --- | --- |
| Per-approach vehicle counts | Signal timing decisions | In memory, current cycle only |
| Per-approach bus counts | Person-weighted priority | In memory, current cycle only |
| Pedestrian counts | Guaranteeing maximum crossing wait | In memory, current cycle only |
| Phase decisions and the reason for each | Engineering audit after an incident | Rolling window, last 400 decisions |
| Aggregate delay statistics | Benchmarking and impact reporting | Per run |

## What the system deliberately does not do

- **No number-plate recognition.** No ANPR, no plate text, no vehicle identity.
- **No face detection or recognition.** People are never the detection target.
- **No individual vehicle tracking across junctions.** The engine tracks a
  queue position so it can compute delay; that record carries an arrival tick
  and a vehicle class, and nothing that identifies a vehicle or its owner.
- **No image retention.** `POST /api/vision/analyse` writes the uploaded frame
  to a temporary file, runs detection, and deletes it when the request ends.
  Only counts, confidences and bounding boxes are returned; the frame itself is
  never stored or forwarded.
- **No third-party transmission.** Detection runs locally against locally-held
  YOLO weights. Nothing is sent to an external API.

## Why this matters under DPDP

Counts of vehicles are not personal data, because they cannot be linked to an
identifiable individual. By restricting the system to counts, SmartTraffic
stays outside the Act's obligations for personal data entirely, rather than
relying on consent, notice and retention controls to justify collecting it.

This is a design decision with a cost: plate-level data would allow
origin-destination inference and per-vehicle travel-time measurement, both
genuinely useful for traffic planning. We consider that trade a poor one for a
signal controller, which does not need to know *which* vehicles are waiting in
order to decide how long to hold a green.

## If a deployment adds cameras with ANPR

That is a different system with different obligations, and it must not be
bolted onto this one silently. It would require, at minimum: a notice under
DPDP §5, a stated retention period, a named Data Protection Officer, access and
erasure handling, and an assessment of whether the purpose could be met with
counts alone. The signal-control logic in this repository does not need any of
it, and should stay separable from anything that does.

## Operational access

The decision audit (`GET /api/safety/audit`) records signal decisions, not
people. It is intended for traffic engineers reviewing an incident, and it
contains no data about who was at the junction.
