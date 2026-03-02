import requests
import urllib.parse
from markitdown import MarkItDown
from agents import function_tool
from myagents.tools_helpers import *
from myagents.base_agent import BaseAgent, system_prompt_tool_usage
from duckduckgo_search import DDGS

from PySide6.QtCore import QCoreApplication
# tr_context = "web_agent"

import warnings
warnings.filterwarnings("ignore", category=RuntimeWarning, module="duckduckgo_search")

class WebAgent(BaseAgent):
    def get_name(self) -> str:
        #return "Web Agent can read webpages and PDFs from the internet by URL"
        return "Web Agent"
    
    def get_handoff_description(self):
        return "Can search the web and read webpages or PDFs from the internet."
    
    def get_system_prompt(self) -> str:
        return """
        You can read web-pages and PDFs from the internet by URL.
        You may follow up tp 3 links to answer user-questions.
        """ + system_prompt_tool_usage
    
    def get_tools(self) -> list:
        return [web_search, read_webpage_from_url, read_pdf_from_url, get_user_info, get_system_time]

webpage_cache = {}

@function_tool
async def web_search(query: str) -> str:
    """Search the web"""
    cache_url = "ddgsearch:" + query
    if cache_url in webpage_cache:
        return webpage_cache[cache_url]

    parameters: List[Dict[str, str]] = []    
    parameters.append({"name": "query", "value": query})

    if not confirm_tools_call(QCoreApplication.translate("web_agent", "Websuche"), parameters, True):
        return cancelled_by_user_message()
    
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, region="wt-wt", safesearch="off", max_results=10))            
            # JSON zurückliefern, ähnlich wie bei deiner bisherigen API-Version
            ret = json.dumps(results, ensure_ascii=False, indent=2)
            webpage_cache[cache_url] = ret
            return ret

    except Exception as e:
        return f"Error: {str(e)}"

@function_tool
async def read_webpage_from_url(url: str) -> str:
    """Read a webpage and return the main article text"""
    if url in webpage_cache:
        return webpage_cache[url]
    
    parameters: List[Dict[str, str]] = []    
    parameters.append({"name": "url", "value": url})
    if not confirm_tools_call(QCoreApplication.translate("web_agent", "Webseite abrufen"), parameters, True):
        return cancelled_by_user_message()
    return get_webpage(url)

@function_tool
async def read_pdf_from_url(url: str) -> str:
    """Read a PDF and return the content as text"""
    if url in webpage_cache:
        return webpage_cache[url]

    parameters: List[Dict[str, str]] = []    
    parameters.append({"name": "url", "value": url})    

    if not confirm_tools_call(QCoreApplication.translate("web_agent", "PDF abrufen"), parameters, True):
        return cancelled_by_user_message()
    return get_webpage(url)


def get_webpage(url: str) -> str:
    if url in webpage_cache:
        return webpage_cache[url]
    
    session = requests.Session()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/114.0.0.0 Safari/537.36"
        )
    }
    session.cookies.set("cookie_consent", "true", domain=".example.com")

    try:                
        #cookies = {"cookie_consent": "true"}
        response = session.get(url, headers=headers, allow_redirects=True, timeout=20)
        response.raise_for_status()
        md = MarkItDown()
        result = md.convert(response)
        text = result.text_content
        webpage_cache[url] = text
        return text
    except requests.RequestException as e:
        return f"Error loading page: {e}"
    except Exception as e:        
        return getattr(e, "msg", str(e))
    
'''
from html2text import HTML2Text

def html_to_markdown(html: str) -> str:
    parser = HTML2Text()
    parser.ignore_links = False
    parser.ignore_images = False
    return parser.handle(html)
'''


'''
wait_time = 60.0 # limit access to 60 seconds
last_access = datetime.now()

def wait():
    global last_access
    seconds = wait_time - (datetime.now() - last_access).total_seconds()
    if seconds > 0:
        time.sleep(seconds)
    last_access = datetime.now()    

@function_tool
def search_news(topic):     
    """Search for news articles using DuckDuckGo"""
    print("Using Tool: search_news ..")
    wait()
    with DDGS() as ddg:
        try:
            results = ddg.text(f"{topic} news {datetime.now().strftime('%Y-%m')}", max_results=3)
            if results:
                news_results = "\n\n".join([
                    f"Title: {result['title']}\nURL: {result['href']}\nSummary: {result['body']}" 
                    for result in results
                ])
                return news_results
            return f"No news found for {topic}."
        except Exception as e:
            print("ERROR: Using Tool 'search_news'")
            return e.msg if hasattr(e, "msg") else str(e)
    

# cache the web searches
web_searches_cache = {}

@function_tool
def search_the_web(topic):
    """Search for common articles using DuckDuckGo"""
    print("Using Tool: search_the_web ..")

    if web_searches_cache.get(topic):
        return web_searches_cache[topic]
    
    wait()
    news_results = ""
    with DDGS() as ddg:        
        try:
            results = ddg.text(topic, max_results=3)
            if results:
                news_results = "\n\n".join([
                    f"Title: {result['title']}\nURL: {result['href']}\nSummary: {result['body']}" 
                    for result in results
                ])    
            news_results = f"No news found for {topic}."
        except Exception as e:
            print(f"Error in search_the_web(): {str(e)}")
            return e.msg if hasattr(e, "msg") else str(e)
        
    web_searches_cache[topic] = news_results
    return news_results
'''