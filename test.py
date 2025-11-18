import os 
import unicodedata
import re
import chromadb 
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from embeddings import get_embedding
from langchain_openai import AzureChatOpenAI
from dotenv import load_dotenv
from langchain.schema import HumanMessage, SystemMessage
from dataclasses import dataclass
import regex as re2
import json 
import numpy as np 
load_dotenv()
db_path = ".chroma_db"
collection = "ptit_giaotrinh_2"
embedder = get_embedding()
fetch_k = 30
top_k = 10
client = chromadb.PersistentClient(path=db_path, settings=Settings(anonymized_telemetry=False))
collection = client.get_collection(name=collection)

dist_thres = 1.60
max_rewrite_chars = 220 
route_min_cos = 0.30

DEIXIS_PAT = re2.compile(
    r"\b(tiếp|tiếp tục|nữa|như trên|như vừa rồi|cái đó|vấn đề đó|phần đó|trường hợp này|"
    r"cái kia|như đã nói|tiếp theo|như trước|phần trước|ví dụ trên|thì sao|còn)\b",
    re2.I | re2.U
)

def looks_deictic(text):
    t = (text or "").strip().lower()
    return bool(DEIXIS_PAT.search(t))

def clamp_len(s,n = max_rewrite_chars):
    s = (s or "").strip()
    if len(s) <= n:
        return s 
    cut = s[:n]
    dot = cut.rfind('.')
    if dot >= n * 0.5:
        return cut[:dot+1].strip()
    return cut.strip()

def normalize_ws(s):
    return re.sub(r'\s+',' ',(s or "").strip())


llm = AzureChatOpenAI(
    deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT"),
    api_key = os.getenv("AZURE_OPENAI_KEY"),
    api_version = os.getenv("AZURE_OPENAI_VERSION")
)

def vn_normalize(s):
    if not s:
        return ""
    s = unicodedata.normalize('NFC', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s 

ROUTE_SAMPLES = {
    "hedieuhanh": [
        "Hệ điều hành là gì?",
        "Môn hệ điều hành có mấy chương?",
        "Bạn có thể giải thích về deadlock trong hệ điều hành không?",
        "Sự khác biệt giữa tiến trình (process) và luồng (thread) là gì?",
        "Bộ nhớ ảo (virtual memory) hoạt động như thế nào?",
        "Các giải thuật lập lịch CPU phổ biến là gì?",
        "So sánh FCFS và Round Robin.",
        "Thông tin về môn học Hệ điều hành.",
        "Kernel là gì?",
        "Hệ thống file (file system) là gì?",
        "Thông tin về môn Hệ điều hành PTIT?",
    ],
    "Phantichthietkehttt": [
        "Môn phân tích thiết kế hệ thống thông tin có mấy chương?",
        "Biểu đồ Use Case (Use Case Diagram) dùng để làm gì?",
        "Hãy giải thích về biểu đồ lớp (Class Diagram).",
        "Sự khác biệt giữa yêu cầu chức năng và yêu cầu phi chức năng là gì?",
        "UML là gì và nó được sử dụng như thế nào?",
        "So sánh các mối quan hệ: Association, Aggregation, và Composition.",
        "Hãy kể tên một vài mô hình phát triển phần mềm.",
        "Mô hình Agile là gì?",
        "Mô hình thác nước (Waterfall) hoạt động ra sao?",
        "DAO (Data Access Object) là gì?",
        "Thông tin về môn Phân tích thiết kế hệ thống thông tin."
    ],
    "tutuonghcm": [
        "Môn tư tưởng Hồ Chí Minh có mấy chương?",
        "Nguồn gốc của Tư tưởng Hồ Chí Minh là gì?",
        "Nội dung cốt lõi của Tư tưởng Hồ Chí Minh về chủ nghĩa xã hội là gì?",
        "Tư tưởng Hồ Chí Minh về con đường cách mạng giải phóng dân tộc là gì?",
        "Vai trò của Đảng Cộng sản Việt Nam theo tư tưởng Hồ Chí Minh?",
        "Bạn có thể tóm tắt các đặc trưng của chủ nghĩa xã hội ở Việt Nam không?",
        "Chủ nghĩa Mác-Lênin có vai trò gì trong Tư tưởng Hồ Chí Minh?",
        "Thông tin về môn Tư tưởng Hồ Chí Minh.",
        "Sự kiện lịch sử 17h30 ngày 7/5/1954 là gì?",
        "Cô Phạm Thị Khánh là ai?"
    ],
    "Xulyanh": [
        "Môn xử lý ảnh có mấy chương?",
        "Xử lý ảnh (image processing) là gì?",
        "Phép lọc Gaussian (Gaussian filter) được sử dụng để làm gì?",
        "Phân đoạn ảnh (image segmentation) là gì?",
        "Biến đổi Fourier trong xử lý ảnh có ý nghĩa gì?",
        "So sánh phép toán hình thái học Erosion (co) và Dilation (giãn).",
        "Thresholding (ngưỡng hóa) trong xử lý ảnh là gì?",
        "Làm thế nào để phát hiện biên (edge detection) trong một bức ảnh?",
        "Bộ lọc Median (Median filter) khác gì bộ lọc trung bình (Mean filter)?",
        "Thông tin về môn Xử lý ảnh PTIT"
    ],
    "chitchat": [
        "Thời tiết hôm nay như thế nào?",
        "Ngoài trời nóng bao nhiêu?",
        "Ngày mai có mưa không?",
        "Nhiệt độ hiện tại là bao nhiêu?",
        "Bạn có thể cho tôi biết điều kiện thời tiết hiện tại không?",
        "Cuối tuần này có nắng không?",
        "Nhiệt độ hôm qua là bao nhiêu?",
        "Đêm nay trời sẽ lạnh đến mức nào?",
        "Ai là tổng thống đầu tiên của Hoa Kỳ?",
        "Chiến tranh thế giới thứ hai kết thúc vào năm nào?",
        "Bạn có thể kể cho tôi về lịch sử của internet không?",
        "Tháp Eiffel được xây dựng vào năm nào?",
        "Ai đã phát minh ra điện thoại?",
        "Tên của bạn là gì?",
        "Bạn có tên không?",
        "Tôi nên gọi bạn là gì?",
        "Ai đã tạo ra bạn?",
        "Bạn bao nhiêu tuổi?",
        "Bạn có thể kể cho tôi một sự thật thú vị không?",
        "Bạn có biết bất kỳ câu đố thú vị nào không?",
        "Màu sắc yêu thích của bạn là gì?",
        "Bộ phim yêu thích của bạn là gì?",
        "Bạn có sở thích nào không?",
        "Ý nghĩa của cuộc sống là gì?",
        "Bạn có thể kể cho tôi một câu chuyện cười không?",
        "Thủ đô của Pháp là gì?",
        "Dân số thế giới là bao nhiêu?",
        "Có bao nhiêu châu lục?",
        "Ai đã viết 'Giết con chim nhại'?",
        "Bạn có thể cho tôi một câu nói của Albert Einstein không?",
        "Tóm tắt nội dung phim Mưa Đỏ của đạo diễn Đặng Thái Huyền?",
        "Anh Tạ là ai?",
        "MH370 là cái gì?",
        "Nhỡ thích a Quang lính VNCH thì sao?",
        "Cô Đào Thị Thúy Quỳnh là ai?",
        "Thầy Đặng Hoàng Long là ai?",
        "Thầy Nguyễn Mạnh Hùng là ai?",
        "Cô Đỗ Thị Bích Ngọc là ai?",
        "Thầy Phạm Văn Cường là ai?",
        "Tổng thống Nga là ai?"
    ]
}


def l2_norm(x):
    n = np.linalg.norm(x,axis = 1,keepdims=True)
    return x / (n + 1e-12)

def build_short_history(messages,k_turns = 6,max_chars = 1200):
    hist = []
    for m in messages[-2*k_turns:]:
        role = "User" if m["role"] == 'user' else "assistant"
        hist.append(f"{role}:\n{normalize_ws(m['content'])}")
    s = '\n'.join(hist)[-max_chars:]
    return s[-max_chars:] if len(s) > max_chars else (s or "(blank)")
def reflection_rewrite(llm, history, last_user_q, last_subject: str = None) -> str:
    short_hist = build_short_history(history, k_turns=6, max_chars=1200)

    system_prompt = """You are a question rewriter.
- Job: Rewrite the latest user message into a standalone, self-contained Vietnamese QUESTION.
- Keep meaning, add missing nouns/entities from context if the message is deictic (e.g., "tiếp", "như trên").
- Output ONLY a single-line JSON: {"rewritten": "<text>"}.
- DO NOT include code fences, extra keys, comments, or explanations.
- Max length ~220 characters."""

    # Few-shot nhỏ gọn (VN)
    fewshot = """
[EX1]
HISTORY:
User: Trình bày các bước Canny.
Assistant: Gồm 5 bước...
User: tiếp nhé, nhưng nhấn mạnh NMS
REWRITE:
{"rewritten":"Trình bày các bước của thuật toán Canny và nhấn mạnh vai trò của Non-Maximum Suppression (NMS)."}

[EX2]
HISTORY:
User: Định nghĩa deadlock trong Hệ điều hành.
Assistant: ...
User: còn ví dụ như trên thì sao?
REWRITE:
{"rewritten":"Cho ví dụ minh hoạ về deadlock trong Hệ điều hành và giải thích điều kiện để xảy ra deadlock."}

[EX3]
HISTORY:
User: Tính tích chập 3x3 với ma trận ảnh như đã nêu.
Assistant: ...
User: tiếp, nhưng dùng padding same
REWRITE:
{"rewritten":"Tính tích chập 3×3 cho ma trận ảnh đã nêu, với padding 'same' và trình bày từng bước."}
"""

    human_prompt = f"""HISTORY (short):
{short_hist}

LATEST USER MESSAGE:
{last_user_q}

{fewshot}
Return only JSON:"""

    raw = ""
    try:
        resp = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)])
        raw = (resp.content or "").strip()
        # lọc trường hợp model trả kèm text rác
        m = re.search(r'\{.*\}', raw, flags=re.S)
        if m:
            raw = m.group(0)
        obj = json.loads(raw)
        rewritten = clamp_len(normalize_ws(obj.get("rewritten", "")))
        if rewritten:
            return rewritten
    except Exception:
        pass

    # Fallback: nếu câu mang tính deictic → ghép thêm chủ đề trước
    q = normalize_ws(last_user_q)
    if looks_deictic(q) and last_subject:
        subj = last_subject.lower()
        # ghép nhãn môn vào để tự-đủ nghĩa
        if subj == "hedieuhanh":
            q = f"[Hệ điều hành] {q}"
        elif subj == "xulyanh":
            q = f"[Xử lý ảnh] {q}"
        elif subj == "phantichthietkehttt":
            q = f"[Phân tích thiết kế HTTT] {q}"
        elif subj == "tutuonghcm":
            q = f"[Tư tưởng HCM] {q}"
    return clamp_len(q)


def build_route_index(embedder):
    index = {}
    for route,samples in ROUTE_SAMPLES.items():
        vecs = [embedder.embed_query(s) for s in samples]
        mat = np.array(vecs,dtype = float)
        mat = l2_norm(np.array(mat))
        index[route] = mat
    return index

route_index = build_route_index(embedder)

def is_compute_query(q,subject):
    ql = (q or "").lower()
    if subject and subject.lower() == 'hedieuhanh':
        kws = [
            "tính", "bao nhiêu", "waiting time", "turnaround", "response time",
            "throughput", "gantt", "fcfs", "sjf", "srtf", "rr", "round robin",
            "quantum", "q=", "burst", "arrival", "ready queue"
        ]
        return any(k in ql for k in kws) and bool(re.search(r'\d', ql))
    
    if subject and subject.lower() == 'xulyanh':
        xla_kws = [
            "tính", "tích chập", "convolution", "corr", "correlation",
            "ma trận", "matrix", "kernel", "bộ lọc", "filter",
            "3x3", "5x5", "7x7",
            "padding", "stride", "same", "valid",

            # edge/gradient
            "sobel", "prewitt", "scharr", "laplacian",
            "gradient", "độ lớn gradient", "magnitude", "hướng", "orientation",

            # smoothing/threshold
            "gaussian", "lọc gaussian", "median", "bilateral",
            "threshold", "ngưỡng", "otsu",

            # các bước canny (thường vẫn là lý thuyết, nhưng có thể yêu cầu tính)
            "nms", "non-maximum suppression", "double threshold", "hysteresis"
        ]
        looks_numeric = bool(re.search(r'\d', ql)) or ("[" in ql and "]" in ql)
        return any(k in ql for k in xla_kws) and looks_numeric
    
    return False

def compute_agent_solve(llm,query,context_hint,lang_instruction = "Vietnamese (Tiếng Việt)"):
    system_prompt = f"""Bạn là TungTomChat (Compute Agent).
- Nhiệm vụ: giải CÁC BÀI TẬP TÍNH TOÁN kỹ thuật.
- Bạn được phép dùng công thức chuẩn và lập luận của mình (không cần trích dẫn).
- Nếu thiếu tham số để giải, HÃY LIỆT KÊ rõ các tham số thiếu và DỪNG LẠI (không bịa).
- Trình bày ngắn gọn, theo các mục: (1) Dữ liệu vào, (2) Công thức/Thuật toán, (3) Tính toán từng bước, (4) Kết quả gọn gàng.
- Nếu là bài OS: hãy nêu bảng CT/WT/TAT và trung bình; nếu tính không chắc chắn, nói rõ lý do.
- Trả lời bằng {lang_instruction}."""
    human_prompt = f"""Câu hỏi:
{query}
GỢI Ý TỪ TÀI LIỆU (nếu có):
{(context_hint or '(trống)')[:1500]}

YÊU CẦU:
- Nếu đủ dữ liệu: giải dứt điểm và cho bảng kết quả.
- Nếu thiếu: liệt kê NGẮN GỌN các tham số thiếu (ví dụ: thiếu arrival của P2, thiếu quantum), sau đó dừng.
"""
    response = llm.invoke([SystemMessage(content = system_prompt),HumanMessage(content = human_prompt)])
    return (response.content or "").strip()


def route_semantic(q):
    q = (q or "").strip()
    if not q:
        return ("unknown",0.0)
    qvec = np.array(embedder.embed_query(q),dtype = float)
    qvec = qvec / (np.linalg.norm(qvec) + 1e-12)
    best_name, best_score = "unknown",-1.0
    for name,mat in route_index.items():
        scores = mat.dot(qvec)
        s = float(scores.max()) if scores.size > 0 else -1.0 
        if s > best_score:
            best_score = s 
            best_name = name
    if best_score < route_min_cos:
        return ("unknown", best_score)
    return (best_name, best_score)


def retrieve(col,embedder,query,subject_hint = None,k = fetch_k):
    qvec = embedder.embed_query(query)
    where = {"subject":subject_hint} if subject_hint else {}
    res = col.query(
        query_embeddings = [qvec],
        n_results = k, 
        include = ["metadatas","documents","distances"],
        **({"where": where} if where else {})
    )
    docs = res.get("documents",[[]])[0]
    metas = res.get("metadatas",[[]])[0]
    dists = res.get("distances",[[]])[0]
    return list(zip(docs,metas,dists))

def build_context_guarded(ranked,max_chars = 900):
    good = [(d,m,dist) for (d,m,dist) in ranked if (dist is None) or (dist <= dist_thres)]
    if not good:
        return ""
    blocks = []
    for doc,meta,dist in good:
        head = f"[{meta.get('subject','')}/{meta.get('section','')}]"
        body = (doc or "")[:max_chars]
        blocks.append(f"{head}\n{body}")
    return "\n\n".join(blocks)

def must_have_internal_citation(ans: str) -> bool:
    return bool(re.search(r"\[[^/\[\]\n]+/[^/\[\]\n]+\]", ans))


def answer_strict(llm,query,context,lang_instruction = "Vietnamese (Tiếng Việt)"):
    if not context.strip():
        return "Xin lỗi, tôi không tìm thấy thông tin liên quan để trả lời câu hỏi của bạn."
    system_prompt = f"""
    You are TungTomChat. Answer ONLY using context below.
-DO NOT use any outside knowledge.
-If context is insufficient, say so.
-Answer in {lang_instruction}.
- When user requires context, you must give them at least one inline citation like [subject/section]."""

    rag_prompt = f"""QUESTION:
{query}

CONTEXT:
{context}

ANSWER:"""
    response = llm.invoke([SystemMessage(content = system_prompt),HumanMessage(content = rag_prompt)])
    ans = response.content.strip()
    if not must_have_internal_citation(ans):
        return ("Xin lỗi, mình chưa tìm thấy trích dẫn nội bộ phù hợp để trả lời. "
                "Bạn có muốn cho phép mình tra cứu nguồn ngoài không?")
    return ans

def expand_with_parent(col,ranked,max_join = 5,max_chars = 2400):
    if not ranked:
        return ""
    
    _,meta0, _ = ranked[0]
    pid = meta0.get("parent_id")
    if not pid:
        return ""
    res = col.get(where = {"parent_id":pid},include = ["documents","metadatas"])
    doc_all = res.get("documents",[])
    meta_all = res.get("metadatas",[])

    pairs = sorted(zip(doc_all,meta_all), key = lambda x: x[1].get("order_start",0))
    pairs = pairs[:max_join]
    blocks = []
    used = 0
    for d, m in pairs:
        head = f"[{m.get('subject','')}/{m.get('section','')}]"
        block = f"{head}\n{d}"
        if used + len(block) > max_chars:
            break 
        blocks.append(block)
        used+= len(block)
    return "\n\n".join(blocks)


def answer_chitchat(llm,query,lang_instruction = "Vietnamese (Tiếng Việt)"):
    system_prompt = f"""
Bạn là TungTomChat, một trợ lý AI thân thiện và lịch sự.
-Trả lời ngắn gọn và tự nhiên.
-Không dùng trích dẫn, không nói về context.
-Với các câu hỏi đời sống chung chung, hãy cứ trả lời chi tiết dựa trên kiến thức chung.
-Nếu không chắc chắn về 1 dữ kiện, hãy trả lời tổng quát hoặc nói chưa chắc.
-Luôn trả lời bằng {lang_instruction}
""".strip()
    human_prompt = f"""
Người dùng hỏi(chitchat):{query}
Hãy trả lời ngắn gọn, thân thiện:
"""
    response = llm.invoke([SystemMessage(content = system_prompt),HumanMessage(content = human_prompt)])
    return (response.content or "").strip()



dialog = []
last_subject = None 
for i in range(10):
    q = input("Nhập câu hỏi:")

    dialog.append({"role":"user","content":q})
    rewritten_q = reflection_rewrite(llm,dialog,q)
    
    route,conf = route_semantic(rewritten_q)
    print(f"Route: {route} (conf={conf:.2f})")
    if route == 'chitchat':
        ans = answer_chitchat(llm,rewritten_q,lang_instruction="Vietnamese (Tiếng Việt)")
        print(f"Answer:\n{ans}\n")
        dialog.append({"role":"assistant","content":ans})
        continue 
    subject_for_query = None if route == "Unknown" else route
    if route.lower() in ['hedieuhanh','xulyanh'] and is_compute_query(q,route):
        last_subject = route.lower()
        cands = retrieve(collection,embedder,rewritten_q,subject_hint = subject_for_query,k = fetch_k)
        parent_context = expand_with_parent(collection,cands,max_join = 5,max_chars=2400)
        context_hint = build_context_guarded(cands,max_chars=900)
        context_hint = (context_hint + ("\n\n---\n\n" + parent_context if parent_context else ""))[:3000]
        print(f"Đang giải bài tập")
        ans = compute_agent_solve(llm,rewritten_q,context_hint,lang_instruction="Vietnamese (Tiếng Việt)")
        print(f"Answer:\n{ans}\n")
        dialog.append({"role":"assistant","content":ans})
        continue 

    cands = retrieve(collection,embedder,rewritten_q,subject_hint=subject_for_query,k = fetch_k)
    parent_context = expand_with_parent(collection,cands,max_join=5,max_chars=2400)
    context = build_context_guarded(cands,max_chars=900)
    context = (context + ("\n\n---\n\n" + parent_context if parent_context else ""))[:3000]
    print("Context:\n",context)
    print()
    print("Parent Context:\n",parent_context)
    print()
    ans = answer_strict(llm, rewritten_q, context, lang_instruction="Vietnamese (Tiếng Việt)")
    print(f"Answer:\n{ans}\n")
    dialog.append({"role":"assistant","content":ans})