"""Mini-MELiSSA MVP
sensors (real or simulated) -> Kalman filter -> simple rules -> Claude (GenAI)
Run:  python app.py   then open http://localhost:5000
"""
import json, os, random, threading, time
from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv()
app = Flask(__name__, static_folder="static", static_url_path="/static")

# ---------- settings (edit these) ----------
MODE = os.getenv("MODE", "sim")                  # "sim" = fake data, "serial" = real ESP32
SERIAL_PORT = os.getenv("SERIAL_PORT", "COM3")   # Windows: COM3, Linux: /dev/ttyUSB0, Mac: /dev/cu.usbserial-xxx
MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
V_CLEAR = 2.5        # turbidity volts in clear water (calibrate this!)
K_BIOMASS = 1.5      # g/L of biomass per volt of drop (calibrate this!)
GROWTH, XMAX = 0.0085, 3.0   # logistic growth per hour and max biomass in g/L (roughly from Fahrion et al. 2023)
TEMP_OK = (30, 36)   # healthy temperature range, deg C
TDS_LOW = 600        # below this, suggest adding nutrient
HARVEST_AT = 2.2     # biomass (g/L) at which we suggest a harvest

state = {"hours": 0, "temp": None, "tds": None, "turb_v": None, "raw": None, "est": None,
         "blackout": False, "fault": False, "mode": MODE}
history, log, cooldown = [], [], {}
sim = {"x": 0.3, "h": 0}


class Kalman:
    """One-state Kalman filter: predicts logistic growth, then corrects with the turbidity reading."""
    def __init__(self, x0):
        self.x, self.p = x0, 0.01

    def step(self, z, dt):
        self.x += GROWTH * self.x * (1 - self.x / XMAX) * dt   # predict
        self.p += 0.002
        k = self.p / (self.p + 0.05 ** 2)                       # correct
        self.x += k * (z - self.x)
        self.p *= 1 - k
        return self.x


def add_log(kind, text):
    log.insert(0, {"hours": round(state["hours"], 1), "kind": kind, "text": text})
    del log[100:]


def check_rules(step, before, raw, est, temp, tds):
    """Very simple rule-based agent. It only recommends; it never controls hardware."""
    def alert(key, kind, text):
        if step - cooldown.get(key, -999) > 30:
            cooldown[key] = step
            add_log(kind, text)

    if temp is not None and not TEMP_OK[0] <= temp <= TEMP_OK[1]:
        alert("temp", "warn", f"Temperature {temp:.1f} C is outside {TEMP_OK[0]}-{TEMP_OK[1]} C.")
    if tds < TDS_LOW:
        alert("tds", "dose", f"TDS is {tds:.0f} ppm (below {TDS_LOW}). Nutrient looks low: consider dosing.")
    if est > HARVEST_AT:
        alert("harvest", "harvest", f"Estimated biomass is {est:.2f} g/L (above {HARVEST_AT}). Consider harvesting.")
    if abs(raw - before) > 0.4:
        alert("jump", "flag", f"Turbidity jumped by {abs(raw - before):.2f} g/L in one step. "
                              "Possible contamination, bubble or sensor fault. Inspect the culture.")


def worker():
    """Reads data forever: fake data in sim mode, the ESP32 in serial mode."""
    kf, step, last, start = None, 0, time.time(), time.time()
    ser = None
    if MODE == "serial":
        import serial
        ser = serial.Serial(SERIAL_PORT, 115200, timeout=5)
    while True:
        if ser:
            parts = ser.readline().decode(errors="ignore").strip().split(",")
            try:
                _, temp, tds, v = [float(p) for p in parts]
            except ValueError:
                continue                      # skip the header line or garbage
            temp = None if temp != temp else temp   # NaN -> None
            now = time.time()
            dt, last, hours = (now - last) / 3600, now, (now - start) / 3600
        else:
            time.sleep(0.5)
            sim["h"] += 2
            sim["x"] += GROWTH * sim["x"] * (1 - sim["x"] / XMAX) * 2
            extra = 0.8 if state["fault"] else 0
            temp = 33 + random.gauss(0, 0.3)
            tds = 1400 - 400 * (sim["x"] - 0.3) + random.gauss(0, 15)
            v = V_CLEAR - (sim["x"] + extra) / K_BIOMASS + random.gauss(0, 0.02)
            dt, hours = 2, sim["h"]
        raw = max(0.0, (V_CLEAR - v) * K_BIOMASS)
        kf = kf or Kalman(raw)
        before = kf.x
        est = kf.step(raw, dt)
        step += 1
        state.update(hours=hours, temp=temp, tds=tds, turb_v=v, raw=raw, est=est)
        history.append({"raw": raw, "est": est})
        del history[:-300]
        check_rules(step, before, raw, est, temp, tds)


# ---------- GenAI: Claude explains and advises, it never controls anything ----------
SYSTEM = ("You are the crew-support assistant for a small Spirulina photobioreactor on a long space mission. "
          "Answer in at most 3 short, plain sentences using only the data given. "
          "A rule engine watches the sensors; you explain and advise. Never claim you changed anything.")


def ask_claude(question):
    if state["blackout"]:
        return "Ground link is down, so the AI assistant is unavailable. The onboard rules keep running; see the alert log."
    if not os.getenv("ANTHROPIC_API_KEY"):
        return "No API key found. Add ANTHROPIC_API_KEY to your .env file to turn on the AI assistant."
    try:
        from anthropic import Anthropic
        context = {k: state[k] for k in ("hours", "temp", "tds", "turb_v", "raw", "est")}
        prompt = f"STATE: {json.dumps(context)}\nRECENT ALERTS: {json.dumps(log[:8])}\nQUESTION: {question}"
        r = Anthropic().messages.create(model=MODEL, max_tokens=300, system=SYSTEM,
                                        messages=[{"role": "user", "content": prompt}])
        return r.content[0].text
    except Exception as e:
        return f"AI assistant error: {e}"


# ---------- web server ----------
@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/api/state")
def get_state():
    return jsonify(state=state, history=history, log=log[:15])


@app.route("/api/ask", methods=["POST"])
def ask():
    question = (request.get_json(silent=True) or {}).get("question", "").strip()
    return jsonify(answer=ask_claude(question or "Summarize the culture status."))


@app.route("/api/blackout", methods=["POST"])
def blackout():
    state["blackout"] = not state["blackout"]
    add_log("info", "Ground link lost. Rules only." if state["blackout"] else "Ground link restored.")
    return jsonify(blackout=state["blackout"])


@app.route("/api/fault", methods=["POST"])
def fault():
    if MODE == "sim":
        state["fault"] = not state["fault"]
    return jsonify(fault=state["fault"])


if __name__ == "__main__":
    threading.Thread(target=worker, daemon=True).start()
    app.run(port=5000)
