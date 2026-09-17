from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os, re, subprocess, tempfile

app = FastAPI(title='VedASIC Backend', version='0.1.0')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])

class SimulationRequest(BaseModel):
    verilog_code: str
    testbench_code: str

def parse_vcd(path: str):
    if not os.path.exists(path): return None
    signals=[]
    in_header=True
    with open(path,'r',errors='ignore') as f:
        for line in f:
            line=line.strip()
            if line.startswith('$var'):
                p=line.split()
                if len(p)>=5: signals.append(p[4])
            if line.startswith('$enddefinitions'): in_header=False
            if not in_header and line.startswith('#'): break
    return {'signals': list(dict.fromkeys(signals))}

@app.get('/')
def home(): return {'message':'Welcome to VedASIC Backend','status':'online'}

@app.post('/simulate')
def simulate(req: SimulationRequest):
    with tempfile.TemporaryDirectory() as td:
        design=os.path.join(td,'design.v'); tb=os.path.join(td,'tb.v'); out=os.path.join(td,'sim.out')
        with open(design,'w',encoding='utf-8') as f: f.write(req.verilog_code)
        with open(tb,'w',encoding='utf-8') as f: f.write(req.testbench_code)
        c=subprocess.run(['iverilog','-o',out,design,tb],capture_output=True,text=True,timeout=20)
        if c.returncode:
            return {'success':False,'stage':'compilation','error':c.stderr or c.stdout}
        try:
            s=subprocess.run(['vvp',out],cwd=td,capture_output=True,text=True,timeout=20)
        except subprocess.TimeoutExpired:
            return {'success':False,'stage':'simulation','error':'Simulation timed out.'}
        vcd=os.path.join(td,'dump.vcd')
        return {'success':s.returncode==0,'stage':'simulation','output':s.stdout,'error':s.stderr,'waveform':parse_vcd(vcd)}
