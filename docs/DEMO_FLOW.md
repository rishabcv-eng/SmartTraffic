# Demo Flow

## Judge sequence
1. Open the SmartTraffic control room.
2. Start the deterministic `accident` comparison: fixed-time vs predictive-pressure-v1.
3. Show current congestion and +15-step forecast.
4. Replay both controllers from the same seed and event tick.
5. Inject an emergency vehicle and request `/api/emergency/corridor` for a route such as `J1 -> J2 -> J4`.
6. Show the moving green-wave schedule and post-pass recovery.
7. Upload a traffic image to `/api/vision/analyse`. If local YOLO weights are installed, detections are returned; otherwise the API clearly reports that the CV runtime is unavailable instead of fabricating detections.
8. Switch `SMARTTRAFFIC_ENGINE=sumo` on a SUMO-equipped machine to run the same controller interface against TraCI.

## What is validated now
- deterministic mock traffic propagation
- fixed-time / max-pressure / predictive-pressure controller comparison
- reproducible replay from identical initial state
- congestion forecast API
- accident, demand-surge and emergency scenario hooks
- emergency corridor scheduling
- image upload API with explicit optional YOLO runtime

## What must be validated on the demo machine
- actual SUMO execution and TraCI timing
- imported OpenStreetMap corridor topology
- YOLO weight file and test-image accuracy
- multi-seed SUMO benchmark report

Never present mock-engine performance numbers as real-world improvement claims. Use the mock engine for UI/controller development and SUMO for final benchmark evidence.
