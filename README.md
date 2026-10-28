# Mini-MELiSSA photobioreactor (MVP)

A tiny Spirulina photobioreactor monitor inspired by ESA's MELiSSA life-support loop.
It reads temperature, TDS (nutrient proxy) and turbidity (biomass proxy), estimates biomass
with a Kalman filter, raises simple rule-based alerts, and has a **Claude AI crew assistant**
that explains the situation. It works with **simulated data** (no hardware) or a real **ESP32**.

```
ESP32 sensors (or simulator) -> Kalman filter -> rules (alerts) -> Claude (explains / advises)
                                         \-> web dashboard
```

The AI never controls hardware. It only explains and advises. During a simulated comms
blackout it is switched off and the rules keep running.

## Run it (no hardware needed)
1. Install Python 3.10+.
2. In this folder:
   ```
   pip install -r requirements.txt
   cp .env.example .env        # Windows: copy .env.example .env
   ```
3. Open `.env` and paste your Anthropic API key (get one at console.anthropic.com). Without a key everything works except the AI assistant.
4. `python app.py`, then open http://localhost:5000

Try: wait for the harvest alert, click **Simulate contamination**, click **Toggle comms blackout**, then ask the assistant a question.

## Use the real sensors
1. Wire the sensors and flash `firmware/sensors/sensors.ino` with Arduino IDE (pins D4 temperature, D34 TDS, D35 turbidity).
2. In `.env` set `MODE=serial` and `SERIAL_PORT` (see Arduino IDE > Tools > Port). Close the Serial Monitor first.
3. Calibrate in `app.py`: put the turbidity sensor in clear water and set `V_CLEAR` to its voltage. Then compare against dry-weight or OD measurements to set `K_BIOMASS`.

## Push to GitHub
```
git init
git add .
git commit -m "Mini-MELiSSA MVP"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/mini-melissa.git
git push -u origin main
```
`.env` is in `.gitignore`, so your API key stays private.

## Notes
- Growth parameters are roughly from Fahrion et al. 2023 (*Limnospira indica* PCC8005 batch cultures, 36-75 umol photons m-2 s-1, about 30-34 C).
- This is a first-level MVP: one-state filter, simple rules, advisory only. Next steps: a full two-state EKF, MPC harvest planning, pH sensor, actuators with guardrails.
