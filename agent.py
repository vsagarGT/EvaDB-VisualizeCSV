# agent.py
import os
import evadb
import pandas as pd

# Setting up the api key
import environ
#from dotenv import load_dotenv

# Load environment variables from .env
#load_dotenv()

cursor = evadb.connect().cursor()

API_KEY = os.environ.get("apikey")

def create_agent(filename: str):
    """
    Create an agent that can access and use a large language model (LLM).

    Args:
        filename: The path to the CSV file that contains the data.

    Returns:
        An agent that can access and use the LLM.
    """

    # Create an OpenAI object.
    try_to_import_openai()
    import openai

    @retry(tries=6, delay=20)
    def completion_with_backoff(**kwargs):
        return openai.ChatCompletion.create(**kwargs)

    # Register API key
    openai.api_key = os.environ.get('OPENAI_KEY')
    assert len(openai.api_key) != 0, (
        "Please set your OpenAI API key in evadb.yml file (third_party,"
        " open_api_key) or environment variable (OPENAI_KEY)"
    )

    queries = text_df[text_df.columns[0]]
    content = text_df[text_df.columns[0]]
    if len(text_df.columns) > 1:
        queries = text_df.iloc[:, 0]
        content = text_df.iloc[:, 1]

    prompt = None
    if len(text_df.columns) > 2:
        prompt = text_df.iloc[0, 2]

    # openai api currently supports answers to a single prompt only
    completion_tokens = 0
    prompt_tokens = 0


    # Read the CSV file into a Pandas DataFrame.
    df = pd.read_csv(filename)

    # Create a Pandas DataFrame agent.
    return create_pandas_dataframe_agent(llm, df, verbose=False)

def query_agent(agent, query):
    """
    Query an agent and return the response as a string.

    Args:
        agent: The agent to query.
        query: The query to ask the agent.

    Returns:
        The response from the agent as a string.
    """

    prompt = (
        """
            For the following query, if it requires drawing a table, reply as follows:
            {"table": {"columns": ["column1", "column2", ...], "data": [[value1, value2, ...], [value1, value2, ...], ...]}}

            If the query requires creating a bar chart, reply as follows:
            {"bar": {"columns": ["A", "B", "C", ...], "data": [25, 24, 10, ...]}}

            If the query requires creating a line chart, reply as follows:
            {"line": {"columns": ["A", "B", "C", ...], "data": [25, 24, 10, ...]}}

            There can only be two types of chart, "bar" and "line".

            If it is just asking a question that requires neither, reply as follows:
            {"answer": "answer"}
            Example:
            {"answer": "The title with the highest rating is 'Gilead'"}

            If you do not know the answer, reply as follows:
            {"answer": "I do not know."}

            Return all output as a string.

            All strings in "columns" list and data list, should be in double quotes,

            For example: {"columns": ["title", "ratings_count"], "data": [["Gilead", 361], ["Spider's Web", 5164]]}

            Lets think step by step.

            Below is the query.
            Query: 
            """
        + query
    )

    # Run the prompt through the agent.
    response = agent.run(prompt)

    # Convert the response to a string.
    return response.__str__()