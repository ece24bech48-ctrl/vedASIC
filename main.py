from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import re
import subprocess
import tempfile

app = FastAPI(title="VedASIC Backend", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# REQUEST MODELS
# =========================

class SimulationRequest(BaseModel):
    verilog_code: str
    testbench_code: str


class VerificationRequest(BaseModel):
    verilog_code: str
    testbench_code: str
    expected_output: str | None = None


class SynthesisRequest(BaseModel):
    verilog_code: str
    top_module: str | None = None


# =========================
# TOOL CHECK
# =========================

def check_tool(tool):
    try:
        result = subprocess.run(
            [tool, "-V"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


# =========================
# VCD PARSER
# =========================

def parse_vcd(path):
    if not os.path.exists(path):
        return None

    signals = []
    in_header = True

    with open(path, "r", errors="ignore") as f:
        for line in f:
            line = line.strip()

            if line.startswith("$var"):
                parts = line.split()

                if len(parts) >= 5:
                    signals.append(parts[4])

            if line.startswith("$enddefinitions"):
                in_header = False

            if not in_header and line.startswith("#"):
                break

    return {
        "signals": list(dict.fromkeys(signals))
    }


# =========================
# TOP MODULE DETECTION
# =========================

def detect_top_module(verilog_code):
    match = re.search(
        r"\bmodule\s+([A-Za-z_]\w*)\s*(?:#\s*\(|\()",
        verilog_code
    )

    return match.group(1) if match else None


# =========================
# SIMULATION ENGINE
# =========================

def run_simulation(verilog_code, testbench_code):

    with tempfile.TemporaryDirectory() as td:

        design = os.path.join(td, "design.v")
        tb = os.path.join(td, "tb.v")
        sim_out = os.path.join(td, "sim.out")

        with open(design, "w", encoding="utf-8") as f:
            f.write(verilog_code)

        with open(tb, "w", encoding="utf-8") as f:
            f.write(testbench_code)

        # Compile
        try:
            compile_result = subprocess.run(
                ["iverilog", "-o", sim_out, design, tb],
                capture_output=True,
                text=True,
                timeout=20
            )

        except FileNotFoundError:
            return {
                "success": False,
                "stage": "compilation",
                "error": "Icarus Verilog is not installed or not in PATH."
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "stage": "compilation",
                "error": "Compilation timed out."
            }

        if compile_result.returncode != 0:

            return {
                "success": False,
                "stage": "compilation",
                "output": compile_result.stdout,
                "error": compile_result.stderr or compile_result.stdout,
                "waveform": None
            }

        # Run simulation
        try:
            sim_result = subprocess.run(
                ["vvp", sim_out],
                cwd=td,
                capture_output=True,
                text=True,
                timeout=20
            )

        except FileNotFoundError:
            return {
                "success": False,
                "stage": "simulation",
                "error": "vvp is not installed or not in PATH."
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "stage": "simulation",
                "error": "Simulation timed out."
            }

        vcd = os.path.join(td, "dump.vcd")

        return {
            "success": sim_result.returncode == 0,
            "stage": "simulation",
            "output": sim_result.stdout,
            "error": sim_result.stderr,
            "waveform": parse_vcd(vcd)
        }


# =========================
# HOME
# =========================

@app.get("/")
def home():

    return {
        "message": "Welcome to VedASIC Backend",
        "status": "online",

        "pipeline": [
            "RTL",
            "Simulate",
            "Verify",
            "Synthesize",
            "Physical Design",
            "GDSII"
        ]
    }


# =========================
# HEALTH
# =========================

@app.get("/health")
def health():

    return {
        "status": "online",

        "tools": {
            "iverilog": check_tool("iverilog"),
            "vvp": check_tool("vvp"),
            "yosys": check_tool("yosys")
        }
    }


# =========================
# SIMULATE
# =========================

@app.post("/simulate")
def simulate(req: SimulationRequest):

    return run_simulation(
        req.verilog_code,
        req.testbench_code
    )


# =========================
# VERIFY
# =========================

@app.post("/verify")
def verify(req: VerificationRequest):

    result = run_simulation(
        req.verilog_code,
        req.testbench_code
    )

    if not result["success"]:

        return {
            "success": False,
            "stage": result.get("stage", "verification"),
            "status": "FAIL",
            "output": result.get("output", ""),
            "error": result.get("error", ""),
            "waveform": result.get("waveform")
        }

    output = result.get("output", "")

    # Compare expected output if supplied
    if req.expected_output is not None:

        actual = output.strip()
        expected = req.expected_output.strip()

        passed = actual == expected

        return {
            "success": passed,
            "stage": "verification",
            "status": "PASS" if passed else "FAIL",
            "output": output,
            "expected_output": req.expected_output,
            "error": ""
                if passed
                else "Simulation output does not match expected output.",
            "waveform": result.get("waveform")
        }

    # No expected output supplied
    return {
        "success": True,
        "stage": "verification",
        "status": "PASS",
        "output": output,
        "error": "",
        "waveform": result.get("waveform"),
        "message": "Simulation completed successfully. No expected output was supplied."
    }


# =========================
# SYNTHESIS - YOSYS
# =========================

@app.post("/synthesize")
def synthesize(req: SynthesisRequest):

    top = req.top_module or detect_top_module(req.verilog_code)

    if not top:

        return {
            "success": False,
            "stage": "synthesis",
            "status": "FAIL",
            "error": "Could not detect top module. Please provide top_module."
        }

    if not check_tool("yosys"):

        return {
            "success": False,
            "stage": "synthesis",
            "status": "FAIL",
            "error": "Yosys is not installed or not in PATH."
        }

    with tempfile.TemporaryDirectory() as td:

        design = os.path.join(td, "design.v")
        netlist = os.path.join(td, "synthesized.v")
        script = os.path.join(td, "synth.ys")

        with open(design, "w", encoding="utf-8") as f:
            f.write(req.verilog_code)

        yosys_script = f"""
read_verilog {design}

hierarchy -check -top {top}

proc
opt

fsm
opt

memory
opt

techmap
opt

abc -g simple
opt

write_verilog -noattr {netlist}

stat
"""

        with open(script, "w", encoding="utf-8") as f:
            f.write(yosys_script)

        try:

            result = subprocess.run(
                ["yosys", "-s", script],
                capture_output=True,
                text=True,
                timeout=60
            )

        except subprocess.TimeoutExpired:

            return {
                "success": False,
                "stage": "synthesis",
                "status": "FAIL",
                "error": "Yosys synthesis timed out."
            }

        if result.returncode != 0:

            return {
                "success": False,
                "stage": "synthesis",
                "status": "FAIL",
                "top_module": top,
                "error": result.stderr or result.stdout
            }

        synthesized_netlist = ""

        if os.path.exists(netlist):

            with open(
                netlist,
                "r",
                encoding="utf-8",
                errors="ignore"
            ) as f:

                synthesized_netlist = f.read()

        return {
            "success": True,
            "stage": "synthesis",
            "status": "PASS",
            "top_module": top,
            "netlist": synthesized_netlist,
            "yosys_output": result.stdout,
            "error": result.stderr
        }


# =========================
# PHYSICAL DESIGN
# =========================

@app.post("/physical-design")
def physical_design():

    return {
        "success": False,
        "stage": "physical_design",
        "status": "NOT_IMPLEMENTED",
        "message": "OpenLane/Sky130 integration will be added here."
    }


# =========================
# GDSII
# =========================

@app.post("/gdsii")
def gdsii():

    return {
        "success": False,
        "stage": "gdsii",
        "status": "NOT_IMPLEMENTED",
        "message": "GDSII generation will be enabled after OpenLane/Sky130 integration."
    }
