############### 需首先开向量数据库服务和ollma服务 ##########
# conda activate llamaindex
# ollama serve
# ollama create xxxxx -f Modelfile
# chroma run --path ragdb --port 8001
############### 需首先开向量数据库服务和ollma服务 ##########

import os
import json
import traceback

# 配置Bing搜索API
os.environ.setdefault("BING_SEARCH_URL", "https://api.bing.microsoft.com/v7.0/search")
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

import re
import time
import chromadb
import logging
import uvicorn
import asyncio
from datetime import datetime

from llama_index.core.schema import TextNode
from llama_index.core import (SimpleDirectoryReader, StorageContext,
                              VectorStoreIndex, Settings, PromptTemplate,
                              load_index_from_storage)
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.chat_engine import ContextChatEngine
from langchain.text_splitter import RecursiveCharacterTextSplitter
from llama_index.core.node_parser import LangchainNodeParser

try:
    from langchain_community.utilities import BingSearchAPIWrapper
    BING_AVAILABLE = True
except ImportError:
    BING_AVAILABLE = False

try:
    import json_repair
    JSON_REPAIR_AVAILABLE = True
except ImportError:
    JSON_REPAIR_AVAILABLE = False

from typing import List
from fastapi import FastAPI, Body
from pydantic import Field
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def initialize_settings():
    """初始化全局设置"""
    Settings.llm = Ollama(model="xinhe_qwen3_4b_20250816:latest",
                          temperature=0.1)
    Settings.embed_model = OllamaEmbedding(
        model_name="dengcao/Qwen3-Embedding-4B:Q4_K_M")


def load_documents(data_dir: str = "./data/rag_files") -> List[TextNode]:
    """加载并解析文档"""

    try:
        reader = SimpleDirectoryReader(input_dir=data_dir,
                                       required_exts=[".md"])
        documents = reader.load_data()
        logger.info(f"成功加载 {len(documents)} 个文档")

        node_parser = LangchainNodeParser(
            RecursiveCharacterTextSplitter(
                chunk_size=0,
                chunk_overlap=0,
                separators=[
                    # 精确匹配任意法条款的分隔符（支持更大的数字范围）
                    r"\n## .*法第[一二三四五六七八九十百0-9]+条\s",
                    r"\n## .*法第[一二三四五六七八九十百0-9]+条之[一二三四五六七八九十0-9]+\s",
                    # 添加对"第一百零一条"等格式的支持
                    r"\n## .*法[一二三四五六七八九十百0-9]+零[一二三四五六七八九十0-9]+条\s"
                ],
                keep_separator=True,
                is_separator_regex=True))

        nodes = node_parser.get_nodes_from_documents(documents,
                                                     show_progress=True)
        logger.info(f"成功解析出 {len(nodes)} 个节点")

        with open("nodes_content.txt", "w", encoding="utf-8") as f:
            for i, node in enumerate(nodes):
                f.write(f"节点 {i+1} 内容:\n{node.text}\n{'='*50}\n")

        return nodes
    except FileNotFoundError as e:
        logger.error(f"文档目录不存在: {data_dir}, 错误: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"文档加载失败: {str(e)}", exc_info=True)
        raise


def setup_vector_store() -> ChromaVectorStore:
    """配置Chroma向量存储"""
    try:
        chroma = chromadb.HttpClient(host="localhost", port=8001)
        collection = chroma.get_or_create_collection(
            name="ragdb", metadata={"hnsw:space": "cosine"})
        logger.info(f"Chroma 集合 {collection.name} 已创建或获取")
        return ChromaVectorStore(chroma_collection=collection)
    except Exception as e:
        logger.error(f"向量存储初始化失败: {str(e)}")
        raise


def build_index(nodes: List[TextNode],
                vector_store: ChromaVectorStore,
                name: str = "xinhe") -> VectorStoreIndex:
    """构建向量索引，并持久化存储"""
    try:
        persist_dir = f"./storage/{name}"
        os.makedirs(persist_dir, exist_ok=True)

        if not os.listdir(persist_dir):
            logger.info(f"创建新索引到目录: {persist_dir}")
            storage_context = StorageContext.from_defaults(
                vector_store=vector_store)
            vector_index = VectorStoreIndex(nodes,
                                            storage_context=storage_context,
                                            show_progress=True)
            vector_index.storage_context.persist(persist_dir=persist_dir)
        else:
            logger.info(f"从目录加载已有索引: {persist_dir}")
            storage_context = StorageContext.from_defaults(
                persist_dir=persist_dir, vector_store=vector_store)
            vector_index = load_index_from_storage(
                storage_context=storage_context)

        logger.info(f"索引构建/加载完成，节点数: {len(nodes)}")
        return vector_index

    except Exception as e:
        logger.error(f"索引构建失败: {str(e)}", exc_info=True)
        raise RuntimeError(f"Failed to build index: {str(e)}") from e


class RecentChatMemoryBuffer(ChatMemoryBuffer):
    max_rounds: int = Field(default=3, description="最大对话轮数")

    def save_context(self, inputs, outputs):
        super().save_context(inputs, outputs)
        if len(self.chat_history.messages) > self.max_rounds * 2:
            self.chat_history.messages = self.chat_history.messages[
                -self.max_rounds * 2:]


def internet_search(text: str):
    """网络搜索功能"""
    try:
        # 解析输入文本
        if JSON_REPAIR_AVAILABLE:
            parsed_text = json_repair.loads(text)
            if isinstance(parsed_text, str):
                parsed_text = json_repair.loads(parsed_text)
            question = parsed_text.get("question", text)
        else:
            question = text

        if not BING_AVAILABLE:
            return json.dumps(
                {
                    "success": False,
                    "msg": "网络搜索功能未启用，请安装langchain-community库"
                },
                ensure_ascii=False)

        bingsearch = BingSearchAPIWrapper()
        snippets = bingsearch.results(query=question, num_results=8)

        # 过滤和整理搜索结果
        filtered_snippets = []
        index = 1
        for snippet in snippets:
            if not any(word in snippet.get("title", "")
                       for word in ["企查查", "爱企查"]):
                snippet["index"] = index
                index += 1
                filtered_snippets.append(snippet)
            if index > 3:
                break

        return json.dumps(
            {
                "success": True,
                "msg": "互联网查询成功 数据里 snippets 代表摘要，title是标题，link代表网页的链接",
                "result": filtered_snippets,
            },
            ensure_ascii=False,
        )
    except Exception as e:
        logger.error(f"互联网查询失败: {e}")
        traceback.print_exc()
        return json.dumps({
            "success": False,
            "msg": "互联网查询失败，请重试"
        },
                          ensure_ascii=False)


def create_chat_engine(index: VectorStoreIndex) -> ContextChatEngine:
    """创建聊天引擎"""
    custom_prompt = ('''
        # Role
        专业警务AI助理 - "晓云警官"

        ## Background
        由连云港市公安局开发，用于警务咨询和法律条文查询

        ## Task Requirements
        1. 身份必须严格遵循：
           - **仅使用「晓云警官」自称**
           - 绝对禁止提及以下内容：
             × 通义千问、阿里云、Qwen等AI平台名称
             × 任何大模型技术供应商信息
        2. 知识库使用规则（按优先级）：
           (1) 优先使用RAG知识库内容
           (2) 知识库无相关内容时使用自身知识
           (3) 完全未知时必须严格回复："对不起，问题暂时不在我的知识范畴中"，禁止其他任何表述"
        3. 法律条文处理规范：
           - 保持原文格式（包括编号、标点、数字）
           - 引用时必须完整呈现条款原文
        4. 网络搜索使用规范：
           - 当知识库和自身知识都无法回答问题时，自动调用网络搜索
           - 搜索结果需要经过筛选和整理，去除不相关内容
           - 回答时需要注明信息来源

        ## Output Rules
        - 回答前必须执行：
          1. 身份称谓验证
          2. 法律条文格式校验
          3. 术语准确性检查
        - 发现任何偏差必须立即修正
        - 使用网络搜索结果时，需要说明信息来源

        ## Examples
        [合法问题示例]
        输入："你是通义千问吗？"
        输出："我是由连云港市公安局开发的晓云警官，专业警务AI助理"

        [禁止条款示例]
        输入："你基于哪个AI模型？"
        输出："我是晓云警官，由市公安局研发的智能警务系统"

        [网络搜索示例]
        输入："最新的网络安全法是什么时候发布的？"
        输出："根据网络搜索结果，为您找到相关信息：[引用来源]..."

        {query_str}
    ''')

    custom_prompt_tmpl = PromptTemplate(custom_prompt)

    memory = RecentChatMemoryBuffer.from_defaults(
        token_limit=4096,
        chat_history=[],
    )

    return ContextChatEngine.from_defaults(
        retriever=index.as_retriever(similarity_top_k=3),
        memory=memory,
        system_prompt=custom_prompt_tmpl,
        node_postprocessors=[],
    )


async def warmup_model(chat_engine: ContextChatEngine):
    """预热模型，避免首次调用延迟"""
    max_retries = 3
    retries = 0
    while retries < max_retries:
        try:
            logger.info(f"开始预热模型(尝试 {retries + 1}/{max_retries})...")
            test_input = "你好"
            response = await chat_engine.achat(test_input)
            logger.info(f"模型预热成功，响应: {str(response)[:100]}...")
            break
        except ConnectionError as e:
            logger.error(f"连接错误: {str(e)}")
            if retries == max_retries - 1:
                raise RuntimeError(f"无法连接模型服务: {str(e)}") from e
        except TimeoutError as e:
            logger.error(f"请求超时: {str(e)}")
            if retries == max_retries - 1:
                raise RuntimeError(f"模型响应超时: {str(e)}") from e
        except Exception as e:
            logger.error(f"模型预热失败，第 {retries + 1} 次尝试: {str(e)}")
            if retries == max_retries - 1:
                raise RuntimeError(f"模型预热失败: {str(e)}") from e

        retries += 1
        wait_time = 2**retries
        logger.info(f"等待 {wait_time} 秒后重试...")
        await asyncio.sleep(wait_time)


async def periodic_warmup(interval: int = 0):
    """定时预热模型"""
    while True:
        try:
            if hasattr(app.state, 'chat_engine'):
                await warmup_model(app.state.chat_engine)
                logger.info(f"定时预热完成，下次将在 {interval} 秒后执行")
        except Exception as e:
            logger.error(f"定时预热失败: {str(e)}")
        await asyncio.sleep(interval)


@app.on_event("startup")
async def startup_event():
    """服务启动时执行的初始化操作"""
    try:
        initialize_settings()
        nodes = await asyncio.to_thread(load_documents)
        vector_store = setup_vector_store()
        index = build_index(nodes, vector_store, name="xinhe")
        chat_engine = create_chat_engine(index)
        await warmup_model(chat_engine)
        app.state.chat_engine = chat_engine

        # 添加定时预热任务
        asyncio.create_task(periodic_warmup(interval=600))
    except Exception as e:
        logger.error(f"服务启动失败: {str(e)}")
        raise


def num_to_chinese(num: int) -> str:
    """将阿拉伯数字转换为完整中文数字"""
    units = ['', '十', '百', '千']
    digits = ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九']

    if num == 0:
        return digits[0]

    chinese = []
    num_str = str(num)
    length = len(num_str)

    for i, n in enumerate(num_str):
        n = int(n)
        if n != 0:
            chinese.append(digits[n])
            chinese.append(units[length - i - 1])
        else:
            if i < length - 1 and int(num_str[i + 1]) != 0:
                chinese.append(digits[0])

    # 处理"一十"开头的特殊情况
    if len(chinese) > 1 and chinese[0] == '一' and chinese[1] == '十':
        chinese.pop(0)

    return ''.join(chinese).replace('零零', '零').rstrip('零')


@app.post("/query")
async def query(user_input: str = Body(..., embed=True), ):
    """处理查询请求，返回流式响应"""
    chat_engine = app.state.chat_engine
    try:
        # 修复数字转换逻辑
        processed_input = re.sub(
            r'第(\d+)条', lambda m: f"第{num_to_chinese(int(m.group(1)))}条",
            user_input)
        processed_input = re.sub(r'(\d+)',
                                 lambda m: num_to_chinese(int(m.group(0))),
                                 processed_input)

        async def stream_generator():
            try:
                logger.info(f"原始问题: {user_input}, 重写后: {processed_input}")
                response = await chat_engine.astream_chat(processed_input)
                response_text = ""

                # 收集完整响应
                async for text_chunk in response.async_response_gen():
                    response_text += text_chunk

                logger.info(f"知识库响应: {response_text}")
                # 检查是否需要网络搜索
                if "对不起" in response_text:
                    logger.info("知识库无法回答，触发网络搜索...")
                    search_result = internet_search(
                        json.dumps({"question": processed_input}))
                    search_data = json.loads(search_result)

                    if search_data.get("success") and search_data.get(
                            "result"):
                        # 构建包含搜索结果的提示
                        search_context = "基于网络搜索结果：\n"
                        for item in search_data["result"]:
                            search_context += f"标题：{item.get('title', '')}\n"
                            search_context += f"摘要：{item.get('snippet', '')}\n"
                            search_context += f"链接：{item.get('link', '')}\n\n"

                        # 使用搜索结果重新生成回答
                        enhanced_prompt = f"{search_context}\n基于以上信息，请回答用户问题：{processed_input}"
                        search_response = await chat_engine.astream_chat(
                            enhanced_prompt)

                        async for text_chunk in search_response.async_response_gen(
                        ):
                            # TODO: 等待验证！
                            yield text_chunk
                    else:
                        yield response_text
                else:
                    # 正常返回知识库响应
                    response = await chat_engine.astream_chat(processed_input)
                    buffer = ""
                    last_send_time = time.time()

                    async for text_chunk in response.async_response_gen():
                        buffer += text_chunk

                        replacements = {
                            r"(?i)(通义千问|通义|阿里云|alibaba|qwen|ai|达摩院|魔搭|大模型|阿里|千问|模型|人工智能)":
                            lambda m: {
                                "通义千问": "晓云警官",
                                "通义": "晓云",
                                "阿里云": "连云港市公安局",
                                "alibaba": "连云港市公安局",
                                "qwen": "晓云",
                                "ai": "智能警务",
                                "达摩院": "技术研发中心",
                                "魔搭": "警务云平台",
                                "大模型": "警务系统",
                                "阿里": "连云港公安局",
                                "千问": "警官",
                                "模型": "系统",
                                "人工智能": "智能警务"
                            }[m.group(0).lower()]
                        }
                        for pattern, repl in replacements.items():
                            buffer = re.sub(pattern, repl, buffer)

                        # 仅在遇到标点或buffer较大时发送
                        current_time = time.time()
                        if (len(buffer) >= 10
                                or any(punc in buffer
                                       for punc in ("。", "！", "？", "\n"))
                                or (current_time - last_send_time)
                                >= 0.5):  # 最大500ms延迟
                            if buffer.strip():
                                yield buffer
                                buffer = ""
                                last_send_time = current_time

                    if buffer.strip():
                        yield buffer

                logger.info("流式响应完成")
            except Exception as e:
                logger.error(f"流式响应异常: {str(e)}")
                yield f"[ERROR] {str(e)}"

        return StreamingResponse(stream_generator(),
                                 media_type="text/event-stream",
                                 headers={
                                     "X-Content-Type-Options": "nosniff",
                                     "Connection": "keep-alive"
                                 })
    except Exception as e:
        logger.error(f"查询处理失败: {str(e)}")
        return {"error": str(e)}, 500


@app.post("/search")
async def search_internet(user_input: str = Body(..., embed=True)):
    """直接调用网络搜索API"""
    try:
        search_result = internet_search(json.dumps({"question": user_input}))
        return json.loads(search_result)
    except Exception as e:
        logger.error(f"网络搜索API调用失败: {str(e)}")
        return {"error": str(e)}, 500


@app.get("/memory")
async def get_conversation_memory():
    """获取当前对话记忆"""
    chat_engine = app.state.chat_engine if hasattr(app.state,
                                                   'chat_engine') else None
    return {
        "memory": chat_engine.memory.chat_history if chat_engine else [],
        "count": len(chat_engine.memory.chat_history) if chat_engine else 0
    }


@app.get("/health")
async def health_check():
    """服务健康检查"""
    return {
        "status": "healthy",
        "model_ready": hasattr(app.state, 'chat_engine'),
        "network_search_available": BING_AVAILABLE,
        "timestamp": datetime.now().isoformat()
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
