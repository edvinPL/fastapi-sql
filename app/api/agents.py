# Llamaindex imports
from llama_index.llms.openai import OpenAI
from llama_index.agent.openai import OpenAIAgent
from llama_index.tools.exa import ExaToolSpec
from llama_index.core.workflow import (
    Event,
    StartEvent,
    StopEvent,
    Workflow,
    step,
)
from llama_index.core.tools import FunctionTool
from app.api import prompts
from app.core.config import get_settings
from app.api import tools



class SEO_Platform_Strategist(Event):
    input: str

class Content_Strategist_Prompt_Weaver(Event):
    input: str

class Target_Audience_Trend_Alchemist(Event):
    input: str


class IdeationFlow(Workflow):
    llm = OpenAI(api_key=get_settings().OPENAI_API_KEY, model=get_settings().RESEARCH_LLM_NAME)
    
    report = {}

    @step()
    async def start_agent_flow(self, ev: StartEvent) -> Target_Audience_Trend_Alchemist:
        
        initial_input = ev.input
        prompt = f"Here is the initial topic I need youtube ideas on - {initial_input}."
        
        return Target_Audience_Trend_Alchemist(input=str(prompt))

    @step()
    async def trend_analysis(self, ev: Target_Audience_Trend_Alchemist) -> SEO_Platform_Strategist:
        input = ev.input
        
        system_prompt= prompts.Target_Audience_Trend_Alchemist_Prompt

        exa_tool = ExaToolSpec(
            api_key=get_settings().EXA_API_KEY
        )

        # avatar_tool = avatar_retreiver_tool()

        tool_list = [FunctionTool.from_defaults(tools.perplexity_ai_search, 
                        name="perplexity_ai_search", 
                        description="You can use this tool, to understand concepts or search for certain queries for elaboration. Useful when conducting research using Perplexity AI online model."
                        ),

                    FunctionTool.from_defaults(tools.youtube_search, 
                        name="youtube_search", 
                        description="Use this tool for searching YouTube videos for related topics. Make sure to pay attention to views and views to subscriber ratios."
                        ),
                    
                    FunctionTool.from_defaults(tools.channel_details_tool, 
                        name="channel_details_tool", 
                        description="Use this tool to retrieve details of a specific YouTube channel, like the subscriber count and channel description."
                        ),

                    FunctionTool.from_defaults(tools.youtube_video_details, 
                        name="youtube_video_details", 
                        description="Use this tool for retrieving detailed information about a youtube video, like the views, publish date, like count, channel id."
                        ),

                    FunctionTool.from_defaults(tools.transcribe_video, 
                        name="transcribe_video", 
                        description="Transcribe a YouTube video using Youtube Transcriptor RapidAPI."
                        ),

                    FunctionTool.from_defaults(tools.avatar_information, 
                        name="Avatar", 
                        description="use it to find out more about our target audience, our avatars. Their information about interests, age, employment and other information about them."
                        )
        ]

        tool_list.extend(exa_tool.to_tool_list())

        agent = OpenAIAgent.from_tools(tool_list, verbose=True, system_prompt=system_prompt, llm=self.llm)

        response = agent.chat(input)

        self.report["Trend_And_Audience_Analysis"] = str(response)

        return SEO_Platform_Strategist(input=str(response))
        # return StopEvent(result=str(response))

    @step()
    async def seo_optimization(self, ev: SEO_Platform_Strategist) -> Content_Strategist_Prompt_Weaver:

        input = f"Here is the output of the Target Audience Trend Alchemist: {ev.input}. I need you to validate the topics, titles, and thumbnails for search optimization."

        system_prompt= prompts.SEO_Platform_Strategist_Prompt

        exa_tool = ExaToolSpec(
            api_key=get_settings().EXA_API_KEY
        )

        tool_list = [FunctionTool.from_defaults(tools.google_promise, 
                        name="google_promise", 
                        description="Google Promise Keyword Tool used via RapidAPI, that should be used whenever you need to find information about current search volumes and popularity on any topic and keyword or phrase. It runs both dedicated global search for English language. You can also do dedicated location research by specifying country, like US or GB. Purpose: Fetches keyword data, including search volume, competition, and related keywords, from Google Keyword Planner via RapidAPI. Make sure that the input is no longer than 3 words"
                        )
        ]

        tool_list.extend(exa_tool.to_tool_list())

        agent = OpenAIAgent.from_tools(tool_list, verbose=True, system_prompt=system_prompt, llm=self.llm)

        response = agent.chat(input)

        self.report["SEO_Analysis"] = str(response)

        return Content_Strategist_Prompt_Weaver(input=str(response))
        

    @step()
    async def content_strategy(self, ev: Content_Strategist_Prompt_Weaver) -> StopEvent:

        input = f"This is the output of the Target_Audience_Trend_Alchemist: {self.report["Trend_And_Audience_Analysis"]}. \n\n This is the output of the SEO_Platform_Strategist:  {self.report["SEO_Analysis"]}"

        system_prompt= prompts.Content_Strategist_Prompt_Weaver_Prompt

        tool_list = [
                    FunctionTool.from_defaults(tools.ultimatebrain_information, 
                        name="Ultimate_Brain", 
                        description="This is the Ultimate_Brain that contains a lot of curated distilled knowledge about scripting, content creation, AI and optimal way to write youtube video scripts. It contains a lot of viable useful crucial key information for perfect youtube video masterpiece creation process. Especially titles, thumbnails, hooks, payoffs, cognitive bias, retention methods etc."
                        ),

                    FunctionTool.from_defaults(tools.avatar_information, 
                        name="Avatar", 
                        description="use it to find out more about our target audience, our avatars. Their information about interests, age, employment and other information about them."
                        )
            ]
        agent = OpenAIAgent.from_tools(tool_list, verbose=True, system_prompt=system_prompt, llm=self.llm)

        response = agent.chat(input)

        self.report["Content_Strategist_Prompt_Weaver"] = str(response)

        return StopEvent(result=str(response))



class Research_Navigator(Event):
    input: str

class Knowledge_Curator_Fact_Checker(Event):
    input: str


class ResearchFlow(Workflow):
    llm = OpenAI(api_key=get_settings().OPENAI_API_KEY, model=get_settings().RESEARCH_LLM_NAME)
    
    report = {}

    @step()
    async def start_agent_flow(self, ev: StartEvent) -> Research_Navigator:
        
        initial_input = ev.input
        ideation_output = ev.ideation
        prompt = f"Here is the initial topic - {initial_input}. \n I need you to find statistics, studies, examples from reputable scientific sources and store properly. \n\n Here are the 3 idea sets finalized: {ideation_output}"
        
        return Research_Navigator(input=str(prompt))

    @step()
    async def research_navigator(self, ev: Research_Navigator) -> Knowledge_Curator_Fact_Checker:
        input = ev.input
        
        system_prompt= prompts.Research_Navigator_Prompt

        tool_list = [FunctionTool.from_defaults(tools.Med_Articles_PMC, 
                        name="Med_Articles_PMC", 
                        description="Fetches medical literature data from the Europe PMC API. Use it to find scientific news - new research, letters, case reports and reviews from medical world."
                        ),

                    FunctionTool.from_defaults(tools.Semantic_Scholar_Tool, 
                        name="Semantic_Scholar_Tool", 
                        description="Use this tool to access a free, AI-powered research tool for scientific literature."
                        ),
                    
                    FunctionTool.from_defaults(tools.PubMed_Tool, 
                        name="PubMed_Tool", 
                        description="Searches PubMed NCBI Database for medical publications and research papers."
                        ),

                    FunctionTool.from_defaults(tools.Google_Scholar_Tool, 
                        name="Google_Scholar_Tool", 
                        description="Fetches scholarly articles from Google Scholar using SerpAPI"
                        )
        ]

        agent = OpenAIAgent.from_tools(tool_list, verbose=True, system_prompt=system_prompt, llm=self.llm)

        response = await agent.achat(input)

        self.report["Research_Navigator"] = str(response)

        return Knowledge_Curator_Fact_Checker(input=str(response))

    @step()
    async def knowledge_curator(self, ev: Knowledge_Curator_Fact_Checker) -> StopEvent:

        input = f"Here is the output of the Research_Navigator: {ev.input}"

        system_prompt= prompts.Knowledge_Curator_Fact_Checker_Prompt

        exa_tool = ExaToolSpec(
            api_key=get_settings().EXA_API_KEY
        )

        tool_list = [FunctionTool.from_defaults(tools.perplexity_ai_search, 
                        name="perplexity_ai_search", 
                        description="You can use this tool, to understand concepts or search for certain queries for elaboration. Useful when conducting research using Perplexity AI online model. You can also use this to fetch the content from the urls returns by Research_Navigator"
                        ),

                    FunctionTool.from_defaults(tools.save_in_notion, 
                        name="save_in_notion", 
                        description="Use this to send information to Notion database"
                        ),

                    FunctionTool.from_defaults(tools.upsert_to_qdrant, 
                        name="upsert_to_qdrant", 
                        description="Use this to upsert the notion page's data into Qdrant Vector Store. Example input: page_id: 3c8babb6-0666-48e6-a584-444ddf7a008f"
                        )

        ]

        tool_list.extend(exa_tool.to_tool_list())

        agent = OpenAIAgent.from_tools(tool_list, verbose=True, system_prompt=system_prompt, llm=self.llm)

        response = await agent.achat(input)

        self.report["Knowledge_Curator_Fact_Checker"] = str(response)

        return StopEvent(result=str(response))
        
class Lead_Scriptwriter_Engagement_Maestro(Event):
    input: str

class Scientific_Accuracy_Clarity_Guardian(Event):
    input: str

class Call_to_Action_Channel_Integration_Specialist(Event):
    input: str

class ScriptingFlow(Workflow):
    llm = OpenAI(api_key=get_settings().OPENAI_API_KEY, model=get_settings().RESEARCH_LLM_NAME)
    
    report = {}

    @step()
    async def start_agent_flow(self, ev: StartEvent) -> Lead_Scriptwriter_Engagement_Maestro:
        
        ideation_output = ev.ideation
        research_output = ev.research
        prompt = f"Here is the chosen set from output of Team 1 (Ideation Workflow): {ideation_output}. \n\n Here is the output of Team 2 (Medical Researcher): {research_output}"
        
        return Lead_Scriptwriter_Engagement_Maestro(input=str(prompt))

    @step()
    async def scriptwriter(self, ev: Lead_Scriptwriter_Engagement_Maestro) -> Scientific_Accuracy_Clarity_Guardian:
        input = ev.input
        
        system_prompt= prompts.Lead_Scriptwriter_Engagement_Maestro_Prompt

        tool_list = [FunctionTool.from_defaults(tools.avatar_information, 
                        name="Avatar", 
                        description="use it to find out more about our target audience, our avatars. Their information about interests, age, employment and other information about them."
                        ),

                    FunctionTool.from_defaults(tools.sugarbrain_information, 
                        name="Ultimate_Brain", 
                        description="Use it to retrieve all the important information for current script in terms of scientific knowledge. It contains research papers, notes, insights, conclusions, scientific review articles and much more relating to current problem we are trying to tackle in the video. Use it always."
                        )
        ]

        agent = OpenAIAgent.from_tools(tool_list, verbose=True, system_prompt=system_prompt, llm=self.llm)

        response = agent.chat(input)

        # self.report["Lead_Scriptwriter_Engagement_Maestro"] = str(response)

        return Scientific_Accuracy_Clarity_Guardian(input=str(response))

    @step()
    async def accuracy_check(self, ev: Scientific_Accuracy_Clarity_Guardian) -> Call_to_Action_Channel_Integration_Specialist:

        input = f"Here is the first draft of the script: {ev.input}"

        system_prompt= prompts.Scientific_Accuracy_Clarity_Guardian_Prompt

        tool_list = [FunctionTool.from_defaults(tools.ultimatebrain_information, 
                        name="scripting_brain", 
                        description="This is a database that contains a lot of curated distilled knowledge about scripting, content creation and optimal way to write youtube video scripts. It contains a lot of viable, useful, crucial, key information for perfect, masterpiece youtube video content creation process."
                        ),

                    FunctionTool.from_defaults(tools.sugarbrain_information, 
                        name="Ultimate_Brain", 
                        description="Use it to retrieve all the important information for current script in terms of scientific knowledge. It contains research papers, notes, insights, conclusions, scientific review articles and much more relating to current problem we are trying to tackle in the video. Use it always."
                        )
        ]

        agent = OpenAIAgent.from_tools(tool_list, verbose=True, system_prompt=system_prompt, llm=self.llm)

        response = agent.chat(input)

        self.report["Scientific_Accuracy_Clarity_Guardian"] = str(response)

        return Call_to_Action_Channel_Integration_Specialist(input=str(response))
        
    @step()
    async def final_script(self, ev: Call_to_Action_Channel_Integration_Specialist) -> StopEvent:

        input = f"Here is the output of the Scientific_Accuracy_Clarity_Guardian: {ev.input}"

        system_prompt= prompts.Call_to_Action_Channel_Integration_Specialist_Prompt

        tool_list = [FunctionTool.from_defaults(tools.ultimatebrain_information, 
                        name="scripting_brain", 
                        description="This is a database that contains a lot of curated distilled knowledge about scripting, content creation and optimal way to write youtube video scripts. It contains a lot of viable, useful, crucial, key information for perfect, masterpiece youtube video content creation process."
                        )
        ]

        agent = OpenAIAgent.from_tools(tool_list, verbose=True, system_prompt=system_prompt, llm=self.llm)

        response = agent.chat(input)

        self.report["Call_to_Action_Channel_Integration_Specialist"] = str(response)

        return StopEvent(result=self.report)