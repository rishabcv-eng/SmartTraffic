# Architecture

SmartTraffic separates sensing, control logic, and simulation so demo inputs can evolve independently.

## Core contracts

- `TrafficEngine`: reset, step, inject.
- `Controller`: convert a `NetworkSnapshot` into signal phase choices.
- `NetworkSnapshot`: common state representation used by mock, SUMO, and future CV/map ingestion.

This prevents CV, SUMO, and UI experiments from being coupled to one algorithm.

## Target architecture

`CCTV/image upload -> vehicle/queue extraction -> map matching -> network state -> short-horizon prediction -> coordinated controller -> SUMO replay -> web visualization`.

The image upload is an initialization/observation source, not the physics engine. SUMO is used to animate consequences and produce comparable metrics.
