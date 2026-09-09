# Hardware in the loop

A physical model junction whose LEDs change because the controller decided they
should. The board is a dumb display: it holds no timing logic, it just mirrors
whatever `/api/hil/state` reports, and fails safe when it cannot reach the
backend.

## Why bother

Charts are easy to disbelieve. A foam-board junction with real signal heads
changing in front of a judge is not — and because the board is driven by the
same decisions the benchmark measures, it is a demonstration rather than a prop.

## Wire format

`GET /api/hil/state?format=wire` returns a single ASCII line, deliberately so a
microcontroller can parse it with `strtok` and no JSON library:

```
T42|J1:GRR|J2:RGR|J3:RRA|J4:GRR
```

- `T42` — simulation tick.
- Each `Jn:XYZ` — aspects for that junction: **NS, EW, PED**, in that order.
- Aspect codes: `G` green, `A` amber, `R` red.

`GET /api/hil/state` (no `format`) returns the same thing as JSON, with queue
lengths, pedestrian counts and the junction's operating mode.

Amber is inserted by the backend, not the board: when a junction changes phase,
the movement losing right of way shows amber for one tick before the new green.

## Bill of materials

| Part | Qty | Notes |
| --- | --- | --- |
| ESP32 DevKit v1 | 1 | Any ESP32 with WiFi |
| 5 mm LEDs, red / amber / green | 7 per junction | NS×3, EW×3, pedestrian×1 |
| 220 Ω resistors | 7 per junction | One per LED |
| Breadboard + jumpers | — | |
| 74HC595 shift register | 2 | Only if driving all four junctions |

## Wiring

Each junction head uses seven pins, defined in the `heads[]` table in
`esp32_signal_head/esp32_signal_head.ino`:

| Junction | NS G / A / R | EW G / A / R | PED G |
| --- | --- | --- | --- |
| J1 | 13 / 12 / 14 | 27 / 26 / 25 | 33 |
| J2 | 32 / 15 / 2 | 4 / 16 / 17 | 5 |

Each LED goes GPIO → 220 Ω → LED anode, cathode → GND.

**Two important constraints:**

- **GPIO 34–39 are input-only on the ESP32** and cannot drive an LED. Do not
  extend the table into that range.
- **A bare ESP32 has enough usable output pins for two full heads.** Four
  junctions needs 28 outputs. To build all four, chain two 74HC595 shift
  registers and replace `setPin()` with a shift-out; the rest of the sketch is
  unchanged.

## Flashing

1. Arduino IDE → Boards Manager → install **esp32 by Espressif**.
2. Select *ESP32 Dev Module*.
3. Open `esp32_signal_head/esp32_signal_head.ino`.
4. Set `WIFI_SSID`, `WIFI_PASSWORD`, and `API_URL` to the LAN address of the
   machine running `uvicorn` — `http://<host-ip>:8000/api/hil/state?format=wire`.
   `localhost` will not work; the board is a separate device.
5. Upload, then open Serial Monitor at 115200 to watch the wire lines arrive.

## Fail-safe behaviour

If the backend does not answer for 3 seconds, the board stops trusting its last
instruction and flashes amber on every head with all reds lit. This mirrors what
a real controller cabinet does on a comms failure, and it means a crashed laptop
during a demo produces correct-looking degraded behaviour rather than a junction
frozen on green.

The same fail-safe applies per junction from the backend side: a junction with
an injected `signal-fault` reports code `RRR` and never shows green.

## Running the demo

```bash
# terminal 1
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000
# terminal 2
curl 'localhost:8000/api/run' -X POST
```

`--host 0.0.0.0` matters: the default binds to localhost only and the board
will not be able to reach it.
