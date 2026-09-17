# VedASIC Integrated Prototype

This version keeps the original multi-page website structure and changes its content/theme to VedASIC. The new `studio.html` is the functional prototype: React UI + Monaco editor + Tailwind utility classes + FastAPI + Icarus Verilog.

## 1. Backend
Open PowerShell in this folder:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

If PowerShell blocks activation, run once:
`Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

Keep this terminal running.

## 2. Frontend
In VS Code, install/use Live Server, then right-click `index.html` or `studio.html` and choose **Open with Live Server**. Open the displayed URL. Do not open `studio.html` with `file://` if your browser blocks cross-origin requests.

Click **Launch Studio** → **RUN SIMULATION**.

## 3. Current working flow
React/Monaco → FastAPI → Icarus Verilog → simulation output + VCD signal detection.

## 4. Next engineering layers
1. Docker sandbox for untrusted user code.
2. Full VCD parsing and WaveDrom rendering.
3. Yosys synthesis endpoint.
4. OpenLane + Sky130 flow inside Linux containers.
5. Three.js/WebGL visualization of synthesized/physical-design data.
6. WebSocket streaming for live compiler logs and concurrent job queues.
