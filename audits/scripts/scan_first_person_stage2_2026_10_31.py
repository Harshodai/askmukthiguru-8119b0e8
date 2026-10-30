import json,re,sys,collections,hashlib,urllib.request as u
sys.path.insert(0,".")
from ingest.verbatim.boundaries import boundary_defects
from ingest.verbatim.gates import script_and_loop_problem
from ingest.verbatim.asr_cleaner import asr_cleaner_flags
def scroll(c):
    out=[];off=None
    while True:
        b={"limit":500,"with_payload":True,"with_vector":False}
        if off: b["offset"]=off
        r=json.loads(u.urlopen(u.Request(f"http://localhost:6333/collections/{c}/points/scroll",json.dumps(b).encode(),{"Content-Type":"application/json"})).read())["result"]
        out+=[p["payload"] for p in r["points"]]; off=r.get("next_page_offset")
        if off is None: return out
S=[p for p in scroll("first_person_v10_stage2_20261031") if p.get("record_type")=="retrieval_child"]
V=[p for p in scroll("first_person_v10") if p.get("record_type")=="retrieval_child"]
norm=lambda t:re.sub(r"[^a-z0-9 ]","",t.lower()).split()
print("stage2 children",len(S),"v10 children",len(V))
wc=[len(norm(p["verbatim_text"])) for p in S]; dur=[(p["end_ms"]-p["start_ms"])/1000 for p in S]
print("words min/med/max",min(wc),sorted(wc)[len(wc)//2],max(wc),"| dur s min/med/max",min(dur),sorted(dur)[len(dur)//2],max(dur))
print("<15 words:",sum(w<15 for w in wc),"dur>90s:",sum(d>90 for d in dur),"dur<8s:",sum(d<8 for d in dur))
iss=collections.Counter()
for p in S:
    t=p["verbatim_text"]
    if boundary_defects(t.split()): iss["boundary_defect"]+=1
    if script_and_loop_problem(t): iss["script_or_loop"]+=1
    if asr_cleaner_flags(t): iss["asr_cleaner_flag"]+=1
    if re.search(r"[^\x00-\x7f]",t): iss["non_ascii"]+=1
    if hashlib.sha256(t.encode()).hexdigest()!=p.get("source_text_hash") and p.get("transcript_hash")!=hashlib.sha256(t.encode()).hexdigest(): iss["hash_not_sha256_of_text(informational)"]+=1
    if p["foreign_window_count"] and p["window_count"] and p["foreign_window_count"]/p["window_count"]>0.5: iss["majority_foreign_windows"]+=1
print("issues",dict(iss))
print("speaker_verified:",collections.Counter(p["speaker_verified"] for p in S))
byv=collections.defaultdict(lambda:[0,0,0])
for p in S: x=byv[p["video_id"]]; x[0]+=1; x[1]+=bool(p["speaker_verified"]); x[2]+=p["rights_cleared"] is True
print("per video (n,verified,rights):",{k:tuple(v) for k,v in sorted(byv.items())})
print("guru:",collections.Counter(p["guru_id"] for p in S))
# duplicates
seen=collections.defaultdict(list)
for p in S: seen[" ".join(norm(p["verbatim_text"]))].append(p["video_id"])
print("exact dup within stage2:",sum(len(v)>1 for v in seen.values()))
vkeys={" ".join(norm(p["verbatim_text"])) for p in V}
ex=[p["video_id"] for p in S if " ".join(norm(p["verbatim_text"])) in vkeys]
print("exact dup vs live v10:",len(ex),collections.Counter(ex))
def grams(t,n=8):
    w=norm(t); return {" ".join(w[i:i+n]) for i in range(max(0,len(w)-n+1))}
vg=set()
for p in V: vg|=grams(p["verbatim_text"])
near=collections.Counter()
for p in S:
    g=grams(p["verbatim_text"])
    if g and len(g&vg)/len(g)>=0.6: near[p["video_id"]]+=1
print("near-dup (>=60% 8-grams in v10):",sum(near.values()),dict(near))
print("---- details")
for p in S:
    t=p["verbatim_text"]; bd=boundary_defects(t.split())
    fw=p["foreign_window_count"] and p["window_count"] and p["foreign_window_count"]/p["window_count"]>0.5
    if bd or fw or len(norm(t))<15:
        print(p["video_id"],p["start_ms"]//1000,"bd=",bd,"foreign=%s/%s"%(p["foreign_window_count"],p["window_count"]),"verified=",p["speaker_verified"],"|",t[:90].replace("\n"," "),"...",t[-50:])
print("---- status")
print(collections.Counter((p["boundary_status"],p["completeness_status"],p["quality_status"]) for p in S))
print("head_fragment spans:",[(p["video_id"],p["boundary_status"],p["completeness_status"],p["quality_status"],p["speaker_verified"]) for p in S if boundary_defects(p["verbatim_text"].split())])
print("verified & clean(no bd, >=15w, <=90s, foreign<=50%):",sum(1 for p in S if p["speaker_verified"] and not boundary_defects(p["verbatim_text"].split()) and len(norm(p["verbatim_text"]))>=15 and (p["end_ms"]-p["start_ms"])<=90000 and not (p["window_count"] and p["foreign_window_count"]/p["window_count"]>0.5)))
