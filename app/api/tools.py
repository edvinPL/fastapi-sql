import requests
import json
import asyncio
import aiohttp
import time
from app.core.config import get_settings
from notion_client import Client
import markdown2
import math
import re
from app.api import notion
from pydantic import Field

yt_api_key = get_settings().YT_API_KEY
rapidapi_key = get_settings().RAPID_API_KEY
serpapi_key = get_settings().SERP_API_KEY

def perplexity_ai_search(query:str):
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {get_settings().PERPLEXITY_API_KEY}'
    }
    
    body = {
        'model': 'llama-3-sonar-large-32k-online',
        'messages': [
            {'role': 'system', 'content': 'Be precise and concise.'},
            {'role': 'user', 'content': query}
        ]
    }
    
    try:
        response = requests.post("https://api.perplexity.ai/chat/completions", headers=headers, json=body)
        response.raise_for_status()  # Raise an HTTPError for bad responses
        # json_data = response.json()  # Parse the JSON response
        # print(json.dumps(json_data, indent=2))  # Print formatted JSON
        return response.text
    except requests.exceptions.RequestException as e:
        print(f'Error making request: {e}')
        return None
    except json.JSONDecodeError as e:
        print(f'Error parsing JSON: {e}')
        return None

def youtube_search(region_code: str, lang:str, keywords:str):
    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&regionCode={region_code}&relevanceLanguage={lang}&q={keywords}&maxResults=15&type=video&key={yt_api_key}"
    headers = {
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Will raise an HTTPError for bad responses (4xx and 5xx)
        data = response.json()
        return data
    except requests.RequestException as error:
        print(f"An error occurred: {error}")
        return ''


def channel_details_tool(channel_id: str):
    url = f'https://www.googleapis.com/youtube/v3/channels?part=statistics&id={channel_id}&key={yt_api_key}'
    headers = {
        'Content-Type': 'application/json'
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise an HTTPError for bad responses
        data = response.json()
        return data
    except requests.RequestException as error:
        print(error)
        return ''

def youtube_video_details(video_id:str):
    url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet,statistics&id={video_id}&key={yt_api_key}"
    headers = {
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Will raise an HTTPError for bad responses
        data = response.json()
        return data
    except requests.RequestException as error:
        print(f"Error: {error}")
        return ''

def transcribe_video(video_id: str):
    url = f'https://youtube-transcriptor.p.rapidapi.com/transcript?video_id={video_id}'
    headers = {
        'x-rapidapi-key': rapidapi_key,
        'x-rapidapi-host': 'youtube-transcriptor.p.rapidapi.com'
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Will raise an HTTPError for bad responses
        result = response.text
        print(result)
        return result
    except requests.exceptions.RequestException as e:
        print(e)
        return ''

def google_promise(keyword: str, location: str, lang: str):
    keysuggest_url = f'https://google-keyword-insight1.p.rapidapi.com/keysuggest/?keyword={keyword}&location={location}&lang={lang}&min_search_vol=5000'
    globalkey_url = f'https://google-keyword-insight1.p.rapidapi.com/globalkey/?keyword={keyword}&lang={lang}&min_search_vol=5000'

    headers = {
        'x-rapidapi-key': rapidapi_key,
        'x-rapidapi-host': 'google-keyword-insight1.p.rapidapi.com'
    }

    try:
        # Fetch data from both URLs concurrently
        with requests.Session() as session:
            keysuggest_response = session.get(keysuggest_url, headers=headers)
            globalkey_response = session.get(globalkey_url, headers=headers)

            keysuggest_data = keysuggest_response.text
            globalkey_data = globalkey_response.text

        print('Keysuggest Data:', keysuggest_data)
        print('Globalkey Data:', globalkey_data)

        return {'keysuggest_data': keysuggest_data, 'globalkey_data': globalkey_data}

    except requests.RequestException as e:
        print(f"An error occurred: {e}")
        return {'keysuggest_data': '', 'globalkey_data': ''}

def Med_Articles_PMC(query: str):
    cleaned_query = query.strip()
    page_size = 25  # Number of results per page
    page = 1
    total_results = []
    total_count = 0
    max_pages = 5  # Safeguard to prevent infinite loops

    try:
        while True:
            europe_pmc_url = (f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?"
                              f"query={requests.utils.quote(cleaned_query)}&format=json&pageSize={page_size}&page={page}")
            print(f"Searching Europe PMC for query: {cleaned_query}, page: {page}")
            response = requests.get(europe_pmc_url)

            if not response.ok:
                response_text = response.text
                raise Exception(f"Europe PMC request failed with status {response.status_code}: {response_text}")

            europe_pmc_data = response.json()
            print(f"Europe PMC response for page {page}: {json.dumps(europe_pmc_data, indent=2)}")

            if page == 1:
                total_count = europe_pmc_data.get('hitCount', 0)
                print(f"Total count of results: {total_count}")

            results = europe_pmc_data.get('resultList', {}).get('result', [])
            if results:
                total_results.extend(results)
                print(f"Accumulated results count: {len(total_results)}")
            else:
                print(f"No results found on page {page}")
                break

            page += 1
            if page > max_pages:
                print(f"Reached maximum page limit of {max_pages}")
                break

            if len(total_results) >= total_count:
                break

        return json.dumps({'europePmc': total_results}, indent=2)
    
    except Exception as e:
        print("Error fetching articles:", e)
        return json.dumps({'status': 'error', 'reason': str(e)}, indent=2)


async def delay(ms):
    await asyncio.sleep(ms / 1000.0)

async def search_papers(query):
    url = f'https://api.semanticscholar.org/graph/v1/paper/search?query={aiohttp.web.Request.query_string}'
    headers = {
        'Content-Type': 'application/json'
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            if response.status != 200:
                print(f'Error searching papers: HTTP error! status: {response.status}')
                return []
            
            data = await response.json()
            if 'data' not in data:
                print('Error searching papers: No data found in the response')
                return []
            
            return [paper['paperId'] for paper in data['data']]

async def get_paper_details(paper_ids):
    url = 'https://api.semanticscholar.org/graph/v1/paper/batch?fields=title,tldr,openAccessPdf,abstract,year'
    headers = {
        'Content-Type': 'application/json'
    }
    payload = {
        'ids': paper_ids
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as response:
            if response.status != 200:
                print(f'Error getting paper details: HTTP error! status: {response.status}')
                return []
            
            data = await response.json()
            if not isinstance(data, list):
                print('Error getting paper details: Invalid data format received from the API')
                return []
            
            return data

async def Semantic_Scholar_Tool(query: str):
    print('Query:', query)
    paper_ids = await search_papers(query)
    print('Paper IDs:', paper_ids)
    
    if not paper_ids:
        return 'No papers found'
    
    paper_details = await get_paper_details(paper_ids)
    print('Paper Details:', paper_details)
    return json.dumps(paper_details, indent=2)

# Function to extract keywords from the input query
def extract_keywords(query):
    stop_words = {'the', 'is', 'at', 'which', 'on', 'and', 'a', 'an', 'in', 'with', 'to', 'for', 'of', 'by', 'from'}
    words = query.split()
    filtered_words = [word for word in words if word.lower() not in stop_words]
    return ' '.join(filtered_words)

# Function to handle HTTP requests with retries and exponential backoff
def fetch_with_retry(url, retries=3, backoff=3.0):
    headers = {'Accept': 'application/json'}
    for i in range(retries):
        try:
            response = requests.get(url, headers=headers)
            if response.ok:
                return response
            elif response.status_code == 429:
                print(f'Rate limit exceeded. Retrying in {int(backoff * 1000)}ms...')
                time.sleep(backoff)
                backoff *= 2  # Exponential backoff
            else:
                response.raise_for_status()
        except requests.RequestException as e:
            print(f'Error: {e}')
            if i == retries - 1:
                raise
    raise RuntimeError('Max retries exceeded')

# Function to search for PubMed articles
def PubMed_Tool(query: str):
    cleaned_query = extract_keywords(query.strip())
    page_size = 25  # Number of results per page
    page = 0
    total_results = []
    total_count = 0
    max_pages = 5  # Safeguard to prevent infinite loops

    try:
        while True:
            pubmed_url = (
                f'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={requests.utils.quote(cleaned_query)}'
                f'&retmode=json&retmax={page_size}&retstart={page * page_size}'
            )
            print(f'Searching PubMed for query: {cleaned_query}, page: {page}')
            pubmed_response = fetch_with_retry(pubmed_url)
            pubmed_data = pubmed_response.json()
            print(f'PubMed response for page {page}: {json.dumps(pubmed_data, indent=2)}')

            if page == 0:
                total_count = int(pubmed_data['esearchresult']['count'])

            if pubmed_data['esearchresult']['idlist']:
                ids = ','.join(pubmed_data['esearchresult']['idlist'])
                details_url = (
                    f'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={ids}&retmode=json'
                )
                details_response = fetch_with_retry(details_url)
                details_data = details_response.json()
                total_results.extend(details_data['result'])
                print(f'Accumulated results count: {len(total_results)}')
            else:
                print(f'No results found on page {page}')
                break

            page += 1
            if page >= max_pages:
                print(f'Reached maximum page limit of {max_pages}')
                break

            if len(total_results) >= total_count:
                break

        return json.dumps({
            'pubMed': total_results
        }, indent=2)
    except Exception as e:
        print(f"Error fetching articles: {e}")
        return json.dumps({'status': 'error', 'reason': str(e)}, indent=2)


def Google_Scholar_Tool(query: str, num_results=10):
    
    endpoint = "https://serpapi.com/search"
    params = {
        'engine': 'google_scholar',
        'q': query,
        'num': num_results,
        'api_key': serpapi_key
    }
    
    try:
        response = requests.get(endpoint, params=params)
        response.raise_for_status()  # Raise an HTTPError for bad responses
        result = response.json()
        
        if 'organic_results' not in result:
            raise ValueError("Unexpected API response format")
        
        results = [
            {
                'title': res.get('title'),
                'link': res.get('link'),
                'snippet': res.get('snippet'),
                'publication_info': res.get('publication_info')
            }
            for res in result['organic_results']
        ]
        
        return results
    except Exception as e:
        print(f"Error searching Google Scholar: {e}")
        return []


def avatar_information(query:str):
    API_URL = get_settings().QDRANT_FLOWISE_URL
    input = {
        "question": query,
        "overrideConfig": {
            "qdrantApiKey": get_settings().QDRANT_API_KEY,
            "qdrantServerUrl": get_settings().QDRANT_URL,
            "qdrantCollection": "Avatar",
            "contentPayloadKey": "content",
            "metadataPayloadKey": "metadata",
            "description": "use it to find out more about our target audience, our avatars. Their information about interests, age, employment and other information about them.",
            "name": "Avatar"
        }
    }

    response = requests.post(API_URL, json=input)
    return response.json()

def ultimatebrain_information(query:str):
    API_URL = get_settings().QDRANT_FLOWISE_URL
    input = {
        "question": query,
        "overrideConfig": {
            "qdrantApiKey": get_settings().QDRANT_API_KEY,
            "qdrantServerUrl": get_settings().QDRANT_URL,
            "qdrantCollection": "ScriptingBrain",
            "contentPayloadKey": "content",
            "metadataPayloadKey": "metadata",
            "description": "This is the scripting_brain that contains a lot of curated distilled knowledge about scripting, content creation, AI and optimal way to write youtube video scripts. It contains a lot of viable useful crucial key information for perfect youtube video masterpiece creation process. Especially titles, thumbnails, hooks, payoffs, cognitive bias, retention methods etc.",
            "name": "scripting_brain"
        }
    }

    response = requests.post(API_URL, json=input)
    return response.json()

def sugarbrain_information(query:str):
    API_URL = get_settings().QDRANT_FLOWISE_URL
    input = {
        "question": query,
        "overrideConfig": {
            "qdrantApiKey": get_settings().QDRANT_API_KEY,
            "qdrantServerUrl": get_settings().QDRANT_URL,
            "qdrantCollection": "Sugar",
            "contentPayloadKey": "content",
            "metadataPayloadKey": "metadata",
            "description": "Use it to retrieve all the important information for current script in terms of scientific knowledge. It contains research papers, notes, insights, conclusions, scientific review articles and much more relating to current problem we are trying to tackle in the video. Use it always.",
            "name": "Ultimate_Brain"
        }
    }

    response = requests.post(API_URL, json=input)
    return response.json()


def markdown_to_notion_blocks(markdown_content):
    """
    Convert markdown content to Notion block objects directly without HTML conversion.
    """
    lines = markdown_content.splitlines()
    blocks = []
    
    for line in lines:
        line = line.strip()

        # Handle Headers
        if line.startswith("# "):
            blocks.append({
                "object": "block",
                "type": "heading_1",
                "heading_1": {
                    "rich_text": [{"type": "text", "text": {"content": line[2:].strip()}}]
                }
            })
        elif line.startswith("## "):
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": line[3:].strip()}}]
                }
            })
        elif line.startswith("### "):
            blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {
                    "rich_text": [{"type": "text", "text": {"content": line[4:].strip()}}]
                }
            })
        
        # Handle Unordered Lists
        elif line.startswith("- "):
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": line[2:].strip()}}]
                }
            })

        # Handle Horizontal Rules
        elif line == "---":
            blocks.append({
                "object": "block",
                "type": "divider",
                "divider": {}
            })

        # Handle Bold Text
        elif "**" in line:
            bold_text = re.sub(r"\*\*(.*?)\*\*", r"\1", line)
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{
                        "type": "text",
                        "text": {"content": bold_text}
                    }]
                }
            })

        # Handle Regular Paragraphs
        else:
            if line:  # Avoid empty lines
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": line}}]
                    }
                })

    return blocks

def store_markdown_in_notion_research(token, database_id, markdown_content, page_title, doi_options):
    """
    Store markdown content as a page in the Notion database with batch handling for API limits.
    
    Parameters:
    - token: Notion API token.
    - database_id: The ID of the target Notion database.
    - markdown_content: Markdown content to store in the page.
    - page_title: Title of the page.
    """
    # Initialize Notion client
    notion = Client(auth=token)

    # Convert markdown content to Notion blocks
    blocks = markdown_to_notion_blocks(markdown_content)

    # Create the first page with the title and the first batch of blocks (up to 100 blocks)
    page_properties = {
        "parent": {"database_id": database_id},
        "properties": { "Name":{
            "type": "title",
            "title": [
                {
                    "type": "text",
                    "text": {
                        "content": page_title
                    }
                }
            ]},
            "Tags": {
      "multi_select": 
        doi_options
      
    }
        }
    }

    # Split blocks into chunks of 100 blocks max
    batch_size = 100
    num_batches = math.ceil(len(blocks) / batch_size)

    # Create the page with the first batch
    response = notion.pages.create(
        **page_properties,
        children=blocks[:batch_size]
    )

    # If there are more blocks, append them in additional requests
    if num_batches > 1:
        page_id = response['id']
        for i in range(1, num_batches):
            notion.blocks.children.append(
                block_id=page_id,
                children=blocks[i*batch_size:(i+1)*batch_size]
            )

    return response

def store_markdown_in_notion(token, database_id, markdown_content, page_title):
    """
    Store markdown content as a page in the Notion database with batch handling for API limits.
    
    Parameters:
    - token: Notion API token.
    - database_id: The ID of the target Notion database.
    - markdown_content: Markdown content to store in the page.
    - page_title: Title of the page.
    """
    # Initialize Notion client
    notion = Client(auth=token)

    # Convert markdown content to Notion blocks
    blocks = markdown_to_notion_blocks(markdown_content)

    # Create the first page with the title and the first batch of blocks (up to 100 blocks)
    page_properties = {
        "parent": {"database_id": database_id},
        "properties": {
            "title": [
                {
                    "type": "text",
                    "text": {
                        "content": page_title
                    }
                }
            ]
        }
    }

    # Split blocks into chunks of 100 blocks max
    batch_size = 100
    num_batches = math.ceil(len(blocks) / batch_size)

    # Create the page with the first batch
    response = notion.pages.create(
        **page_properties,
        children=blocks[:batch_size]
    )

    # If there are more blocks, append them in additional requests
    if num_batches > 1:
        page_id = response['id']
        for i in range(1, num_batches):
            notion.blocks.children.append(
                block_id=page_id,
                children=blocks[i*batch_size:(i+1)*batch_size]
            )

    return response

def save_in_notion(content:str, 
    title:str , doi: str):
    token = get_settings().NOTION_TOKEN  # Your Notion integration token
    database_id = get_settings().NOTION_DATABASE_ID_RESEARCH
      # Split the DOIs by comma and strip any whitespace
    doi_list = [doi.strip() for doi in doi.split(",") if doi.strip()]
    
    # Prepare DOI options for Notion
    doi_options = [{"name": doi} for doi in doi_list]
    response = store_markdown_in_notion_research(token, database_id, content, title, doi_options)

    if response:
        return response
    else:
        return "Failed to upsert"

def search_notion_pages(query: str):
    token = get_settings().NOTION_TOKEN  # Your Notion integration token
    notion = Client(auth=token)

    # Construct the search request
    response = notion.search(query=query)

    # Filter results to get only pages
    pages = [result for result in response.get('results', []) if result['object'] == 'page']

    return pages

# def save_in_notion(content:str, title:str):
#     token = get_settings().NOTION_TOKEN  # Your Notion integration token
#     database_id = get_settings().NOTION_DATABASE_ID_RESEARCH

#     response = store_markdown_in_notion(token, database_id, content, title)

#     if response:
#         return response
#     else:
#         return "Failed to upsert"

def save_outputs_in_notion(content:str, title:str):
    token = get_settings().NOTION_TOKEN  # Your Notion integration token
    database_id = get_settings().NOTION_DATABASE_ID_OUTPUTS

    response = store_markdown_in_notion(token, database_id, content, title)

    if response:
        return response
    else:
        return "Failed to upsert"


async def upsert_to_qdrant(page_id:str):    
    return await notion.process_notion_data(page_id, "page", "incremental")

# def extract_notion_page_content( page_url: str):
#     """
#     Extract content from a Notion page given its URL.

#     Parameters:
#     - token: Notion API token.
#     - page_url: URL of the Notion page.

#     Returns:
#     - The content of the page as a string, or an error message if the request fails.
#     """
#     token = get_settings().NOTION_TOKEN  # Your Notion integration token
#     # Extract the page ID from the URL
#     page_id_match = re.search(r'([a-zA-Z0-9]+)$', page_url)
#     if not page_id_match:
#         return "Invalid Notion page URL."

#     page_id = page_id_match.group(0)

#     # Set up the API endpoint
#     url = f"https://api.notion.com/v1/pages/{page_id}"
#     headers = {
#         "Authorization": f"Bearer {token}",
#         "Content-Type": "application/json",
#         "Notion-Version": "2022-06-28"  # Use the latest version of the API
#     }

#     # Make the API request
#     response = requests.get(url, headers=headers)

#     if response.status_code != 200:
#         return f"Error fetching page: {response.status_code} - {response.text}"

#     # Extract and return content from the response
#     data = response.json()
#     # content = extract_content_from_response(data)
    
#     return data

def extract_notion_page_content(page_url: str):
    """
    Extract content from a Notion page given its URL.

    Parameters:
    - token: Notion API token.
    - page_url: URL of the Notion page.

    Returns:
    - The content of the page as a string, or an error message if the request fails.
    """
    token = get_settings().NOTION_TOKEN  # Your Notion integration token
    # Extract the page ID from the URL
    page_id_match = re.search(r'([a-f0-9]{32})$', page_url)
    if not page_id_match:
        return "Invalid Notion page URL."

    page_id = page_id_match.group(0)

    # Set up the API endpoint for fetching block children
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"  # Use the latest version of the API
    }

    # Make the API request
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        return f"Error fetching page content: {response.status_code} - {response.text}"

    # Extract and return content from the response
    data = response.json()
    content = extract_content_from_response(data)
    
    return content

def extract_content_from_response(data):
    """
    Extract content from the API response data.

    Parameters:
    - data: The JSON response from the Notion API.

    Returns:
    - A string representing the extracted content.
    """
    content = []
    
    # Traverse the blocks and extract text
    if "results" in data:
        for block in data['results']:
            if block['type'] == 'paragraph':
                text = ''.join([t['text']['content'] for t in block['paragraph']['rich_text']])
                content.append(text)
            elif block['type'] == 'heading_1':
                text = ''.join([t['text']['content'] for t in block['heading_1']['rich_text']])
                content.append(f"# {text}")
            elif block['type'] == 'heading_2':
                text = ''.join([t['text']['content'] for t in block['heading_2']['rich_text']])
                content.append(f"## {text}")
            elif block['type'] == 'heading_3':
                text = ''.join([t['text']['content'] for t in block['heading_3']['rich_text']])
                content.append(f"### {text}")
            elif block['type'] == 'bulleted_list_item':
                text = ''.join([t['text']['content'] for t in block['bulleted_list_item']['rich_text']])
                content.append(f"- {text}")
            # Add more block types as needed
    
    return '\n'.join(content)