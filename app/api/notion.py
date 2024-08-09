from langchain_community.document_loaders.notiondb import NotionDBLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import tiktoken
from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore
import logging
import time
from dotenv import load_dotenv
import os
from llama_index.readers.notion import NotionPageReader
from langchain.schema import Document as LangChainDocument
import hashlib
from uuid import uuid4
from enum import Enum
from datetime import datetime, timedelta
import json
from app.core.config import get_settings
from langchain.indexes import SQLRecordManager, aindex
from sqlalchemy.ext.asyncio import create_async_engine
from qdrant_client import QdrantClient

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("uvicorn")

# Load environment variables
load_dotenv()

NOTION_TOKEN = get_settings().NOTION_TOKEN
CHUNK_SIZE = get_settings().CHUNK_SIZE
CHUNK_OVERLAP = get_settings().CHUNK_OVERLAP
EMBEDDING_MODEL = get_settings().EMBEDDING_MODEL
OPENAI_API_KEY = get_settings().OPENAI_API_KEY

# Global variables
docs = []
length_of_docs = 0
total_cost = 0
total_embedding_cost = 0


class CleanupMode(str, Enum):
    NONE = "None"
    INCREMENTAL = "Incremental"
    FULL = "Full"


def generate_source_id(content, metadata):
    """Generate a unique source ID based on content and metadata."""
    unique_string = f"{content}{str(metadata)}".encode('utf-8')
    return hashlib.md5(unique_string).hexdigest()


def convert_llamaindex_to_langchain(llamaindex_doc):
    """Convert a LlamaIndex document to a LangChain document."""
    content = llamaindex_doc.text
    langchain_doc = LangChainDocument(
        page_content=content,
        metadata=llamaindex_doc.metadata
        if hasattr(llamaindex_doc, 'metadata') else {})
    return langchain_doc


async def load_documents_from_notion_db(document_id):
    logger.info("Loading documents from notion")
    start_time = time.time()

    loader = NotionDBLoader(
        integration_token=NOTION_TOKEN,
        database_id=document_id,
        request_timeout_sec=60,  # optional, defaults to 10
    )

    docs = loader.load()

    length_of_docs = len(docs)

    process_time = time.time() - start_time

    logger.info(
        f"{length_of_docs} documents loaded - Duration: {process_time:.4f} seconds"
    )

    return docs


async def load_documents_from_notion_page(document_id):
    logger.info("Loading documents from notion")
    start_time = time.time()

    reader = NotionPageReader(integration_token=NOTION_TOKEN)

    documents = reader.load_data(page_ids=[document_id], )

    docs = []
    
    for document in documents:
        docs.append(convert_llamaindex_to_langchain(document))

    length_of_docs = len(docs)

    process_time = time.time() - start_time
    logger.info(
        f"{length_of_docs} documents loaded - Duration: {process_time:.4f} seconds"
    )

    return docs

async def split_documents(docs):
    logger.info("Splitting documents into chunks")
    start_time = time.time()

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )

    split_docs = text_splitter.split_documents(docs)

    length_of_docs = len(split_docs)

    process_time = time.time() - start_time

    logger.info(
        f"{length_of_docs} documents in total after splitting - Duration: {process_time:.4f} seconds"
    )

    return split_docs

async def calculate_pinecone_cost(docs):
    logger.info("Calculating embeddings cost")

    # Initialize tokenizer for a specific OpenAI model
    encoder = tiktoken.encoding_for_model(EMBEDDING_MODEL)

    # Sample documents
    documents = []

    for doc in docs:
        documents.append(doc.page_content)

    def count_tokens(text, encoder):
        tokens = encoder.encode(text)
        return len(tokens)

    def calculate_embedding_cost(total_tokens, cost_per_token):
        return total_tokens * cost_per_token

    # Calculate total tokens
    total_tokens = sum(count_tokens(doc, encoder) for doc in documents)
    total_vectors = len(documents)

    # Pinecone cost parameters
    storage_cost_per_vector = 0.000001  # Storage cost per vector
    read_cost_per_vector = 0.000008  # Read cost per vector
    write_cost_per_vector = 0.000002  # Write cost per vector
    cost_per_token = 0.00000013  # $0.130 per 1 million tokens

    # Calculate costs
    storage_cost = total_vectors * storage_cost_per_vector
    read_cost = total_vectors * read_cost_per_vector
    write_cost = total_vectors * write_cost_per_vector
    
    total_cost = storage_cost + read_cost + write_cost
    total_embedding_cost = calculate_embedding_cost(total_tokens,
                                                    cost_per_token)

    return {
        "total_pinecone_cost" : total_cost,
        "total_embedding_cost" : total_embedding_cost
    }

from sqlalchemy import create_engine
from langchain_qdrant import Qdrant

async def cleanup_and_upsert_documents(docs, cleanup_mode):
    logger.info(
        f"Upserting documents to Qdrant with {cleanup_mode} cleanup mode")
    start_time = time.time()

    embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY,
                                  model=EMBEDDING_MODEL)

    url = get_settings().QDRANT_URL
    api_key = get_settings().QDRANT_API_KEY

    client = QdrantClient(url=url, api_key=api_key)
    
    collection_name=get_settings().QDRANT_COLLECTION_NAME

    vectorstore = Qdrant(collection_name=collection_name, client=client, embeddings=embeddings)

    namespace = "qdrant/my_docs"

    engine = create_async_engine(get_settings().sqlalchemy_database_uri.render_as_string(hide_password=False))

    record_manager = SQLRecordManager(
        namespace, engine=engine
    )

    await record_manager.acreate_schema()
    mode = cleanup_mode.lower() 
    
    result = {}

    if mode == "incremental":
        result = await aindex(
            docs,
            record_manager,
            vectorstore,
            cleanup="incremental",
            source_id_key="id"
        )
    elif mode == "full":
        result = await aindex(
            docs,
            record_manager,
            vectorstore,
            cleanup="full",
            source_id_key="id"
        )
    elif mode == "none":
        result = await aindex(
            docs,
            record_manager,
            vectorstore,
            cleanup=None,
            source_id_key="id"
        )
    else:
        raise Exception("Incorrect cleanup mode")
    
    return result