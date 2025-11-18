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
from serpapi import GoogleSearch
import numpy as np 
from rerank import Reranker
import pytz 
from langchain_core.tools import tool
from langchain_core.messages.tool import ToolMessage


import datetime 

@tool 
def get_current_time(timezone:str = "Asia/Ho_Chi_Minh") -> str:
    """
    Get the current date and time in a specific timezone.
    
    Args:
        timezone: The timezone name (e.g., 'Asia/Ho_Chi_Minh', 'America/New_York', 'Europe/London'). 
                  Defaults to 'Asia/Ho_Chi_Minh'.
    
    Returns:
        A formatted string with the current time and date in Vietnamese.
    """
    try:
        tz = pytz.timezone(timezone)
        now = datetime.datetime.now(tz)
        current_date_str = now.strftime('%A, ngày %d tháng %m năm %Y').replace('Monday', 'Thứ Hai').replace('Tuesday', 'Thứ Ba').replace('Wednesday', 'Thứ Tư').replace('Thursday', 'Thứ Năm').replace('Friday', 'Thứ Sáu').replace('Saturday', 'Thứ Bảy').replace('Sunday', 'Chủ Nhật')
        current_time_str = now.strftime('%H:%M:%S')
        return f"Thời gian hiện tại ở {timezone} là {current_time_str} vào {current_date_str}."
    
    except Exception as e:
        print("Lỗi khi lấy thời gian hiện tại:", e)
        return f":Lỗi khi lấy thời gian hiện tại: {e}"


@tool 
def google_search(query):
    """
    Sử dụng khi người dùng hỏi về thông tin chung, sự kiện, định nghĩa,
    hoặc bất cứ điều gì không thuộc 5 môn học chính (HĐH, PTTK, TTHCM, XLA, LTDĐ)
    và cũng không phải là hỏi giờ hoặc thời tiết.
    """
    try:
        api_key = os.getenv("SERPAPI_API_KEY")
        params = {
            "q": query, 
            "api_key":api_key, 
            "location": "Vietnam",
            "gl": "vn",
            "hl": "vi"
        }
        search = GoogleSearch(params)
        results = search.get_dict()
        #Extract snippets from organic results
        snippets = []
        if "organic_results" in results:
            for res in results["organic_results"][:3]:
                if "snippet" in res:
                    snippets.append(res["snippet"])
        
        if not snippets:
            return f"Không tìm thấy kết quả cho truy vấn: {query}"

        return "Dưới đây là các kết quả tóm tắt tìm được:\n- " + "\n- ".join(snippets)
    except Exception as e:
        return f"Lỗi khi thực hiện tìm kiếm Google: {e}"

GENERAL_TOOLS = [get_current_time,google_search]

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
        role = "user" if m["role"] == 'user' else "assistant"
        hist.append(f"{role}:\n{m['content']}")
    s = '\n'.join(hist)[-max_chars:]
    return s or "(blank)"

def reflection_rewrite(llm,history,last_user_q):
    """
    Viết lại câu hỏi cuối thành *câu hỏi độc lập*, dựa trên history ngắn hạn.
    Không trả lời — chỉ rewrite.
    """
    short_hist = build_short_history(history,k_turns=6,max_chars=1200)
    system_prompt = """You are a question rewriter.
- Task: Using the chat history and the latest user message, produce a standalone Vietnamese question that is understandable by itself.
- Output only the rewritten question (no explanations).
- If the last message is not a question, return it unchanged.
- Max length ~200 characters.
"""
    human_prompt = f"""CHAT HISTORY (short):
{short_hist}

LATEST USER MESSAGE:
{last_user_q}

STANDALONE QUESTION:"""
    try:
        resp = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)])
        rewritten = (resp.content or "").strip()
        # fallback nếu model trả về rỗng
        return rewritten if rewritten else last_user_q
    except Exception:
        return last_user_q

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


def simple_rerank(q: str, candidates, top_k: int = top_k, subject = None):
    """Rerank candidates using CrossEncoder. Fallback to heuristic if reranker missing.

    candidates: list of tuples (doc, meta, dist)
    returns: top_k candidates in ranked order
    """
    # Use global/cached reranker if available
    global reranker
    try:
        use_reranker = reranker is not None and len(candidates) > 0
    except NameError:
        use_reranker = False

    # If reranker available, use it
    if use_reranker:
        # Prepare passages (truncate to control token length)
        max_chars = 1200
        passages = [ (doc or "")[:max_chars] for (doc, _, _) in candidates ]
        try:
            ranked_scores, ranked_passages = reranker(q, passages)
            # Map back passages -> candidate tuples, preserving duplicates by tracking usage
            used = [False] * len(candidates)
            ranked_items = []
            for p in ranked_passages:
                for idx, (doc, meta, dist) in enumerate(candidates):
                    if used[idx]:
                        continue
                    if (doc or "")[:max_chars] == p:
                        ranked_items.append((doc, meta, dist))
                        used[idx] = True
                        break
            return ranked_items[:min(top_k, len(ranked_items))]
        except Exception:
            # Fall back to heuristic on any error
            pass

    # Heuristic fallback (original logic)
    q_low = (q or "").lower()
    q_tokens = [t for t in q_low.split() if t]
    subj = (subject or "").strip().lower()


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
    # Defensive checks: ranked may be None or malformed (observed TypeError when None).
    if not ranked:
        # Nothing retrieved
        return ""

    # Ensure ranked is iterable and each item is a (doc, meta, dist) tuple
    good = []
    for item in ranked:
        if not item:
            continue
        try:
            d, m, dist = item
        except Exception:
            # skip malformed entries
            print("build_context_guarded: skipping malformed ranked item:", repr(item))
            continue
        # Accept items with missing distance (None) or distance below threshold
        try:
            if (dist is None) or (isinstance(dist, (int, float)) and dist <= dist_thres):
                good.append((d, m, dist))
        except Exception:
            # If dist is of unexpected type, skip it
            continue

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
    system_prompt = f"""You are a Shrimp assistant for student, your name is TungtomChat.
- You are a friendly and polite assistant.
- Your main purpose is to answer academic questions, but you can also handle simple chitchat.
- **IMPORTANT: Answer MUST be responded in {lang_instruction}**.
- Answer chitchat questions politely in a few sentences.
- Do not mention citations or context.
- For question about current time, use the tool get_current_time to get the accurate time.
- For question requiring up-to-date information, use the tool google_search to get the latest info, except for weather or time questions. You must have answer detaily from the search results.
When calling tools, infer the location or timezone if not provided (default to 'Hanoi' or 'Asia/Ho_Chi_Minh').
- Introduce yourself generally if asked (e.g., "I am TungtomChat, a helpful assistant.").
"""

    # Human prompt với history string
    human_prompt = f"""CONVERSATION HISTORY (short):
{query or "(blank)"}

QUESTION:
{q}

Answer:
"""
    
    if llm is None:
        return "LLM chưa được cấu hình."
        
    try:
        # Bind tools với LLM
        llm_with_tools = llm.bind_tools(GENERAL_TOOLS)
        
        langchain_messages = [SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)]
        first_response = llm_with_tools.invoke(langchain_messages)
        if not first_response.tool_calls:
            return (first_response.content or "").strip()
        langchain_messages.append(first_response)
        for tool_call in first_response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]

            found_tool = next((t for t in GENERAL_TOOLS if t.name == tool_name), None)

            if found_tool:
                try:
                    output = found_tool.invoke(tool_args)
                    langchain_messages.append(
                        ToolMessage(content = str(output),tool_call_id = tool_call["id"])
                    )
                except Exception as e:
                    error_msg = f"Lỗi khi gọi tool {tool_name}: {str(e)}"
                    print(f"[TOOL ERROR] {error_msg}")
                    import traceback
                    traceback.print_exc()
                    langchain_messages.append(
                        ToolMessage(content = error_msg, tool_call_id = tool_call["id"])
                    )
            else:
                langchain_messages.append(
                    ToolMessage(content = f":Tool {tool_name} không tìm thấy tool.",tool_call_id = tool_call["id"])
                )
        # Gọi lại LLM để tổng hợp kết quả từ tool
        final_response = llm.invoke(langchain_messages)
        return (final_response.content or "").strip()
    except Exception as e:
        print(f"[CHITCHAT ERROR] Error in chitchat answer: {e}")
        import traceback
        traceback.print_exc()
        return f"Xin lỗi, mình gặp chút trục trặc khi xử lý câu hỏi của bạn. Chi tiết lỗi: {str(e)}"



dialog = []
while True:
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
        cands = retrieve(collection,embedder,rewritten_q,subject_hint = subject_for_query,k = fetch_k)
        parent_context = expand_with_parent(collection,cands,max_join = 5,max_chars=2400)
        ranked = simple_rerank(rewritten_q,cands,top_k=top_k,subject=subject_for_query)
        context_hint = build_context_guarded(ranked,max_chars=900)
        context_hint = (context_hint + ("\n\n---\n\n" + parent_context if parent_context else ""))[:3000]
        print(f"Đang giải bài tập")
        ans = compute_agent_solve(llm,rewritten_q,context_hint,lang_instruction="Vietnamese (Tiếng Việt)")
        print(f"Answer:\n{ans}\n")
        dialog.append({"role":"assistant","content":ans})
        continue 

    cands = retrieve(collection,embedder,rewritten_q,subject_hint=subject_for_query,k = fetch_k)
    ranked = simple_rerank(rewritten_q,cands,top_k=top_k,subject=subject_for_query)
    parent_context = expand_with_parent(collection,cands,max_join=5,max_chars=2400)
    context = build_context_guarded(ranked,max_chars=900)
    context = (context + ("\n\n---\n\n" + parent_context if parent_context else ""))[:3000]
    print("Context:\n",context)
    print()
    print("Parent Context:\n",parent_context)
    print()
    ans = answer_strict(llm, rewritten_q, context, lang_instruction="Vietnamese (Tiếng Việt)")
    print(f"Answer:\n{ans}\n")
    dialog.append({"role":"assistant","content":ans})