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
from sqlalchemy import create_engine
from langchain_qdrant import Qdrant
from typing import Dict, Any, List, Generator, Tuple
import concurrent.futures
from requests.exceptions import HTTPError

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


def load_documents_from_notion_page(document_id):
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

def split_documents(docs):
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

def calculate_cost(docs):
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
        "total_embedding_cost" : total_embedding_cost
    }

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

# def load_notion_db_in_chunks(
#     integration_token: str,
#     database_id: str,
#     doc_type: str,
#     chunk_size: int = 10,
#     filter_object: Dict[str, Any] = None
# ) -> Generator[List[Dict[str, Any]], None, None]:
#     loader = NotionDBLoader(
#         integration_token=NOTION_TOKEN,
#         database_id=database_id,
#         request_timeout_sec=90,
#     )

#     NOTION_BASE_URL = "https://api.notion.com/v1"
#     DATABASE_URL = NOTION_BASE_URL + f"/databases/{database_id}/query"
    
#     def page_generator():
#         query_dict = {"page_size": chunk_size}
#         while True:
#             data = loader._request(
#                 DATABASE_URL,
#                 method="POST",
#                 query_dict=query_dict,
#             )
#             yield from data.get("results", [])
#             if not data.get("has_more"):
#                 break
#             query_dict["start_cursor"] = data.get("next_cursor")

#     chunk = []
#     for page in page_generator():
#         chunk.append(page)
#         if len(chunk) == chunk_size:
#             yield chunk
#             chunk = []

#     if chunk:  # Yield any remaining pages
#         yield chunk

from threading import Lock

class RateLimiter:
    def __init__(self, rate_per_second):
        self.rate_per_second = rate_per_second
        self.max_tokens = rate_per_second
        self.tokens = rate_per_second
        self.last_check = time.time()
        self.lock = Lock()

    def _refill(self):
        now = time.time()
        elapsed = now - self.last_check
        self.tokens += elapsed * self.rate_per_second
        self.tokens = min(self.tokens, self.max_tokens)
        self.last_check = now

    def acquire(self):
        with self.lock:
            self._refill()
            if self.tokens < 1:
                return False
            self.tokens -= 1
            return True

    def wait_for_token(self):
        while not self.acquire():
            time.sleep(0.1)  # Wait a short while before retrying

rate_limiter = RateLimiter(rate_per_second=2)


def process_chunk(chunk: List[Dict[str, Any]], loader: NotionDBLoader) -> List:
    documents = []
    def load_page_and_process(page_summary: Dict[str, Any]):
        rate_limiter.wait_for_token()  # Ensure the request respects the rate limit
        retries = 5
        base_delay = 0.5
        
        for attempt in range(retries):
            try:
                document = loader.load_page(page_summary)  # Perform the API request
                # if response.status_code == 429:  # Check if rate limit exceeded
                name = document.metadata.get("name", "Unknown")
                print(f"Processing document: {name[:50]}...")
                return document

            except HTTPError as e:
                if e.response.status_code == 429:
                    # If rate limit error and no Retry-After header, use exponential backoff
                    # retry_after = base_delay * (2 ** attempt)
                    # print(f"Rate limit exceeded. Retrying in {retry_after} seconds...")
                    # time.sleep(retry_after)
                    retry_after = e.response.headers.get('Retry-After')  # Get Retry-After header
                    if retry_after:
                        retry_after = int(float(retry_after))  # Convert to integer (seconds)
                    else:
                        retry_after = base_delay * (2 ** attempt)  # Fallback to exponential backoff if header missing

                    print(f"Rate limit exceeded. Retrying in {retry_after} seconds...")
                    time.sleep(retry_after)  # Wait for the specified duration
                    continue
                else:
                    print(f"Error loading page {page_summary['id']}: {e}")
                return None
            except Exception as e:
                print(f"Unexpected error: {e}")
                return None

    start_time = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_to_page_summary = {executor.submit(load_page_and_process, page): page for page in chunk}
        
        for future in concurrent.futures.as_completed(future_to_page_summary):
            page = future_to_page_summary[future]
            try:
                result = future.result()
                if result is not None:
                    documents.append(result)
            except Exception as e:
                print(f"Error processing page {page['id']}: {e}")

    print(f"Time taken to process chunk: {time.time() - start_time:.2f} seconds")

    split_docs = split_documents(documents)

    return split_docs

def load_notion_db_in_chunks(
    integration_token: str,
    database_id: str,
    doc_type: str,
    chunk_size: int = 10,
) -> Generator[List[Dict[str, Any]], None, None]:
    loader = NotionDBLoader(
        integration_token=NOTION_TOKEN,
        database_id=database_id,
        request_timeout_sec=90,
    )

    NOTION_BASE_URL = "https://api.notion.com/v1"
    DATABASE_URL = NOTION_BASE_URL + f"/databases/{database_id}/query"
    
    # def page_generator():
    #     query_dict = {"page_size": chunk_size}
    #     while True:
    #         data = loader._request(
    #             DATABASE_URL,
    #             method="POST",
    #             query_dict=query_dict,
    #         )
    #         yield from data.get("results", [])
    #         if not data.get("has_more"):
    #             break
    #         query_dict["start_cursor"] = data.get("next_cursor")

    def page_generator():
        query_dict = {"page_size": chunk_size}
        retries = 5
        base_delay = 0.5
        
        while True:
            for attempt in range(retries):
                try:
                    data = loader._request(
                        DATABASE_URL,
                        method="POST",
                        query_dict=query_dict,
                    )
                    
                    if hasattr(data, 'status_code') and data.status_code == 429:
                        retry_after = data.headers.get('Retry-After')
                        if retry_after:
                            retry_after = int(float(retry_after))  # Convert to integer (seconds)
                        else:
                            retry_after = base_delay * (2 ** attempt)  # Fallback to exponential backoff
                        
                        print(f"Rate limit exceeded. Retrying in {retry_after} seconds...")
                        time.sleep(retry_after)
                        break  # Retry after waiting
                                            
                    yield from data.get("results", [])
                    if not data.get("has_more"):
                        return
                    query_dict["start_cursor"] = data.get("next_cursor")
                    break  # Exit retry loop on success
                except HTTPError as e:
                    if e.response.status_code == 429:
                        # If rate limit error and no Retry-After header, use exponential backoff
                        # retry_after = base_delay * (2 ** attempt)
                        # print(f"Rate limit exceeded. Retrying in {retry_after} seconds...")
                        # time.sleep(retry_after)
                        retry_after = e.response.headers.get('Retry-After')  # Get Retry-After header
                        if retry_after:
                            retry_after = int(float(retry_after))  # Convert to integer (seconds)
                        else:
                            retry_after = base_delay * (2 ** attempt)  # Fallback to exponential backoff if header missing

                        print(f"Rate limit exceeded. Retrying in {retry_after} seconds...")
                        time.sleep(retry_after)  # Wait for the specified duration
                        continue
                    else:
                        print(f"Error loading page {page_summary['id']}: {e}")
                    return None
                except Exception as e:
                    if attempt == retries - 1:
                        # Log and handle error if max retries reached
                        print(f"Error in API request: {e}")
                        raise  # Reraise the exception after retries
                    else:
                        print(f"Retrying due to error: {e}")

    chunk = []
    for page in page_generator():
        chunk.append(page)
        if len(chunk) == chunk_size:
            yield chunk
            chunk = []

    if chunk:  # Yield any remaining pages
        yield chunk

async def process_notion_data(database_id: str, doc_type: str, cleanup_mode:str):
    logger.info("Upserting notion documents")
    start_time = time.time()

    loader = NotionDBLoader(
        integration_token=NOTION_TOKEN,
        database_id=database_id,
        request_timeout_sec=60,
    )

    def process_chunk_wrapper(chunk: List[Dict[str, Any]]):
        try:
            return process_chunk(chunk, loader)
        except Exception as e:
            logger.error(f"Error processing chunk: {e}")
            return []
    
    total_docs = []
    chunk_size = 10  # Number of pages per chunk
    
    if doc_type == "database":
        chunks = load_notion_db_in_chunks(NOTION_TOKEN, database_id, doc_type, chunk_size=chunk_size)

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_to_chunk = {executor.submit(process_chunk_wrapper, chunk): chunk for chunk in chunks}
            
            for future in concurrent.futures.as_completed(future_to_chunk):
                try:
                    split_docs = future.result()
                    total_docs.extend(split_docs)
                    logger.info(f"Chunk processed with {len(split_docs)} documents split.")
                except Exception as e:
                    logger.error(f"Error during chunk processing: {e}")

    elif doc_type == "page":
        total_docs = split_documents(load_documents_from_notion_page(notion_id))
    else:
        raise HTTPException(status_code=400,
                            detail="Invalid document type")

    cost_info = calculate_cost(total_docs)
    logger.info(f"Total Embedding Cost: {cost_info}")

    vectordb_result = await cleanup_and_upsert_documents(total_docs, cleanup_mode)

    process_time = time.time() - start_time
    logger.info(f"Total documents: {len(total_docs)} - Duration: {process_time:.4f} seconds")

    return {"Embedding_cost" : cost_info["total_embedding_cost"], "Qdrant_result": vectordb_result, "total_vectors": len(total_docs)}



# ---------------------- This works made loading of 30 pages db to 93 seconds from 130s -----------------------
# def fetch_chunk(
#     integration_token: str,
#     database_id: str,
#     chunk_size: int,
#     start_cursor: str = None
# ) -> Tuple[List[Dict[str, Any]], bool, str]:
#     loader = NotionDBLoader(
#         integration_token=integration_token,
#         database_id=database_id,
#         request_timeout_sec=90,
#     )
#     NOTION_BASE_URL = "https://api.notion.com/v1"
#     DATABASE_URL = NOTION_BASE_URL + f"/databases/{database_id}/query"

#     query_dict = {"page_size": chunk_size}
#     if start_cursor:
#         query_dict["start_cursor"] = start_cursor

#     data = loader._request(DATABASE_URL, method="POST", query_dict=query_dict)
#     results = data.get("results", [])
#     has_more = data.get("has_more", False)
#     next_cursor = data.get("next_cursor", None)
#     return results, has_more, next_cursor

# def load_chunks(
#     integration_token: str,
#     database_id: str,
#     chunk_size: int = 10
# ) -> List[List[Dict[str, Any]]]:
#     chunks = []
#     start_cursor = None

#     while True:
#         results, has_more, next_cursor = fetch_chunk(integration_token, database_id, chunk_size, start_cursor)
#         if results:
#             chunks.append(results)
#         if not has_more:
#             break
#         start_cursor = next_cursor

#     return chunks

# def process_chunk(chunk: List[Dict[str, Any]], loader: NotionDBLoader) -> List:
#     documents = [loader.load_page(page) for page in chunk]
#     # Process documents here
#     for doc in documents:
#         print(f"Processing document: {doc.metadata.get("name")[:50]}...")

#     split_docs = split_documents(documents)
#     return split_docs

# def process_notion_data(database_id: str, doc_type: str):
#     logger.info("Upserting notion documents")
#     start_time = time.time()

#     loader = NotionDBLoader(
#         integration_token=NOTION_TOKEN,
#         database_id=database_id,
#         request_timeout_sec=60,
#     )

#     # Load chunks
#     logger.info("Loading chunks...")
#     chunks = load_chunks(NOTION_TOKEN, database_id, chunk_size=10)
#     logger.info(f"Total {len(chunks)} chunks loaded.")

#     total_docs = 0

#     # Process chunks concurrently
#     with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
#         future_to_chunk = {}
#         for i, chunk in enumerate(chunks):
#             future = executor.submit(process_chunk, chunk, loader)
#             future_to_chunk[future] = i  # Track which chunk index is being processed

#         for future in concurrent.futures.as_completed(future_to_chunk):
#             try:
#                 split_docs = future.result()
#                 total_docs += len(split_docs)
#                 logger.info(f"Chunk {future_to_chunk[future]} processed with {len(split_docs)} documents split.")
#                 # Handle split_docs here, e.g., upsert to Pinecone
#             except Exception as e:
#                 logger.error(f"Error processing chunk: {e}")

#     process_time = time.time() - start_time
#     logger.info(f"Total documents: {total_docs} - Duration: {process_time:.4f} seconds")

# --------------------------------------------------------------------

