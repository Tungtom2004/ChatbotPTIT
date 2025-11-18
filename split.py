import json 
from transformers import pipeline, BlipProcessor, BlipForConditionalGeneration
from transformers import MarianMTModel, MarianTokenizer
from PIL import Image 
import os 
import glob 
import os 
import unicodedata
import uuid 
from pathlib import Path 
import re

folder_path = "D:/ChatBotSlidePTIT/MinerU_out"
parent_out = "data/parent_docs.jsonl"
child_out = "data/child_chunks.jsonl"

chunk_size = 1100
chunk_overlap = 180 
min_section_len = 50 

def summarize_text(text,max_tokens = 100):
    return text or ""

def vn_norm(s):
    if not s:
        return ""
    s = unicodedata.normalize('NFC', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s 

def merge_blocks_lines(block):
    out = []
    for line in block.get("lines",[]):
        for span in line.get("spans",[]):
            t = span.get("content","")
            if t:
                out.append(t)
    return vn_norm(" ".join(out))

def flatten_table(table_obj):
    lines = []
    for row in table_obj.get("cells",[]):
        line = " | ".join((cell.get("content","") for cell in row))
        lines.append(line)
    return "\n".join(lines)

def char_chunks(text,size,overlap):
    text = (text or "").strip()
    if not text:
        return []
    chunks,n,start = [],len(text),0
    while start < n:
        end = min(start+size,n)
        dot = text.rfind('.',start,end)
        if dot != -1 and dot - start > size*0.6:
            end = dot+1 
        chunks.append(text[start:end].strip())
        if end >= n:
            break 
        start = max(0,end - overlap)
    return [c for c in chunks if len(c) > 10]

def process_middle_json(json_path,subject_name):
    with open(json_path,"r",encoding="utf-8") as f:
        data = json.load(f)

    parents = []
    children = []
    buf_text = []
    title_stack = []
    current_section_title = None 

    def flush_section():
        nonlocal buf_text,current_section_title
        text = vn_norm(" ".join(buf_text))
        if len(text) >= min_section_len:
            parent_id = str(uuid.uuid4())
            title_path = " / ".join([t for t in title_stack if t]) or (current_section_title or "Untitled")
            parent_doc = {
                "parent_id": parent_id,
                "subject":subject_name,
                "section": current_section_title or title_path,
                "title_path": title_path,
                "text": text,
                "word_count": len(text.split())
            }
            parents.append(parent_doc)
        
            prefix = f"[{subject_name} / {title_path}]"
            pos = 0 
            for chunk in char_chunks(text,chunk_size,chunk_overlap):
                start = pos 
                pos = start + len(chunk)
                children.append({
                    "parent_id": parent_id,
                    "subject": subject_name,
                    "section": parent_doc["section"],
                    "title_path": title_path,
                    "content": (prefix + " " + chunk).strip(),
                    "order_start": start,
                    "order_end": pos,
                    "word_count": len(chunk.split())
                })
        buf_text = []
    for page in data.get("pdf_info",[]):
        for block in page.get("preproc_blocks",[]):
            btype = block.get("type","")
            if btype == "title":
                flush_section()
                title_text = merge_blocks_lines(block) or block.get("text","") or block.get("raw","")
                current_section_title = vn_norm(title_text) or "Untitled"
                title_stack = [current_section_title]
            
            elif btype == "text":
                t = merge_blocks_lines(block)
                if t:
                    buf_text.append(t)
            
            elif btype == "table":
                table_text = flatten_table(block)
                if table_text.strip():
                    buf_text.append("\n[Table]\n" + table_text.strip() + "\n[/Table]\n")
            
            else:
                pass 
    flush_section()
    return parents,children

def process_folder(folder_path):
    Path(".").mkdir(parents = True, exist_ok=True)
    for outp in [parent_out,child_out]:
        if os.path.exists(outp):
            os.remove(outp)
    
    parent_f = open(parent_out,"a",encoding="utf-8")
    child_f = open(child_out,"a",encoding="utf-8")

    total_parents = total_children = 0 
    for subdir in os.listdir(folder_path):
        subdir = os.path.join(folder_path,subdir)
        if not os.path.isdir(subdir):
            continue 
        middle_files = glob.glob(os.path.join(subdir,"auto","*_middle.json"))
        if not middle_files:
            continue
        for middle_path in middle_files:
            subject_name = os.path.basename(subdir)
            parents,children = process_middle_json(middle_path,subject_name=subject_name)
            for p in parents:
                parent_f.write(json.dumps(p,ensure_ascii=False)+"\n")
            for c in children:
                child_f.write(json.dumps(c,ensure_ascii=False)+"\n")
            total_parents += len(parents)
            total_children += len(children)
    parent_f.close()
    child_f.close()
    print("Ok")

process_folder(folder_path)

