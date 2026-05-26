# chroma run --path ragdb --port 8001
import re
import chromadb
import logging
import uvicorn

from llama_index.core.schema import TextNode
from llama_index.core import (SimpleDirectoryReader, StorageContext,
                              VectorStoreIndex, Settings, PromptTemplate)
from llama_index.core.node_parser import SentenceSplitter
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.chat_engine import ContextChatEngine

from typing import List
from fastapi import FastAPI, Body
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

vector_store = None
index = None
chat_engine = None


def initialize_settings():
    """初始化全局设置"""
    Settings.llm = Ollama(model="qwen2.5:3b", temperature=0.7)
    Settings.embed_model = OllamaEmbedding(
        model_name="quentinz/bge-large-zh-v1.5:latest", embed_batch_size=64)


def load_documents(data_dir: str = "./data/rag_files_睿途") -> List[TextNode]:
    """加载并解析文档"""

    def my_chunking_tokenizer_fn(text: str):
        sentence_delimiters = re.compile(u'''[。？！]''')
        sentences = sentence_delimiters.split(text)
        return [s.strip() for s in sentences if s]

    try:
        documents = SimpleDirectoryReader(data_dir,
                                          file_metadata=lambda x: {
                                              "filename": x
                                          }).load_data()

        node_parser = SentenceSplitter(
            chunk_size=512,
            chunk_overlap=100,
            paragraph_separator="####",
            chunking_tokenizer_fn=my_chunking_tokenizer_fn,
        )
        return node_parser.get_nodes_from_documents(documents,
                                                    show_progress=True)
    except Exception as e:
        logger.error(f"文档加载失败: {str(e)}")
        raise


def setup_vector_store() -> ChromaVectorStore:
    """配置Chroma向量存储"""
    global vector_store
    try:
        chroma = chromadb.HttpClient(host="localhost", port=8001)
        collection = chroma.get_or_create_collection(
            name="ragdb", metadata={"hnsw:space": "cosine"})
        vector_store = ChromaVectorStore(chroma_collection=collection)
        return vector_store
    except Exception as e:
        logger.error(f"向量存储初始化失败: {str(e)}")
        raise


def build_index(nodes: List[TextNode]):
    global index, storage_context
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    index = VectorStoreIndex(nodes, storage_context=storage_context)


def warmup_model():
    """预热模型，避免首次调用延迟"""
    try:
        logger.info("开始预热模型...")
        test_input = "你好"
        response = chat_engine.chat(test_input)
        logger.info("模型预热完成")
    except Exception as e:
        logger.error(f"模型预热失败: {str(e)}")
        raise


@app.on_event("startup")
async def startup_event():
    """服务启动时执行的初始化操作"""
    try:
        initialize_settings()
        nodes = load_documents()
        setup_vector_store()
        build_index(nodes)

        custom_prompt = ('''
            # 智慧途途 - AI助手身份说明
            
            由 **北京中科睿途科技有限公司** 开发的智能助手，名字是 **智慧途途**。

            ## 角色定位
            * 专业可靠的AI助理
            * 擅长技术咨询和日常交流
            * 始终保持"智慧途途"身份
            
            ## 回答原则
            1. **专业问题**：优先使用检索到的上下文信息
            2. **日常对话**：保持简短友好的风格
            3. **长度控制**：回答限制在60字以内
            4. **信息不足**：明确告知无法提供准确答案
            5. **安全原则**：拒绝不当或有害请求

            ## 参考上下文
            ---
            {context_str}
            ---

            ## 当前问题
            {query_str}

            ## 回复规范
            * 语言自然流畅，避免机械化
            * 使用得体的专业用语
            * 严格遵守字数限制

            ## 固定回答示例：
            - 用户：你好  
            - 答案：你好！有什么问题或需求我可以帮助你解决吗？请随时告诉我。
            ''')

        custom_prompt_tmpl = PromptTemplate(custom_prompt)

        memory = ChatMemoryBuffer.from_defaults(
            token_limit=8192,  # 设置最大token限制
            chat_history=[])

        global chat_engine
        chat_engine = ContextChatEngine.from_defaults(
            retriever=index.as_retriever(similarity_top_k=5),
            memory=memory,
            system_prompt=custom_prompt_tmpl,
            node_postprocessors=[],
        )

        warmup_model()

    except Exception as e:
        logger.error(f"服务启动失败: {str(e)}")
        raise


@app.post("/query")
async def query(user_input: str = Body(..., embed=True), ):
    """处理查询请求，返回流式响应"""
    try:

        def stream_generator():
            try:
                logger.info(f"开始处理流式请求，输入内容：{user_input}")

                # 使用 chat_engine 进行对话，自动管理记忆
                response = chat_engine.stream_chat(user_input)

                buffer = []
                for text_chunk in response.response_gen:
                    if text_chunk.strip():
                        buffer.append(text_chunk)
                        if len(buffer) >= 3:
                            yield "".join(buffer)
                            buffer = []
                if buffer:
                    yield "".join(buffer)

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


@app.get("/memory")
async def get_conversation_memory():
    """获取当前对话记忆"""
    return {
        "memory": chat_engine.memory.chat_history if chat_engine else [],
        "count": len(chat_engine.memory.chat_history) if chat_engine else 0
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
