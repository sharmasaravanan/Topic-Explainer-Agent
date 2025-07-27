import os
from typing import TypedDict, List, Literal
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_community.tools import WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper
from langchain_community.tools import YouTubeSearchTool
from langchain_openai import OpenAI
import openai
import requests
import json

# Set up your API keys
# os.environ["OPENAI_API_KEY"] = "your-openai-api-key"

class AgentState(TypedDict):
    user_query: str
    reasoning: str
    selected_medium: Literal["text", "image", "video"]
    output: str
    messages: List[dict]

class ChittiAgent:
    def __init__(self):
        # Initialize tools
        self.llm = ChatOpenAI(model="gpt-4", temperature=0)
        
        # Wikipedia tool
        wikipedia = WikipediaAPIWrapper(top_k_results=1, doc_content_chars_max=1000)
        self.wikipedia_tool = WikipediaQueryRun(api_wrapper=wikipedia)
        
        # YouTube search tool
        self.youtube_tool = YouTubeSearchTool()
        
        # OpenAI client for DALL-E
        self.openai_client = openai.OpenAI()
        
        # Build the graph
        self.graph = self._build_graph()
    
    def _build_graph(self):
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("analyze_query", self.analyze_query)
        workflow.add_node("get_wikipedia", self.get_wikipedia)
        workflow.add_node("generate_image", self.generate_image)
        workflow.add_node("search_youtube", self.search_youtube)
        workflow.add_node("format_response", self.format_response)
        
        # Define the flow
        workflow.set_entry_point("analyze_query")
        
        # Add conditional edges based on selected medium
        workflow.add_conditional_edges(
            "analyze_query",
            self.route_to_medium,
            {
                "text": "get_wikipedia",
                "image": "generate_image",
                "video": "search_youtube"
            }
        )
        
        # All paths lead to format_response
        workflow.add_edge("get_wikipedia", "format_response")
        workflow.add_edge("generate_image", "format_response")
        workflow.add_edge("search_youtube", "format_response")
        
        # End after formatting
        workflow.add_edge("format_response", END)
        
        return workflow.compile()
    
    def analyze_query(self, state: AgentState) -> AgentState:
        """Analyze the user query and determine the best medium for explanation."""
        query = state["user_query"]
        
        analysis_prompt = f"""
        You are Chitti, an AI that determines the best medium (text, image, or video) to explain a topic.
        
        Analyze this user query: "{query}"
        
        Consider:
        - Text: Best for definitions, concepts, historical facts, scientific explanations
        - Image: Best for visual appearance, objects, places, visual concepts
        - Video: Best for processes, tutorials, demonstrations, step-by-step instructions
        
        Respond with ONLY:
        1. Your reasoning (2-3 sentences explaining why you chose this medium)
        2. The selected medium: either "text", "image", or "video"
        
        Format:
        REASONING: [your reasoning here]
        MEDIUM: [text/image/video]
        """
        
        response = self.llm.invoke(analysis_prompt)
        content = response.content
        
        # Parse the response
        lines = content.strip().split('\n')
        reasoning = ""
        medium = "text"  # default
        
        for line in lines:
            if line.startswith("REASONING:"):
                reasoning = line.replace("REASONING:", "").strip()
            elif line.startswith("MEDIUM:"):
                medium = line.replace("MEDIUM:", "").strip().lower()
        
        state["reasoning"] = reasoning
        state["selected_medium"] = medium
        
        return state
    
    def route_to_medium(self, state: AgentState) -> str:
        """Router function to direct to appropriate tool based on selected medium."""
        return state["selected_medium"]
    
    def get_wikipedia(self, state: AgentState) -> AgentState:
        """Get Wikipedia summary for text-based explanations."""
        try:
            wiki_result = self.wikipedia_tool.run(state["user_query"])
            state["output"] = wiki_result
        except Exception as e:
            state["output"] = f"Error retrieving Wikipedia information: {str(e)}"
        
        return state
    
    def generate_image(self, state: AgentState) -> AgentState:
        """Generate image using DALL-E for visual explanations."""
        try:
            # Create a more descriptive prompt for DALL-E
            image_prompt = f"A clear, educational illustration of {state['user_query']}, high quality, detailed"
            
            response = self.openai_client.images.generate(
                model="dall-e-3",
                prompt=image_prompt,
                size="1024x1024",
                quality="standard",
                n=1,
            )
            
            image_url = response.data[0].url
            state["output"] = image_url
            
        except Exception as e:
            state["output"] = f"Error generating image: {str(e)}"
        
        return state
    
    def search_youtube(self, state: AgentState) -> AgentState:
        """Search YouTube for video explanations."""
        try:
            # Search for relevant videos
            youtube_results = self.youtube_tool.run(f"{state['user_query']} tutorial explanation")
            
            # Parse the results to extract video links
            # The YouTube tool typically returns a string with video information
            state["output"] = youtube_results
            
        except Exception as e:
            state["output"] = f"Error searching YouTube: {str(e)}"
        
        return state
    
    def format_response(self, state: AgentState) -> AgentState:
        """Format the final response with reasoning and output."""
        medium = state["selected_medium"]
        reasoning = state["reasoning"]
        output = state["output"]
        
        if medium == "text":
            formatted_response = f"""**Reasoning:** {reasoning}

**Wikipedia Summary:**
{output}"""
        
        elif medium == "image":
            formatted_response = f"""**Reasoning:** {reasoning}

**Generated Image:**
![Generated Image]({output})

Image URL: {output}"""
        
        elif medium == "video":
            formatted_response = f"""**Reasoning:** {reasoning}

**YouTube Videos:**
{output}"""
        
        state["messages"] = [{"role": "assistant", "content": formatted_response}]
        
        return state
    
    def run(self, user_query: str) -> str:
        """Run the agent with a user query."""
        initial_state = {
            "user_query": user_query,
            "reasoning": "",
            "selected_medium": "text",
            "output": "",
            "messages": []
        }
        
        final_state = self.graph.invoke(initial_state)
        
        return final_state["messages"][0]["content"]

# Usage example
def main():
    # Initialize the agent
    chitti = ChittiAgent()
    
    # Example queries
    test_queries = [
        "The process of photosynthesis",
        "What does a blue whale look like?",
        "How to tie a Windsor knot",
        "Explain quantum physics",
        "Show me the Eiffel Tower",
        "How to make chocolate chip cookies"
    ]
    
    print("🤖 Chitti Agent - Multi-Modal Topic Explainer")
    print("=" * 50)
    
    for query in test_queries:
        print(f"\n📝 Query: {query}")
        print("-" * 30)
        try:
            response = chitti.run(query)
            print(response)
        except Exception as e:
            print(f"Error: {str(e)}")
        print()

# Alternative simplified version without some dependencies
class SimpleChittiAgent:
    """Simplified version that can work with basic LangChain setup"""
    
    def __init__(self):
        self.llm = ChatOpenAI(model="gpt-4", temperature=0)
    
    def analyze_and_respond(self, user_query: str) -> str:
        prompt = f"""
        You are Chitti, a helpful bot specialized in explaining topics through the most effective medium.
        
        For the query: "{user_query}"
        
        1. First, provide your REASONING for which medium (text, image, or video) would be best
        2. Then provide a mock response in that format:
           - For text: Provide a detailed explanation
           - For image: Describe what image would be generated and provide a placeholder URL
           - For video: List relevant video topics that would be searched
        
        Always start with "**Reasoning:**" followed by your analysis, then provide the appropriate output.
        """
        
        response = self.llm.invoke(prompt)
        return response.content

if __name__ == "__main__":
    main()
