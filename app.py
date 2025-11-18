# -*- coding: utf-8 -*-
import os, re, unicodedata, datetime
import numpy as np
import pytz
import streamlit as st
import chromadb
from chromadb.config import Settings
from dotenv import load_dotenv
from serpapi import GoogleSearch
import base64 

from langchain_openai import AzureChatOpenAI
from langchain.schema import SystemMessage, HumanMessage
from langchain_core.tools import tool
from langchain_core.messages.tool import ToolMessage
from embeddings import get_embedding
# ========= ENV & GLOBALS =========
load_dotenv()

DB_PATH = os.getenv("DB_PATH", ".chroma_db")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "ptit_giaotrinh_2")
FETCH_K = int(os.getenv("FETCH_K", "30"))
TOP_K   = int(os.getenv("TOP_K", "10"))
DIST_THRES = float(os.getenv("DIST_THRES", "1.60"))
ROUTE_MIN_COS = float(os.getenv("ROUTE_MIN_COS", "0.30"))

# Optional reranker (nếu không có file rerank.py thì bỏ qua)

# ========= TOOLS (cho chitchat) =========
@tool
def get_current_time(timezone: str = "Asia/Ho_Chi_Minh") -> str:
    """Trả về thời gian hiện tại (tiếng Việt)."""
    try:
        tz = pytz.timezone(timezone)
        now = datetime.datetime.now(tz)
        weekdays = {
            'Monday': 'Thứ Hai', 'Tuesday': 'Thứ Ba', 'Wednesday': 'Thứ Tư',
            'Thursday': 'Thứ Năm', 'Friday': 'Thứ Sáu',
            'Saturday': 'Thứ Bảy', 'Sunday': 'Chủ Nhật'
        }
        wd_vi = weekdays.get(now.strftime('%A'), 'Thứ')
        date_vi = now.strftime(f'{wd_vi}, ngày %d tháng %m năm %Y')
        time_vi = now.strftime('%H:%M:%S')
        return f"Thời gian hiện tại ở {timezone} là {time_vi} vào {date_vi}."
    except Exception as e:
        return f"Lỗi khi lấy thời gian hiện tại: {e}"

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
            "q":query,
            "api_key":api_key,
            "location": 'Vietnam',
            "gl": 'vn',
            'hl': 'vi'
        }
        search = GoogleSearch(params)
        results = search.get_dict()
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

# ========= ROUTER & HELPERS =========
def vn_normalize(s):
    if not s: return ""
    s = unicodedata.normalize("NFC", s)
    return re.sub(r"\s+", " ", s).strip()

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
        "Mô hình màu là gì?"
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


@st.cache_resource
def load_embedder():
    return get_embedding()

@st.cache_resource
def load_reranker():
    try:
        from rerank import Reranker
        return Reranker()
    except Exception:
        return None 
@st.cache_resource
def load_llm():
    """Load LLM (chỉ 1 lần)."""
    return AzureChatOpenAI(
        deployment_name=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
        api_key=os.getenv("AZURE_OPENAI_KEY"),
        api_version=os.getenv("AZURE_OPENAI_VERSION")
    )

@st.cache_resource
def load_db_collection():
    """Load ChromaDB collection (chỉ 1 lần)."""
    client = chromadb.PersistentClient(path=DB_PATH, settings=Settings(anonymized_telemetry=False))
    collection = client.get_collection(name=COLLECTION_NAME)
    return collection

embedder = load_embedder()
reranker = load_reranker()
llm = load_llm()
collection = load_db_collection()

def l2_norm(x):
    n = np.linalg.norm(x, axis=1, keepdims=True)
    return x / (n + 1e-12)

def build_route_index(embedder):
    idx = {}
    for route, samples in ROUTE_SAMPLES.items():
        vecs = [embedder.embed_query(s) for s in samples]
        mat = l2_norm(np.array(vecs, dtype=float))
        idx[route] = mat
    return idx

ROUTE_INDEX = build_route_index(embedder)

def get_image_base64(image_bytes):
    encoded_string = base64.b64encode(image_bytes).decode('utf-8')
    return encoded_string


def route_semantic(q):
    q = (q or "").strip()
    if not q: return ("unknown", 0.0)
    qv = np.array(embedder.embed_query(q), dtype=float)
    qv = qv / (np.linalg.norm(qv) + 1e-12)
    best, score = "unknown", -1.0
    for name, mat in ROUTE_INDEX.items():
        s = float(mat.dot(qv).max()) if mat.size else -1.0
        if s > score:
            best, score = name, s
    if score < ROUTE_MIN_COS:
        return ("unknown", score)
    return (best, score)

def build_short_history(messages, k_turns=6, max_chars=1000):
    hist = []
    for m in messages[-2*k_turns:]:
        role = m["role"]
        hist.append(f"{role}:\n{m['content']}")
    return ("\n".join(hist))[-max_chars:] or "(blank)"

def reflection_rewrite(llm, history, last_q):
    short_hist = build_short_history(history, 6, 1000)
    sys = """You are a rewriting assistant for questions.
- Using the chat history and the latest user message, rewrite the LAST USER MESSAGE into a standalone Vietnamese version.
- If the last message contains MULTIPLE QUESTIONS, KEEP ALL of them. Do NOT drop, merge or reorder questions.
- Do NOT answer the questions.
- Output ONLY the rewritten message (no explanation). Max ~400 chars.
- If the last message is not a question, return it unchanged."""
    human = f"CHAT HISTORY (short):\n{short_hist}\n\nLATEST USER MESSAGE:\n{last_q}\n\nSTANDALONE QUESTION:"
    try:
        resp = llm.invoke([SystemMessage(content=sys), HumanMessage(content=human)])
        text = (resp.content or "").strip()
        return text if text else last_q
    except Exception:
        return last_q

def retrieve(col, embedder, query, subject_hint=None, k=FETCH_K):
    qvec = embedder.embed_query(query)
    where = {"subject": subject_hint} if subject_hint else {}
    res = col.query(query_embeddings=[qvec], n_results=k,
                    include=["metadatas","documents","distances"],
                    **({"where": where} if where else {}))
    docs  = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    dists = res.get("distances", [[]])[0]
    return list(zip(docs, metas, dists))

def simple_rerank(q, cands, top_k=TOP_K):
    # dùng reranker nếu có
    if reranker and cands:
        passages = [(d or "")[:1200] for (d,_,_) in cands]
        try:
            _, ranked_pass = reranker(q, passages)
            used = [False]*len(cands)
            out = []
            for p in ranked_pass:
                for i,(d,m,dist) in enumerate(cands):
                    if used[i]: continue
                    if (d or "")[:1200] == p:
                        out.append((d,m,dist)); used[i]=True; break
            return out[:min(top_k, len(out))]
        except Exception:
            pass
    # fallback heuristic
    qtok = set((q or "").lower().split())
    scored=[]
    for (d,m,dist) in cands:
        toks=set((d or "").lower().split())
        overlap=len(qtok & toks)
        dterm=0.0
        try: dterm=1/(1+float(dist))
        except: pass
        score=0.7*overlap+0.3*dterm
        scored.append((score,(d,m,dist)))
    scored.sort(key=lambda x:x[0], reverse=True)
    return [it for _,it in scored[:min(top_k,len(scored))]]

def build_context_guarded(ranked, max_chars=900):
    if not ranked: return ""
    good=[]
    for d,m,dist in ranked:
        try:
            if (dist is None) or (isinstance(dist,(int,float)) and dist<=DIST_THRES):
                good.append((d,m))
        except: continue
    if not good: return ""
    blocks=[]
    for d,m in good:
        head=f"[{m.get('subject','')}/{m.get('section','')}]"
        blocks.append(f"{head}\n{(d or '')[:max_chars]}")
    return "\n\n".join(blocks)

def is_compute_query(q, subject):
    ql=(q or "").lower()
    if subject and subject.lower()=="hedieuhanh":
        kws=["tính","waiting time","turnaround","response time","throughput","gantt",
             "fcfs","sjf","srtf","rr","round robin","quantum","burst","arrival"]
        return any(k in ql for k in kws) and bool(re.search(r"\d", ql))
    if subject and subject.lower()=="xulyanh":
        kws=["tính","tích chập","convolution","kernel","3x3","5x5","padding","stride",
             "sobel","prewitt","laplacian","gradient","magnitude","otsu","threshold"]
        looks_num=bool(re.search(r"\d", ql)) or ("[" in ql and "]" in ql)
        return any(k in ql for k in kws) and looks_num
    return False

# ========= STREAM HELPERS =========
def stream_answer(llm, messages):
    """Stream token-by-token into a string (fallback to non-stream)."""
    try:
        acc = ""
        for chunk in llm.stream(messages):
            token = getattr(chunk, "content", None)
            if token:
                acc += token
                yield acc
        if not acc:
            # fallback khi provider không stream
            resp = llm.invoke(messages)
            yield (resp.content or "")
    except Exception:
        resp = llm.invoke(messages)
        yield (resp.content or "")

# ========= BRANCHES (prompts) =========
def make_rag_messages(query, context, lang="Vietnamese (Tiếng Việt)"):
    sys = f"""You are TungTomChat. Answer ONLY using context below.
- Do NOT use outside knowledge.
- If context is insufficient, say so.
- Answer in {lang}.
- Include at least one inline citation like [subject/section]."""
    human = f"QUESTION:\n{query}\n\nCONTEXT:\n{context}\n\nANSWER:"
    return [SystemMessage(content=sys), HumanMessage(content=human)]

def make_compute_messages(query, ctx_hint, lang="Vietnamese (Tiếng Việt)"):
    sys = f"""Bạn là TungTomChat (Compute Agent).
- Giải bài tập tính toán kỹ thuật bằng công thức/thuật toán chuẩn.
- Thiếu tham số thì LIỆT KÊ và DỪNG, không bịa.
- Trình bày: (1) Dữ liệu vào, (2) Công thức/Thuật toán, (3) Tính từng bước, (4) Kết quả.
- Trả lời bằng {lang}."""
    human = f"Câu hỏi:\n{query}\n\nGỢI Ý (nếu có):\n{(ctx_hint or '(trống)')[:1500]}\n\nYÊU CẦU: như hướng dẫn trên."
    return [SystemMessage(content=sys), HumanMessage(content=human)]

def answer_chitchat_with_tools(question, debug=False):
    sys = "You are TungtomChat, a friendly assistant. Answer concisely in Vietnamese."
    human = f"QUESTION:\n{question}\n\nAnswer:"
    llm_tools = llm.bind_tools(GENERAL_TOOLS)
    msgs = [SystemMessage(content=sys), HumanMessage(content=human)]
    first = llm_tools.invoke(msgs)
    logs=[]
    if getattr(first, "tool_calls", None):
        msgs.append(first)
        for tc in first.tool_calls:
            tool_name, tool_args = tc["name"], tc["args"]
            if debug: logs.append(f"↪ gọi tool: {tool_name}({tool_args})")
            tool_obj = next((t for t in GENERAL_TOOLS if t.name == tool_name), None)
            if tool_obj:
                out = tool_obj.invoke(tool_args)
                msgs.append(ToolMessage(content=str(out), tool_call_id=tc["id"]))
                if debug: logs.append(f"↩ tool trả về: {out}")
            else:
                msgs.append(ToolMessage(content=f"Tool {tool_name} not found", tool_call_id=tc["id"]))
                if debug: logs.append(f"⚠ tool không tồn tại: {tool_name}")
        # tổng hợp cuối (stream)
        return msgs, logs
    else:
        # Không cần tool ⇒ stream ngay nội dung first
        # fake messages để stream helper dùng lại 1 flow
        return [SystemMessage(content=sys), HumanMessage(content=human)], logs

# ========= UI =========
st.set_page_config(page_title="TungTomChat", page_icon="🦐", layout="wide")
st.markdown("<style>.stChatMessage { font-size: 16px; }</style>", unsafe_allow_html=True)

with st.sidebar:
    st.title("🦐 TungTomChat")
    debug = st.toggle("Debug", value=False)
    with st.popover("Tùy chỉnh"):
        st.caption("Chỉ bật khi cần:")
        DIST_THRES = st.slider("Distance threshold", 0.5, 2.5, DIST_THRES, 0.05)
        ROUTE_MIN_COS = st.slider("Route min cosine", 0.0, 0.9, ROUTE_MIN_COS, 0.01)
        FETCH_K = st.number_input("Fetch K", 5, 100, FETCH_K, 1)
        TOP_K = st.number_input("Top K", 1, 30, TOP_K, 1)

if "dialog" not in st.session_state:
    st.session_state.dialog = []

st.header("TungTomChat — PTIT Study Assistant")

# render history
for m in st.session_state.dialog:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])


uploaded_file = st.file_uploader(
        "Tải ảnh lên",
        type = ["png", "jpg", "jpeg", "bmp", "gif"]
    )

if uploaded_file:
    st.image(uploaded_file.getvalue(),caption = "Ảnh vừa tải lên",width = 200)


user_msg = st.chat_input("Gõ câu hỏi của bạn…")
if user_msg:
    # 1) show user immediately
    st.session_state.dialog.append({"role":"user","content":user_msg})
    with st.chat_message("user"):
        st.markdown(user_msg)
        if uploaded_file:
            st.image(uploaded_file.getvalue(),width = 200)

    # 2) reflection (nhưng không show tràn; chỉ show bản rewrite nếu khác)

    # 4) tạo bong bóng assistant + thinking placeholder
    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.markdown("*(Đang suy nghĩ…)*")

        if uploaded_file:
            try:
                image_bytes = uploaded_file.getvalue()
                base64_image = get_image_base64(image_bytes)
                system_message = SystemMessage(
                    content = "Bạn là trợ lý học tập AI. Hãy trả lời câu hỏi của người dùng một cách chi tiết, tập trung vào nội dung học thuật. Câu trả lời phải dựa trên cả văn bản và HÌNH ẢNH mà người dùng cung cấp. Nếu đó là một bài toán, hãy giải nó từng bước."
                )
                human_message = HumanMessage(
                    content = [
                        {"type":"text","text":user_msg},
                        {
                            "type":"image_url",
                            "image_url":{
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                )
                answer_text = ""
                for partial in stream_answer(llm,[system_message,human_message]):
                    answer_text = partial 
                    placeholder.markdown(answer_text)
                
                st.session_state.dialog.append({"role":"assistant","content":answer_text})
                st.stop()
            except Exception as e:
                placeholder.markdown(f"Lỗi khi xử lý ảnh: {e}")
                st.stop()

        rewritten = reflection_rewrite(llm, st.session_state.dialog, user_msg)

    # 3) route (ẩn mặc định, chỉ hiện khi debug)
        route, conf = route_semantic(rewritten)
        if debug:
            st.caption(f"Route: **{route}** (conf={conf:.2f})")

        # === CHITCHAT ===
        if route.lower() == "chitchat":
            msgs, logs = answer_chitchat_with_tools(rewritten, debug=debug)
            # nếu là case không tool, msgs là prompt; nếu có tool, msgs đã append ToolMessage sẵn ⇒ stream tổng hợp
            # stream
            answer_text = ""
            for partial in stream_answer(llm, msgs):
                answer_text = partial
                placeholder.markdown(answer_text)
            if debug and logs:
                st.caption("\n".join(logs))

            st.session_state.dialog.append({"role":"assistant","content":answer_text})
            st.stop()

        # === COMPUTE (OS/XLA có số liệu) ===
        if route.lower() in ["hedieuhanh","xulyanh"] and is_compute_query(rewritten, route):
            cands = retrieve(collection, embedder, rewritten, subject_hint=route, k=FETCH_K)
            ranked = simple_rerank(rewritten, cands, top_k=TOP_K)
            ctx = build_context_guarded(ranked, 900)
            # stream compute
            answer_text = ""
            for partial in stream_answer(llm, make_compute_messages(rewritten, ctx)):
                answer_text = partial
                placeholder.markdown(answer_text)
            st.session_state.dialog.append({"role":"assistant","content":answer_text})
            if debug:
                with st.expander("Retrieve preview"):
                    for i,(d,m,dist) in enumerate(ranked,1):
                        st.write(f"[{i}] dist={dist:.3f} | {m.get('subject')}/{m.get('section')}")
                        st.caption((d or "")[:280]+"…")
                with st.expander("Context"):
                    st.code(ctx)
            st.stop()

        # === RAG LÝ THUYẾT / UNKNOWN ===
        subject_for_query = None if route.lower()=="unknown" else route
        cands = retrieve(collection, embedder, rewritten, subject_hint=subject_for_query, k=FETCH_K)
        ranked = simple_rerank(rewritten, cands, top_k=TOP_K)
        ctx = build_context_guarded(ranked, 900)

        # stream rag strict
        answer_text = ""
        for partial in stream_answer(llm, make_rag_messages(rewritten, ctx)):
            answer_text = partial
            placeholder.markdown(answer_text)

        st.session_state.dialog.append({"role":"assistant","content":answer_text})
        if debug:
            with st.expander("Retrieve preview"):
                for i,(d,m,dist) in enumerate(ranked,1):
                    st.write(f"[{i}] dist={dist:.3f} | {m.get('subject')}/{m.get('section')}")
                    st.caption((d or "")[:280]+"…")
            with st.expander("Context"):
                st.code(ctx)
