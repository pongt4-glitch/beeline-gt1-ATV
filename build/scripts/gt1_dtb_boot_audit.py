#!/usr/bin/env python3
"""Compare boot-critical DTB properties without raw phandle/addr-cell false positives.

Read-only: no DTB mutation, flashing or device operations. Does not print
device-specific boot arguments, addresses or serial numbers.
"""
from __future__ import annotations
import argparse
import json
import struct
from pathlib import Path

MAGIC = 0xD00DFEED
BEGIN, END_NODE, PROP, NOP, END = 1, 2, 3, 4, 9

def u32(data):
    if len(data) != 4:
        raise ValueError(f"Expected four bytes, got {len(data)}")
    return struct.unpack(">I", data)[0]

def words(data):
    if len(data) % 4:
        raise ValueError("Non-cell-aligned binary data")
    return struct.unpack(f">{len(data)//4}I", data)

def parse(path):
    data = Path(path).read_bytes()
    if len(data) < 40:
        raise ValueError(f"Truncated DTB {path}")
    magic, size, off_struct, off_strings, _, _, _, _, str_size, struct_size = struct.unpack_from(">10I",data)
    if magic != MAGIC or size > len(data):
        raise ValueError(f"Invalid DTB: {path}")
    if off_struct+struct_size > size or off_strings+str_size > size:
        raise ValueError("DTB section outside total size")
    strings = data[off_strings:off_strings+str_size]
    pos = off_struct
    limit = off_struct+struct_size
    stack = []
    nodes = {}
    while pos < limit:
        token = u32(data[pos:pos+4]); pos += 4
        if token == BEGIN:
            end = data.index(bytes([0]),pos,limit)
            name = data[pos:end].decode()
            pos = (end+4)&~3
            stack.append(name)
            nodes["/"+"/".join(v for v in stack if v)] = {}
        elif token == END_NODE:
            stack.pop()
        elif token == PROP:
            length, off = struct.unpack_from(">II",data,pos); pos += 8
            if off >= len(strings) or pos+length > limit:
                raise ValueError("Malformed DTB property")
            e = strings.index(bytes([0]),off)
            key = strings[off:e].decode()
            path_key = "/"+"/".join(v for v in stack if v)
            nodes[path_key][key] = data[pos:pos+length]
            pos = (pos+length+3)&~3
        elif token == NOP:
            pass
        elif token == END:
            break
        else:
            raise ValueError(f"Unknown DTB token {token}")
    phandles = {}
    for path_key,props in nodes.items():
        for tag in ("phandle","linux,phandle"):
            if len(props.get(tag,b""))==4:
                phandles[u32(props[tag])] = path_key
    return nodes,phandles

def cells(props,name,default):
    return u32(props[name]) if name in props else default

def reg_intervals(nodes,node,prop="reg"):
    b=nodes[node].get(prop)
    if b is None:return None
    parent=node.rsplit("/",1)[0] or "/"
    pp=nodes[parent]
    ac=cells(pp,"#address-cells",2)
    sc=cells(pp,"#size-cells",1)
    if ac+sc == 0 or len(b)%(4*(ac+sc)):
        return {"error":"unexpected reg cell count"}
    raw=words(b)
    ranges=[]
    for n in range(0,len(raw),ac+sc):
        addr=0; size=0
        for cell in raw[n:n+ac]:addr=(addr<<32)|cell
        for cell in raw[n+ac:n+ac+sc]:size=(size<<32)|cell
        ranges.append([addr,size])
    return ranges

def referenced(nodes,ph,node,prop):
    value=nodes.get(node,{}).get(prop)
    if value is None:return None
    return [ph.get(x,f"UNKNOWN-PHANDLE({x})") for x in words(value)]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("stock")
    ap.add_argument("candidate")
    ap.add_argument("--json-output",type=Path)
    ap.add_argument("--live-memory-dtb",type=Path,
                    help="Live DTB captured after bootloader injected memory/chosen nodes")
    ap.add_argument("--require-memory-match",action="store_true")
    a=ap.parse_args()
    sn,sp=parse(a.stock)
    cn,cp=parse(a.candidate)
    mn,_=parse(a.live_memory_dtb) if a.live_memory_dtb else (sn,sp)
    checks={}
    def record(name,actual,expected):
        checks[name]={"match":actual==expected,"stock":expected,"candidate":actual}
    common={
        "emmc":"/emmc@d0074000",
        "sdio":"/sdio@d0070000",
        "sd":"/sd@d0072000",
        "ethernet":"/ethernet@0xc9410000",
        "ramoops":"/reserved-memory/ramoops@0x07400000",
    }
    for label,path in common.items():
        record(label+"_reg",reg_intervals(cn,path),reg_intervals(sn,path))
    for label,path in common.items():
        record(label+"_compatible",
            cn.get(path,{}).get("compatible",b"").hex(),
            sn.get(path,{}).get("compatible",b"").hex())
    for label,path in (("emmc","/emmc@d0074000"),("sdio","/sdio@d0070000"),("sd","/sd@d0072000")):
        for p in ("interrupts","bus-width","status"):
            record(label+"_"+p,cn.get(path,{}).get(p),sn.get(path,{}).get(p))
    for key in ("compatible","status","power_on_pin","interrupt_pin"):
        record("wifi_"+key,cn.get("/wifi",{}).get(key),sn.get("/wifi",{}).get(key))
    record("ethernet_pinctrl",referenced(cn,cp,"/ethernet@0xc9410000","pinctrl-0"),
           referenced(sn,sp,"/ethernet@0xc9410000","pinctrl-0"))
    for i in range(17):
        record(f"partition_{i}",referenced(cn,cp,"/partitions",f"part-{i}"),
               referenced(sn,sp,"/partitions",f"part-{i}"))
    mem_node=next((p for p in ("/memory", "/memory@00000000") if p in mn),None)
    sr=reg_intervals(mn,mem_node) if mem_node and "reg" in mn[mem_node] else (
        reg_intervals(mn,mem_node,"linux,usable-memory") if mem_node else None)
    cr=reg_intervals(cn,"/memory@00000000","linux,usable-memory")
    memory_match=(sr==cr)
    failed=[k for k,v in checks.items() if not v["match"]]
    result={
        "stock_node_count":len(sn),"candidate_node_count":len(cn),
        "checked_invariants":len(checks),"failed_invariants":failed,
        "memory":{"stock_ranges":sr,"source":"live" if a.live_memory_dtb else "stock_boot", "candidate_usable_ranges":cr,"same":memory_match,
                  "risk":"requires explicit boot memory map review" if not memory_match else "ranges agree"},
        "root_cells":{"stock":[cells(sn["/"],"#address-cells",2),cells(sn["/"],"#size-cells",1)],
                      "candidate":[cells(cn["/"],"#address-cells",2),cells(cn["/"],"#size-cells",1)]},
        "boot_chosen":{"stock":"/chosen" in sn,"candidate":"/chosen" in cn},
    }
    if a.json_output:
        a.json_output.parent.mkdir(parents=True,exist_ok=True)
        a.json_output.write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
    if failed:
        raise SystemExit(1)
    if a.require_memory_match and not memory_match:
        raise SystemExit(2)

if __name__=="__main__":
    main()
