import json 

with open("data/child_chunks.jsonl","r",encoding = "utf-8") as f:
    for line in f:
        obj = json.loads(line)
        if "subject" in obj:
            obj["subject"] = obj["subject"].lower()
        f.write(json.dumps(obj,ensure_ascii=False) + "\n")