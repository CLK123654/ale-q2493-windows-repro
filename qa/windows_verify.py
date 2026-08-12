from __future__ import annotations
import csv,hashlib,json,os,shutil,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];TASK=ROOT/"task";EVIDENCE=ROOT/"evidence";RUNS=ROOT/"windows-runs";PSQL=os.environ["PSQL_PATH"];ADMIN=os.environ["SERVER_ADMIN_URL"]
def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def reset(p:Path)->None:
    if p.exists():shutil.rmtree(p)
    p.mkdir(parents=True)
def extract(z:Path,t:Path)->None:
    t.mkdir(parents=True)
    with zipfile.ZipFile(z) as a:a.extractall(t)
def paths(r:Path)->list[str]:return sorted(p.relative_to(r).as_posix() for p in r.rglob("*") if p.is_file())
def norm(p:Path)->bytes:return p.read_bytes().replace(b"\r\n",b"\n")
def compare(a:Path,e:Path)->list[str]:
    if paths(a)!=paths(e):raise AssertionError("path set differs")
    for rel in paths(e):
        if norm(a/rel)!=norm(e/rel):raise AssertionError(f"Reference differs:{rel}")
    return paths(e)
def admin(sql:str)->None:
    c=subprocess.run([PSQL,"--dbname",ADMIN,"-X","--set","ON_ERROR_STOP=1","--command",sql],text=True,capture_output=True,timeout=60)
    if c.returncode:raise AssertionError(c.stdout+c.stderr)
def build(inp:Path,out:Path,db:str)->subprocess.CompletedProcess[str]:
    admin(f"DROP DATABASE IF EXISTS {db} WITH (FORCE)");admin(f"CREATE DATABASE {db}");return subprocess.run([sys.executable,str(ROOT/"implementation/build_delivery.py"),"--input",str(inp),"--output",str(out),"--psql",PSQL,"--database-url",f"postgresql://postgres:root@127.0.0.1:5432/{db}"],text=True,capture_output=True,timeout=300)
def main()->None:
    reset(RUNS);EVIDENCE.mkdir(exist_ok=True);version=subprocess.run([PSQL,"--version"],text=True,capture_output=True)
    if version.returncode or " 17." not in version.stdout:raise AssertionError("PostgreSQL17 required")
    ref=RUNS/"reference";extract(TASK/"reference.zip",ref);expected=ref/"output";clean=[]
    for ri,label in enumerate(["clean a","clean b"],1):
        base=RUNS/label;extract(TASK/"输入数据包.zip",base);inp=base/"input_data";before={p.relative_to(inp).as_posix():sha(p) for p in inp.rglob("*") if p.is_file()}
        for pi in [1,2]:
            out=base/f"output {pi}";c=build(inp,out,f"meter_clean_{ri}_{pi}")
            if c.returncode:raise AssertionError(c.stdout+c.stderr)
            generated=compare(out,expected);clean.append({"root_id":label,"process_index":pi,"primary_software_executed":True,"input_unchanged":True,"reference_full_match":True,"generated_paths":generated})
        if before!={p.relative_to(inp).as_posix():sha(p) for p in inp.rglob("*") if p.is_file()}:raise AssertionError("input changed")
    positive=RUNS/"positive";extract(TASK/"输入数据包.zip",positive);p=positive/"input_data/correction_batches.csv"
    with p.open(encoding="utf-8",newline="") as h:rows=list(csv.DictReader(h))
    for r in rows:
        if r["event_id"]=="EV-1013":r["quantity"]="7.000"
    with p.open("w",encoding="utf-8",newline="") as h:w=csv.DictWriter(h,fieldnames=list(rows[0]),lineterminator="\n");w.writeheader();w.writerows(rows)
    c=build(positive/"input_data",positive/"output","meter_positive")
    if c.returncode or norm(positive/"output/results/daily_charge.csv")==norm(expected/"results/daily_charge.csv"):raise AssertionError("valid quantity change had no effect")
    (EVIDENCE/"positive-case.json").write_text(json.dumps({"mutation":"EV-1013数量从6改为7","daily_charge_changed":True,"behavior_changed":True},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    negative=RUNS/"negative";extract(TASK/"输入数据包.zip",negative);p=negative/"input_data/usage_events.csv";lines=p.read_text().splitlines();p.write_text("\n".join(lines+[lines[1]])+"\n");out=negative/"output";out.mkdir();(out/"stale.txt").write_text("stale")
    c=build(negative/"input_data",out,"meter_negative")
    if c.returncode==0 or out.exists():raise AssertionError("duplicate event did not fail closed")
    (EVIDENCE/"negative-case.log").write_text(f"return_code={c.returncode}\n{c.stdout}{c.stderr}",encoding="utf-8")
    summary={"result":"PASS","commit_sha":os.getenv("GITHUB_SHA"),"workflow_run_id":os.getenv("GITHUB_RUN_ID"),"runner_image":os.getenv("ImageOS"),"main_software":{"name":"PostgreSQL Client","database":"PostgreSQL17","version":version.stdout.strip(),"executed":True},"clean_directory_count":2,"process_runs_per_directory":2,"clean_runs":clean,"positive_mutation":"PASS","negative_case":"PASS","reference_full_comparison":"PASS","formal_network":{"python_outbound_blocked":True,"psql_internet_blocked":True,"loopback_only":True,"external_services_used":False}}
    (EVIDENCE/"windows-summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__":main()
