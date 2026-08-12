from __future__ import annotations

import argparse
import atexit
import csv
import json
import shutil
import subprocess
from collections import Counter, defaultdict
from pathlib import Path


ROOT=Path(__file__).resolve().parent
REQUIRED={"README.txt","pricing_catalog.csv","usage_events.csv","correction_batches.csv"}
def run(command:list[str],stdin:str|None=None)->subprocess.CompletedProcess[str]:
    completed=subprocess.run(command,input=stdin,text=True,capture_output=True,timeout=300)
    if completed.returncode: raise RuntimeError(completed.stdout+completed.stderr)
    return completed
def psql(binary:str,url:str)->list[str]: return [binary,"--dbname",url,"-X","--set","ON_ERROR_STOP=1"]
def read_csv(path:Path)->list[dict[str,str]]:
    with path.open(encoding="utf-8-sig",newline="") as handle:return list(csv.DictReader(handle))
def unique(rows:list[dict[str,str]],key:str,label:str)->None:
    values=[r.get(key,"") for r in rows]
    if not values or any(not v for v in values) or any(n>1 for n in Counter(values).values()): raise ValueError(f"{label}业务键缺失或重复")
def literal(value:object)->str:return "'"+str(value).replace("'","''")+"'"
def scalar(binary:str,url:str,query:str)->str:return run(psql(binary,url)+["--tuples-only","--no-align","--command",query]).stdout.strip()
def export(binary:str,url:str,query:str,path:Path)->None:path.write_text(run(psql(binary,url)+["--quiet","--command",f"COPY ({query}) TO STDOUT WITH(FORMAT CSV,HEADER TRUE)"]).stdout,encoding="utf-8",newline="")


def main()->None:
    parser=argparse.ArgumentParser(); parser.add_argument("--input",required=True); parser.add_argument("--output",required=True); parser.add_argument("--psql",required=True); parser.add_argument("--database-url",required=True); args=parser.parse_args()
    input_root=Path(args.input).resolve(); output=Path(args.output).resolve()
    if output.exists():shutil.rmtree(output)
    complete={"value":False}
    def cleanup()->None:
        if not complete["value"] and output.exists():shutil.rmtree(output)
    atexit.register(cleanup)
    present={p.relative_to(input_root).as_posix() for p in input_root.rglob("*") if p.is_file()}
    if present!=REQUIRED:raise ValueError("交接材料集合发生变化")
    pricing=read_csv(input_root/"pricing_catalog.csv"); events=read_csv(input_root/"usage_events.csv"); corrections=read_csv(input_root/"correction_batches.csv")
    unique(pricing,"sku","价目表"); unique(events,"event_id","事件底账")
    price={r["sku"]:r["unit_price"] for r in pricing}
    if any(r["sku"] not in price for r in events):raise ValueError("事件引用未知SKU")
    allowed={"INSERT","UPDATE","DELETE"}
    if any(r.get("operation") not in allowed for r in corrections):raise ValueError("更正操作无效")
    batch_orders=defaultdict(list)
    for row in corrections: batch_orders[row["batch_id"]].append(int(row["batch_order"]))
    if any(sorted(v)!=list(range(1,len(v)+1)) for v in batch_orders.values()):raise ValueError("批次顺序不连续")
    output.mkdir(parents=True); (output/"sql").mkdir(); (output/"tools").mkdir(); (output/"results").mkdir()
    solution=ROOT/"solution.sql"; shutil.copy2(solution,output/"sql/solution.sql"); shutil.copy2(Path(__file__).resolve(),output/"tools/build_delivery.py")
    statements=["DROP SCHEMA IF EXISTS metering CASCADE;",solution.read_text(encoding="utf-8"),"SELECT set_config('metering.batch_id','INITIAL',false);"]
    values=[]
    for row in events:
        values.append("("+",".join([literal(row["event_id"]),literal(row["account_id"]),literal(row["service_day"])+"::date",literal(row["sku"]),row["quantity"],price[row["sku"]],row["billable"].lower()])+")")
    statements.append("INSERT INTO metering.usage_event VALUES"+",".join(values)+";")
    run(psql(args.psql,args.database_url),"BEGIN;\n"+"\n".join(statements)+"\nCOMMIT;\n")

    seen=set(r["event_id"] for r in events); batch_rows=[]
    for batch_id in dict.fromkeys(r["batch_id"] for r in corrections):
        rows=[r for r in corrections if r["batch_id"]==batch_id]
        counts=Counter(r["operation"] for r in rows); sql=[f"SELECT set_config('metering.batch_id',{literal(batch_id)},false);"]
        inserts=[r for r in rows if r["operation"]=="INSERT"]
        updates=[r for r in rows if r["operation"]=="UPDATE"]
        deletes=[r for r in rows if r["operation"]=="DELETE"]
        if any(r["event_id"] in seen for r in inserts):raise ValueError("补录事件ID已存在")
        if any(r["event_id"] not in seen for r in updates+deletes):raise ValueError("更正引用未知事件")
        if inserts:
            vals=[]
            for r in inserts:
                if r["sku"] not in price:raise ValueError("补录引用未知SKU")
                unit=r["unit_price"] or price[r["sku"]]; vals.append("("+",".join([literal(r["event_id"]),literal(r["account_id"]),literal(r["service_day"])+"::date",literal(r["sku"]),r["quantity"],unit,r["billable"].lower()])+")");seen.add(r["event_id"])
            sql.append("INSERT INTO metering.usage_event VALUES"+",".join(vals)+";")
        if updates:
            vals=[]
            for r in updates:
                if r["sku"] not in price:raise ValueError("更正引用未知SKU")
                unit=r["unit_price"] or price[r["sku"]];vals.append("("+",".join([literal(r["event_id"]),literal(r["account_id"]),literal(r["service_day"])+"::date",literal(r["sku"]),r["quantity"],unit,r["billable"].lower()])+")")
            sql.append("UPDATE metering.usage_event e SET account_id=v.account_id,service_day=v.service_day,sku=v.sku,quantity=v.quantity,unit_price=v.unit_price,billable=v.billable FROM (VALUES"+",".join(vals)+")v(event_id,account_id,service_day,sku,quantity,unit_price,billable) WHERE e.event_id=v.event_id;")
        if deletes:
            sql.append("DELETE FROM metering.usage_event WHERE event_id IN("+",".join(literal(r["event_id"]) for r in deletes)+");")
            for r in deletes:seen.remove(r["event_id"])
        run(psql(args.psql,args.database_url),"BEGIN;\n"+"\n".join(sql)+"\nCOMMIT;\n")
        reconciliation=json.loads(scalar(args.psql,args.database_url,"WITH keys AS (SELECT account_id,service_day,sku FROM metering.daily_charge UNION SELECT account_id,service_day,sku FROM metering.source_rebuild),d AS (SELECT k.*,coalesce(a.quantity,0)-coalesce(s.quantity,0) dq,coalesce(a.amount,0)-coalesce(s.amount,0) da,(a.account_id IS NULL OR s.account_id IS NULL) missing FROM keys k LEFT JOIN metering.daily_charge a USING(account_id,service_day,sku) LEFT JOIN metering.source_rebuild s USING(account_id,service_day,sku)) SELECT json_build_object('missing',count(*) FILTER(WHERE missing),'max_q',coalesce(max(abs(dq)),0),'max_a',coalesce(max(abs(da)),0)) FROM d"))
        status="PASS" if reconciliation=={"missing":0,"max_q":0,"max_a":0} else "HOLD"
        run(psql(args.psql,args.database_url)+["--command","INSERT INTO metering.batch_reconciliation VALUES("+",".join([literal(batch_id),str(reconciliation["missing"]),str(reconciliation["max_q"]),str(reconciliation["max_a"]),literal(status)])+");"])
        batch_rows.append({"batch_id":batch_id,"insert_rows":counts["INSERT"],"update_rows":counts["UPDATE"],"delete_rows":counts["DELETE"],"status":status})
    results=output/"results"
    export(args.psql,args.database_url,"SELECT * FROM metering.daily_charge ORDER BY account_id,service_day,sku",results/"daily_charge.csv")
    export(args.psql,args.database_url,"SELECT * FROM metering.usage_event ORDER BY event_id",results/"usage_event.csv")
    export(args.psql,args.database_url,"SELECT * FROM metering.charge_delta_log ORDER BY batch_id,trigger_op,account_id,service_day,sku",results/"charge_delta_log.csv")
    export(args.psql,args.database_url,"SELECT * FROM metering.batch_reconciliation ORDER BY batch_id",results/"batch_reconciliation.csv")
    with (results/"batch_summary.csv").open("w",encoding="utf-8",newline="") as handle:
        writer=csv.DictWriter(handle,fieldnames=["batch_id","insert_rows","update_rows","delete_rows","status"],lineterminator="\n");writer.writeheader();writer.writerows(batch_rows)
    if any(r["status"]!="PASS" for r in batch_rows):raise ValueError("批次对账未通过")
    (output/"README.txt").write_text("这份材料交给计量运营人员继续账单生成。daily_charge.csv是批次处理后的日费用，usage_event.csv是当前事件底账，batch_summary.csv和charge_delta_log.csv说明每批动作及其净变化。\n\nbatch_reconciliation.csv把日汇总与事件底账重算逐批比较。状态为PASS表示没有缺失汇总键，数量和金额差均为0。sql和tools保存数据库方案与本地处理入口。\n",encoding="utf-8")
    complete["value"]=True


if __name__=="__main__":main()
