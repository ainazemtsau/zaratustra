"""Read-only synthetic E1 evidence observer. Run only after all producers settle."""
from pathlib import Path
from decimal import Decimal
import json, hashlib, sys
r=Path(sys.argv[1]); results=[]
def lines(p): return [json.loads(s) for s in p.read_text(encoding="utf-8").splitlines() if s.strip()]
def load_rows(summary,table): return [json.loads(row["json"]) for row in summary["database"][table]]
previous=None
attempts=json.loads((r/"attempts.json").read_text(encoding="utf-8"))["attempts"]
ordered=[a for a in attempts if a.get("summary","").startswith("qualified-live/")]
for attempt in ordered:
 d=r/Path(attempt["summary"]).parent
 if not (d/"summary.json").exists(): continue
 s=json.loads((d/"summary.json").read_text(encoding="utf-8")); events=lines(d/"events.jsonl"); requests=lines(d/"requests.jsonl"); identity=lines(d/"identity.jsonl")[0]; startup=lines(d/"startup.jsonl")[0]
 assert s["settled"] and s["permanent_snapshot_count"]==0
 assert startup["messages_before_prompt"]==[]
 assert identity["provider"]=="openai-codex" and identity["model"]=="gpt-6.1-sol" and identity["thinking"]=="medium"
 assert identity["os_cwd"]==identity["sdk_cwd"]
 assert all(len(q["snapshots"])==1 and q["bootstrap_occurrences"]==1 for q in requests)
 assert all(any("zaratustra" in sections for sections in q["system_sections"]) for q in requests)
 primary=load_rows(s,"records");support=load_rows(s,"experience_rows"); evidence={row["id"]:row for row in primary if row["kind"]=="evidence"}
 ends={e["toolCallId"]:e for e in events if e["type"]=="tool_execution_end"}
 observations=[]
 for row in evidence.values():
  p=row["data"].get("provenance",{});ob=p.get("observation")
  if ob and ob["tool_call_id"] in ends:
   end=ends[ob["tool_call_id"]]
   raw=json.dumps(end["result"]["content"],ensure_ascii=False,separators=(",",":"))
   assert hashlib.sha256(raw.encode()).hexdigest()==ob["full_content_hash"]
   observations.append({"ref":{"id":row["id"],"revision":row["revision"]},"tool":ob["tool_name"],"call_id":ob["tool_call_id"],"is_error":ob["is_error"],"digest_matches_actual_event":True})
 calls=[{"name":e["toolName"],"args":e.get("args"),"event_index":i} for i,e in enumerate(events) if e["type"]=="tool_execution_start"]
 errors=[{"name":e["toolName"],"result":e.get("result")} for e in events if e["type"]=="tool_execution_end" and e.get("isError")]
 row={"candidate":attempt["candidate"],"scenario":d.name,"identity":identity,"startup_empty":True,"settled":True,"permanent_snapshot_count":0,"requests":len(lines(d/"provider-requests.jsonl")),"actual_calls":calls,"tool_errors":errors,"actual_retained_observations":observations,"methods":[v for v in primary if v["kind"]=="method"],"runs":[v for v in primary if v["kind"]=="run"],"invocations":[v for v in support if v["kind"]=="invocation"],"evaluations":[v for v in support if v["kind"]=="evaluation"],"signals":[v for v in support if v["kind"]=="signal"],"reviews":[v for v in support if v["kind"]=="signal_review"],"results":[v for v in primary if v["kind"]=="evidence" and v["data"].get("source_kind")=="generated_artifact"],"response":s["response"],"max_snapshot_bytes":max(len(q["snapshots"][0]["content"].encode()) for q in requests)}
 if previous: assert identity["pid"]!=previous["identity"]["pid"] and identity["sdk_cwd"]!=previous["identity"]["sdk_cwd"]
 results.append(row);previous=row
computed={}
for filename in ["alpha.txt","beta.txt","gamma.txt","delta-incomplete.txt","epsilon.txt","zeta.txt"]:
 raw=(r/"inputs"/filename).read_bytes();text=raw.decode("utf-8");all_lines=text.splitlines();start=next(i for i,line in enumerate(all_lines) if line.startswith("Code |"))+1
 rows=[];pieces=0;known=Decimal(0);unknown=False
 for line in all_lines[start:]:
  if not line.strip():continue
  cells=[c.strip() for c in line.split("|")];q=int(cells[2]);pieces+=q;unit=cells[4] if len(cells)>4 else "g"
  if cells[3]=="unknown" or unit=="unknown":mass=None;unknown=True
  else:
   factor={"g":Decimal(1),"mg":Decimal("0.001")}[unit];mass=Decimal(cells[3])*q*factor;known+=mass
  rows.append({"code":cells[0],"pieces":q,"source_unit_mass":cells[3],"source_unit":unit,"row_mass_g":str(mass) if mass is not None else None})
 computed[filename]={"source_sha256":hashlib.sha256(raw).hexdigest(),"rows":rows,"pieces":pieces,"known_mass_g":str(known),"full_mass_g":None if unknown else str(known)}
assert computed["alpha.txt"]["full_mass_g"]=="93.0"
assert Decimal(computed["beta.txt"]["full_mass_g"])==Decimal("88")
assert Decimal(computed["gamma.txt"]["full_mass_g"])==Decimal("4.9")
assert computed["delta-incomplete.txt"]["full_mass_g"] is None and Decimal(computed["delta-incomplete.txt"]["known_mass_g"])==Decimal("12")
assert Decimal(computed["epsilon.txt"]["full_mass_g"])==Decimal("3.375")
assert Decimal(computed["zeta.txt"]["full_mass_g"])==Decimal("3.8")
out={"layer":"L evidence inspection + deterministic arithmetic observations","candidates":list(dict.fromkeys(a["candidate"] for a in ordered)),"final_code_candidate":"6659f4c4d9de1871624efaec37933aa8d03dc0bf","scope":"Synthetic model conversations; never Anton/owner acceptance/T31; repeated candidate fixtures are not independent successful cases.","scenarios":results,"computed_from_original_inputs":computed,"expected_arithmetic":{"alpha":{"pieces":12,"mass_g":"93"},"beta":{"pieces":12,"mass_g":"88"},"gamma":{"pieces":8,"mass_g":"4.9"},"delta":{"known_mass_g":"12","total_mass":"unknown","total_pieces":9}},"arithmetic_basis":"Independently calculated from the six original fixtures; compare with retained actual tool/output rows."}
(r/"live-verification.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"scenarios":len(results),"requests":sum(s["requests"] for s in results),"errors":sum(len(s["tool_errors"]) for s in results)},indent=2))
