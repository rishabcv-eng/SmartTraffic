import pytest

from app.services.vision import (
    REVIEW_THRESHOLD,
    apply_corrections,
    default_mask,
    seed_engine,
    summarise_lanes,
)
from app.simulation.mock_engine import MockTrafficEngine

WIDTH, HEIGHT = 1000.0, 1000.0


def detection(cx, cy, confidence=0.9, label='car'):
    return {
        'label': label,
        'confidence': confidence,
        'bbox_xyxy': [cx - 10, cy - 10, cx + 10, cy + 10],
    }


def test_detections_bind_to_the_approach_they_sit_in():
    result = summarise_lanes([
        detection(500, 100),   # top of frame -> north
        detection(500, 120),
        detection(500, 900),   # bottom -> south
        detection(100, 500),   # left -> west
        detection(900, 500),   # right -> east
    ], WIDTH, HEIGHT)

    lanes = result['lanes']
    assert lanes['north']['vehicles'] == 2
    assert lanes['south']['vehicles'] == 1
    assert lanes['west']['vehicles'] == 1
    assert lanes['east']['vehicles'] == 1
    assert result['unassigned_detections'] == 0


def test_detections_in_the_junction_centre_are_not_assigned():
    result = summarise_lanes([detection(500, 500)], WIDTH, HEIGHT)

    assert result['unassigned_detections'] == 1
    assert sum(l['vehicles'] for l in result['lanes'].values()) == 0
    assert result['trustworthy'] is False


def test_buses_are_counted_separately():
    result = summarise_lanes([
        detection(500, 100, label='bus'),
        detection(500, 110, label='car'),
    ], WIDTH, HEIGHT)

    assert result['lanes']['north']['vehicles'] == 2
    assert result['lanes']['north']['buses'] == 1


def test_low_confidence_detections_are_flagged_for_review():
    weak = summarise_lanes([detection(500, 100, confidence=0.30)], WIDTH, HEIGHT)
    strong = summarise_lanes([detection(500, 100, confidence=0.95)], WIDTH, HEIGHT)

    assert weak['lanes']['north']['needs_review'] is True
    assert weak['lanes']['north']['weak_detections'] == 1
    assert strong['lanes']['north']['needs_review'] is False
    assert weak['overall_confidence'] < strong['overall_confidence']


def test_operator_corrections_override_the_model():
    estimate = summarise_lanes([detection(500, 100, confidence=0.3)], WIDTH, HEIGHT)
    corrected = apply_corrections(estimate, {'north': 12})

    lane = corrected['lanes']['north']
    assert lane['vehicles'] == 12
    assert lane['source'] == 'operator'
    assert lane['confidence'] == 1.0
    assert lane['needs_review'] is False
    assert corrected['corrections_applied'] == [{'direction': 'north', 'from': 1, 'to': 12}]


def test_unknown_directions_in_corrections_are_ignored():
    estimate = summarise_lanes([detection(500, 100)], WIDTH, HEIGHT)
    corrected = apply_corrections(estimate, {'upward': 5})
    assert corrected['corrections_applied'] == []


def test_untrusted_estimates_do_not_seed_the_controller():
    engine = MockTrafficEngine()
    engine.reset(seed=5)
    before = len(engine.lanes[('J1', 'north')])

    estimate = summarise_lanes([detection(500, 100, confidence=0.2)], WIDTH, HEIGHT)
    assert estimate['overall_confidence'] < REVIEW_THRESHOLD

    outcome = seed_engine(engine, 'J1', estimate)
    assert outcome['applied'] is False
    assert len(engine.lanes[('J1', 'north')]) == before


def test_a_trusted_estimate_seeds_the_junction():
    engine = MockTrafficEngine()
    engine.reset(seed=5)
    estimate = summarise_lanes([
        detection(500, 100, confidence=0.95),
        detection(500, 900, confidence=0.95),
        detection(100, 500, confidence=0.95),
        detection(900, 500, confidence=0.95),
    ], WIDTH, HEIGHT)
    corrected = apply_corrections(estimate, {'north': 7, 'south': 2, 'east': 3, 'west': 4})

    outcome = seed_engine(engine, 'J1', corrected)
    assert outcome['applied'] is True
    assert len(engine.lanes[('J1', 'north')]) == 7

    junction = next(j for j in engine.snapshot().junctions if j.id == 'J1')
    assert (junction.north, junction.south, junction.east, junction.west) == (7, 2, 3, 4)


def test_forcing_bypasses_the_confidence_gate():
    engine = MockTrafficEngine()
    engine.reset(seed=5)
    estimate = summarise_lanes([detection(500, 100, confidence=0.2)], WIDTH, HEIGHT)

    outcome = seed_engine(engine, 'J1', estimate, force=True)
    assert outcome['applied'] is True
    assert outcome['forced'] is True


def test_seeding_an_unknown_junction_is_rejected():
    engine = MockTrafficEngine()
    engine.reset(seed=5)
    estimate = summarise_lanes([detection(500, 100)], WIDTH, HEIGHT)

    with pytest.raises(ValueError):
        seed_engine(engine, 'J9', estimate, force=True)


def test_mask_regions_cover_all_four_approaches():
    assert set(default_mask()) == {'north', 'south', 'east', 'west'}
