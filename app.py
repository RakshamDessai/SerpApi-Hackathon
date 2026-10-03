"""
S2S (Syllabus-to-Ship) - Interactive Dashboard
Run with:
    streamlit run app.py
"""

import streamlit as st
from src.config import SERPAPI_API_KEY, is_serpapi_configured
from src.serpapi_service import SerpApiService
from src.agent import ResearchAgent

st.set_page_config(
    page_title="S2S - Syllabus-to-Ship",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🎓 S2S — Syllabus-to-Ship")
st.caption("Turn what you study into live, real-world work")

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuration")
    if is_serpapi_configured():
        st.success("✅ SerpApi Key is Configured")
    else:
        st.error("❌ SerpApi Key Missing")
        custom_key = st.text_input("Enter SerpApi Key temporarily:", type="password")
        if custom_key:
            st.session_state["custom_api_key"] = custom_key
            st.success("Key applied for this session!")

    api_key_to_use = st.session_state.get("custom_api_key") or SERPAPI_API_KEY
    serpapi_client = SerpApiService(api_key=api_key_to_use)
    agent = ResearchAgent(serpapi_service=serpapi_client)

# Main Tabs
tab_agent, tab_explorer = st.tabs([
    "🤖 Autonomous AI Agent",
    "🔎 Multi-Engine Explorer"
])

with tab_agent:
    st.subheader("Autonomous Research & Grounding Agent")
    st.write("Demonstrates an agent decomposing a query into subsearches, retrieving live results via SerpApi, and structuring citations.")
    
    topic_input = st.text_input("Enter a research topic:", value="Electric Vehicle Infrastructure in India")
    col_a1, col_a2 = st.columns([1, 4])
    with col_a1:
        run_agent = st.button("🚀 Run Research Agent", type="primary")

    if run_agent:
        if not api_key_to_use or api_key_to_use == "your_serpapi_api_key_here":
            st.error("Please add your SerpApi key in `.env` or the sidebar to run live queries.")
        else:
            with st.spinner("Agent planning queries and calling SerpApi..."):
                try:
                    result = agent.execute_research(topic_input)
                    st.success(f"Completed research! Retrieved {result['total_sources']} live sources.")
                    
                    st.markdown("### 📋 Planned Subqueries")
                    for q in result["queries_executed"]:
                        st.markdown(f"- `{q}`")
                        
                    st.markdown("### 📚 Extracted Knowledge & Citations")
                    for src in result["sources"]:
                        with st.expander(f"{src['title']} ({src['query']})"):
                            st.write(src["snippet"])
                            st.markdown(f"[Visit Source Link]({src['link']})")
                except Exception as e:
                    st.error(f"Error executing agent: {e}")

with tab_explorer:
    st.subheader("SerpApi Multi-Engine Playground")
    st.write("Test different search verticals supported by SerpApi.")
    
    engine_choice = st.selectbox(
        "Select Engine:",
        ["Google Web Search", "Google News", "Google Shopping", "Google Scholar", "Google Maps", "Google Jobs"]
    )
    
    search_query = st.text_input("Search query:", value="Top tech startups Bengaluru")
    
    if st.button("🔍 Search Engine"):
        if not api_key_to_use or api_key_to_use == "your_serpapi_api_key_here":
            st.error("Please add your SerpApi key in `.env` to execute live searches.")
        else:
            with st.spinner("Fetching data from SerpApi..."):
                try:
                    if engine_choice == "Google Web Search":
                        data = serpapi_client.search_web(search_query)
                        items = data.get("organic_results", [])
                    elif engine_choice == "Google News":
                        data = serpapi_client.search_news(search_query)
                        items = data.get("news_results", [])
                    elif engine_choice == "Google Shopping":
                        data = serpapi_client.search_shopping(search_query)
                        items = data.get("shopping_results", [])
                    elif engine_choice == "Google Scholar":
                        data = serpapi_client.search_scholar(search_query)
                        items = data.get("organic_results", [])
                    elif engine_choice == "Google Maps":
                        data = serpapi_client.search_maps(search_query)
                        items = data.get("local_results", [])
                    elif engine_choice == "Google Jobs":
                        data = serpapi_client.search_jobs(search_query)
                        items = data.get("jobs_results", [])

                    st.json(items[:5])
                except Exception as e:
                    st.error(f"Search failed: {e}")
