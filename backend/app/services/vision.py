"""Estimate junction state from a camera frame, with honest confidence.

The pipeline is deliberately three separable stages, because the failure modes
are different and an operator needs to see which one went wrong:

1. **Detect** vehicles in the frame (YOLO, running locally).
2. **Bind** each detection to an approach, using an image mask.
3. **Score** the result, so a controller can decide whether to trust it.

Stage 3 is the one usually missing. A detector that finds 4 vehicles in fog at
0.31 confidence should not silently seed the controller with "4"; it should
say it is unsure and let the operator correct it, which is what
``apply_corrections`` is for.

Privacy: only counts and bounding boxes leave this module. No number plates are
read, no faces are matched, no image is retained after the request. See
``docs/PRIVACY.md``.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from app.models import DIRECTIONS

VEHICLE_LABELS = {'car', 'motorcycle', 'bus', 'truck'}

#: Detections below this score are counted but flagged for operator review.
LOW_CONFIDENCE = 0.45

#: A lane estimate this uncertain should not be trusted to seed the controller.
REVIEW_THRESHOLD = 0.55


def detector_status() -> dict:
    weights = os.getenv('SMARTTRAFFIC_YOLO_WEIGHTS', 'yolov8n.pt')
    try:
        import ultralytics  # noqa: F401
        available = True
    except Exception:
        available = False
    return {
        'backend': 'ultralytics-yolo',
        'available': available,
        'weights': weights,
        'note': 'Install ultralytics and provide weights locally for offline SIH use.' if not available else 'ready',
    }


def default_mask() -> dict:
    """Approach regions as fractions of the frame.

    The default assumes a mast-arm camera looking down on the junction, so the
    four approaches fall into the four edges of the image. Real installations
    override this once per camera during commissioning.
    """
    return {
        'north': {'x0': 0.25, 'y0': 0.00, 'x1': 0.75, 'y1': 0.40},
        'south': {'x0': 0.25, 'y0': 0.60, 'x1': 0.75, 'y1': 1.00},
        'west': {'x0': 0.00, 'y0': 0.25, 'x1': 0.40, 'y1': 0.75},
        'east': {'x0': 0.60, 'y0': 0.25, 'x1': 1.00, 'y1': 0.75},
    }


def _bind_to_approach(box: list[float], width: float, height: float, mask: dict) -> str | None:
    """Assign a detection to an approach by where its centre falls."""
    cx = (box[0] + box[2]) / 2.0 / max(1.0, width)
    cy = (box[1] + box[3]) / 2.0 / max(1.0, height)
    for direction, region in mask.items():
        if region['x0'] <= cx <= region['x1'] and region['y0'] <= cy <= region['y1']:
            return direction
    return None


def summarise_lanes(detections: list[dict], width: float, height: float, mask: dict | None = None) -> dict:
    """Turn raw detections into per-approach counts with a confidence score."""
    mask = mask or default_mask()
    lanes: dict[str, dict] = {
        d: {'vehicles': 0, 'buses': 0, 'confidences': []} for d in DIRECTIONS
    }
    unassigned = 0

    for det in detections:
        direction = _bind_to_approach(det['bbox_xyxy'], width, height, mask)
        if direction is None:
            unassigned += 1
            continue
        lane = lanes[direction]
        lane['vehicles'] += 1
        if det['label'] in ('bus', 'truck'):
            lane['buses'] += 1
        lane['confidences'].append(det['confidence'])

    estimates = {}
    for direction, lane in lanes.items():
        scores = lane['confidences']
        mean_conf = sum(scores) / len(scores) if scores else 0.0
        weak = sum(1 for s in scores if s < LOW_CONFIDENCE)
        # An empty lane is a real reading, but a much weaker one than a lane
        # with several confident detections, so it is scored conservatively.
        confidence = mean_conf if scores else 0.4
        estimates[direction] = {
            'vehicles': lane['vehicles'],
            'buses': lane['buses'],
            'confidence': round(confidence, 3),
            'weak_detections': weak,
            'needs_review': confidence < REVIEW_THRESHOLD,
            'source': 'vision',
        }

    overall = sum(e['confidence'] for e in estimates.values()) / len(estimates)
    return {
        'lanes': estimates,
        'unassigned_detections': unassigned,
        'overall_confidence': round(overall, 3),
        'trustworthy': overall >= REVIEW_THRESHOLD and unassigned == 0,
        'mask': mask,
    }


def detect_vehicles(image_bytes: bytes, filename: str = 'upload.jpg', mask: dict | None = None) -> dict:
    status = detector_status()
    if not status['available']:
        return {
            **status,
            'vehicle_count': None,
            'detections': [],
            'reason': 'YOLO runtime is not installed on this server.',
        }

    from ultralytics import YOLO

    suffix = Path(filename).suffix or '.jpg'
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(image_bytes)
        tmp.flush()
        model = YOLO(status['weights'])
        result = model.predict(source=tmp.name, verbose=False)[0]

    detections = []
    names = result.names
    for box in result.boxes:
        cls_id = int(box.cls.item())
        label = names.get(cls_id, str(cls_id)) if isinstance(names, dict) else names[cls_id]
        if label not in VEHICLE_LABELS:
            continue
        xyxy = [round(float(v), 1) for v in box.xyxy[0].tolist()]
        detections.append({
            'label': label,
            'confidence': round(float(box.conf.item()), 4),
            'bbox_xyxy': xyxy,
        })

    height, width = result.orig_shape if hasattr(result, 'orig_shape') else (1080, 1920)
    return {
        **status,
        'vehicle_count': len(detections),
        'detections': detections,
        'frame': {'width': width, 'height': height},
        'estimate': summarise_lanes(detections, width, height, mask),
    }


def apply_corrections(estimate: dict, corrections: dict[str, int]) -> dict:
    """Let an operator overwrite any lane the model got wrong.

    A corrected lane is marked as fully confident and sourced to the operator,
    so the audit trail shows which numbers a human stood behind.
    """
    lanes = {k: dict(v) for k, v in estimate['lanes'].items()}
    applied = []
    for direction, value in corrections.items():
        direction = direction.lower()
        if direction not in lanes:
            continue
        count = max(0, int(value))
        applied.append({
            'direction': direction,
            'from': lanes[direction]['vehicles'],
            'to': count,
        })
        lanes[direction].update({
            'vehicles': count,
            'confidence': 1.0,
            'needs_review': False,
            'source': 'operator',
        })

    overall = sum(v['confidence'] for v in lanes.values()) / max(1, len(lanes))
    return {
        **estimate,
        'lanes': lanes,
        'overall_confidence': round(overall, 3),
        'trustworthy': overall >= REVIEW_THRESHOLD,
        'corrections_applied': applied,
    }


def seed_engine(engine, junction_id: str, estimate: dict, force: bool = False) -> dict:
    """Initialise a junction's queues from a vision estimate.

    Refuses low-confidence estimates unless explicitly forced, so a bad frame
    cannot quietly become the controller's view of the world.
    """
    from app.simulation.mock_engine import Vehicle

    if junction_id not in engine.JUNCTION_IDS:
        raise ValueError(f'unknown junction {junction_id}')
    if not estimate.get('trustworthy') and not force:
        return {
            'applied': False,
            'junction': junction_id,
            'reason': 'estimate confidence below review threshold; correct the lanes or force',
            'overall_confidence': estimate.get('overall_confidence'),
        }

    applied = {}
    from collections import deque

    for direction, lane in estimate['lanes'].items():
        count = int(lane['vehicles'])
        buses = min(count, int(lane.get('buses', 0)))
        vehicles = [Vehicle(arrival_tick=engine.tick, kind='bus') for _ in range(buses)]
        vehicles += [Vehicle(arrival_tick=engine.tick, kind='car') for _ in range(count - buses)]
        engine.lanes[(junction_id, direction)] = deque(vehicles)
        applied[direction] = count

    return {
        'applied': True,
        'junction': junction_id,
        'queues': applied,
        'overall_confidence': estimate.get('overall_confidence'),
        'forced': bool(force and not estimate.get('trustworthy')),
    }
